"""
Export completed Prolific study submissions to data/raw_export.csv.

Prolific splits participation metadata and survey answers across two APIs:
  1. Submissions API  — who completed the study and whether they were approved
  2. Surveys API      — the actual question/answer text from a Prolific-native survey

This script joins those two sources, maps questions to our export columns via
demo/config.yaml, and writes a CSV ready for upload in the frontend dashboard.
Gemini scoring happens later in the backend; this file contains survey fields only.

See demo/PROLIFIC.md for full documentation.
"""

from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv

load_dotenv()

# Base URL for all Prolific REST calls (API v1).
# Docs: https://docs.prolific.com/api-reference/
PROLIFIC_API_URL = "https://api.prolific.com/api/v1"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "raw_export.csv"

REQUIRED_OUTPUT_COLUMNS = ["manager_id", "worker_type", "text_type", "raw_text"]

# Top-level fields on a survey response object (not question answers).
SUBMISSION_TOP_LEVEL_FIELDS = {"participant_id", "submission_id", "id"}


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {
            "survey_id": None,
            "field_mapping": {
                "manager_id": "participant_id",
                "worker_type": "worker_type",
                "text_type": "text_type",
                "raw_text": "raw_text",
            },
        }

    with config_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def prolific_headers(api_token: str) -> dict[str, str]:
    """Auth header required on every Prolific API request.

    Create a token in Prolific → Settings → API. Pass it as PROLIFIC_API_KEY in .env.
    Docs: https://docs.prolific.com/api-reference/
    """
    return {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
    }


def fetch_approved_submission_ids(study_id: str, api_token: str) -> set[str]:
    """List submissions for a study and return IDs with status APPROVED.

    Endpoint: GET /api/v1/submissions/?study={study_id}
    Docs: https://docs.prolific.com/api-reference/submissions/get-submissions

    This endpoint returns participation metadata only (participant_id, status,
    timestamps). It does NOT include survey question answers.
    """
    headers = prolific_headers(api_token)
    approved_ids: set[str] = set()
    page = 1
    page_size = 100

    while True:
        response = requests.get(
            f"{PROLIFIC_API_URL}/submissions/",
            headers=headers,
            params={"study": study_id, "page": page, "page_size": page_size},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        page_results = payload.get("results", [])
        for submission in page_results:
            if submission.get("status") == "APPROVED":
                submission_id = submission.get("id")
                if submission_id:
                    approved_ids.add(str(submission_id))

        # Prolific paginates with page/page_size; stop when a page is short.
        if len(page_results) < page_size:
            break
        page += 1

    return approved_ids


def fetch_survey_responses(survey_id: str, api_token: str) -> list[dict]:
    """Fetch all responses for a Prolific-native survey (includes question answers).

    Endpoint: GET /api/v1/surveys/{survey_id}/responses/
    Docs: https://docs.prolific.com/api-reference/surveys/get-responses

  Each result contains participant_id, submission_id, and sections[].questions[]
  with question_id, question_title, and answers[].value.

  This only works for surveys built in Prolific's survey tool. If your study
  redirects to Qualtrics/Typeform/etc., export from that platform instead.
    """
    headers = prolific_headers(api_token)
    response = requests.get(
        f"{PROLIFIC_API_URL}/surveys/{survey_id}/responses/",
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("results", [])


def extract_question_answers(survey_response: dict) -> dict[str, str]:
    """Flatten Prolific survey sections/questions into {question_id: answer_text}."""
    answers_by_question: dict[str, str] = {}
    questions: list[dict] = []

    for section in survey_response.get("sections", []):
        questions.extend(section.get("questions", []))
    questions.extend(survey_response.get("questions", []))

    for question in questions:
        question_id = question.get("question_id")
        if not question_id:
            continue
        values = [
            str(answer.get("value", "")).strip()
            for answer in question.get("answers", [])
            if answer.get("value") not in (None, "")
        ]
        if values:
            answers_by_question[str(question_id)] = "; ".join(values)

    return answers_by_question


def map_survey_response(
    survey_response: dict,
    field_mapping: dict[str, str],
) -> dict[str, str]:
    """Map one Prolific survey response to our export row using config.yaml."""
    question_answers = extract_question_answers(survey_response)

    def resolve(field_name: str) -> str:
        source_key = field_mapping.get(field_name, field_name)

        # Survey answers are keyed by Prolific question_id (UUID strings).
        if source_key in question_answers:
            return question_answers[source_key]

        # participant_id and submission_id live on the response object itself.
        if source_key in SUBMISSION_TOP_LEVEL_FIELDS and source_key in survey_response:
            return str(survey_response[source_key]).strip()

        return ""

    mapped = {column: resolve(column) for column in REQUIRED_OUTPUT_COLUMNS}

    if not mapped["manager_id"]:
        mapped["manager_id"] = str(survey_response.get("participant_id", "")).strip()

    if not mapped["text_type"]:
        mapped["text_type"] = "performance_review"

    return mapped


def write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Prolific submissions to CSV")
    parser.add_argument("--study-id", required=True, help="Prolific study ID")
    parser.add_argument(
        "--survey-id",
        help="Prolific native survey ID (overrides config.yaml survey_id)",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help=f"Output CSV path (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Field mapping config (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--include-unapproved",
        action="store_true",
        help="Include survey responses even if the submission is not APPROVED",
    )
    args = parser.parse_args()

    api_token = os.getenv("PROLIFIC_API_KEY")
    if not api_token:
        raise SystemExit("PROLIFIC_API_KEY is not set in the environment.")

    config = load_config(Path(args.config))
    field_mapping = config.get("field_mapping", {})
    survey_id = args.survey_id or config.get("survey_id")
    if not survey_id:
        raise SystemExit(
            "survey_id is required. Set it in demo/config.yaml or pass --survey-id. "
            "See demo/PROLIFIC.md for how to find it."
        )

    approved_submission_ids = fetch_approved_submission_ids(args.study_id, api_token)
    survey_responses = fetch_survey_responses(survey_id, api_token)

    rows: list[dict[str, str]] = []
    for survey_response in survey_responses:
        submission_id = str(survey_response.get("submission_id", ""))
        if not args.include_unapproved and submission_id not in approved_submission_ids:
            continue

        mapped = map_survey_response(survey_response, field_mapping)
        if mapped.get("raw_text"):
            rows.append(mapped)

    output_path = Path(args.output)
    write_csv(rows, output_path)
    print(
        f"Wrote {len(rows)} row(s) to {output_path} "
        f"(approved submissions in study: {len(approved_submission_ids)})"
    )


if __name__ == "__main__":
    main()

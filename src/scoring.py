import json
import logging
import os
import re
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.models import GeminiScores, ScoredSubmission, SubmissionInput

load_dotenv()

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-2.5-flash"
BATCH_POLL_INTERVAL_SECONDS = 5
BATCH_COMPLETED_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}

SCORING_PROMPT = """You are scoring a manager's written evaluation of an employee.

Read the text and reason through your scoring before outputting results.

Scale definitions (use the full range; do not compress scores toward the middle):

trust_score:
- 0 = constant micromanagement, no benefit of the doubt, no autonomy
- 100 = complete trust; manager lets the worker operate independently

criticism_score:
- 0 = no criticism at all; entirely positive or neutral language
- 100 = extremely harsh, punitive, or severely critical language

Text to score:
{text}

---

First, think step by step:
1. Identify specific phrases or sentences that signal trust or autonomy (or the lack thereof).
2. Identify specific phrases or sentences that signal criticism or praise.
3. Anchor each score to the scale above — consider what a 0, 50, and 100 would look like, then place this text relative to those anchors.

Then output ONLY valid JSON with this exact structure (no extra text after the JSON):
{{
  "reasoning": {{
    "trust": "<your reasoning for the trust score>",
    "criticism": "<your reasoning for the criticism score>"
  }},
  "trust_score": [<int>, "<one-sentence summary>"],
  "criticism_score": [<int>, "<one-sentence summary>"]
}}
"""  # double brackets are escaped because of the prompt template


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set")
    return genai.Client(api_key=api_key)


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group())


def _build_scoring_request(submission: SubmissionInput) -> dict:
    return {
        "contents": [
            {
                "parts": [{"text": SCORING_PROMPT.format(text=submission.raw_text)}],
                "role": "user",
            }
        ],
        "config": {
            "response_mime_type": "application/json",
            "temperature": 0.0,
        },
    }


def _parse_scored_submission(
    submission: SubmissionInput, raw: str
) -> ScoredSubmission | None:
    if not raw:
        logger.warning(
            "Empty Gemini response for manager_id=%s", submission.manager_id
        )
        return None

    payload = _extract_json(raw)
    scores = GeminiScores.model_validate(payload)

    return ScoredSubmission(
        manager_id=submission.manager_id,
        worker_type=submission.worker_type,
        text_type=submission.text_type,
        raw_text=submission.raw_text,
        trust_score=scores.trust_score / 100.0,
        criticism_score=scores.criticism_score / 100.0,
    )


def score_submission(submission: SubmissionInput) -> ScoredSubmission | None:
    """Score a single submission via Gemini. Returns None on failure."""
    try:
        client = _get_client()
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=SCORING_PROMPT.format(text=submission.raw_text),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        return _parse_scored_submission(submission, response.text or "")
    except Exception as exc:
        logger.warning(
            "Failed to score submission for manager_id=%s: %s",
            submission.manager_id,
            exc,
        )
        return None


def _wait_for_batch_job(client: genai.Client, job_name: str):
    batch_job = client.batches.get(name=job_name)
    while batch_job.state.name not in BATCH_COMPLETED_STATES:
        time.sleep(BATCH_POLL_INTERVAL_SECONDS)
        batch_job = client.batches.get(name=job_name)
    return batch_job


def score_submissions_batch(
    submissions: list[SubmissionInput],
) -> tuple[list[ScoredSubmission], list[tuple[int, str]]]:
    """Score submissions via the Gemini Batch API.

    Returns (scored_submissions, failed_items) where each failed item is
    (row_index, reason).
    """
    if not submissions:
        return [], []

    client = _get_client()
    inline_requests = [_build_scoring_request(s) for s in submissions]

    batch_job = client.batches.create(
        model=MODEL_NAME,
        src=inline_requests,
        config={"display_name": "prolific-scoring-batch"},
    )

    batch_job = _wait_for_batch_job(client, batch_job.name)
    scored: list[ScoredSubmission] = []
    failed: list[tuple[int, str]] = []

    if batch_job.state.name != "JOB_STATE_SUCCEEDED":
        error_msg = (
            str(batch_job.error)
            if batch_job.error
            else f"Batch job ended with state {batch_job.state.name}"
        )
        for index in range(len(submissions)):
            failed.append((index, error_msg))
        return scored, failed

    inline_responses = batch_job.dest.inlined_responses or []
    for index, (submission, inline_response) in enumerate(
        zip(submissions, inline_responses)
    ):
        if inline_response.error:
            failed.append(
                (
                    index,
                    f"Gemini batch request failed: {inline_response.error}",
                )
            )
            continue
        if not inline_response.response:
            failed.append(
                (
                    index,
                    "Gemini scoring failed or returned invalid JSON.",
                )
            )
            continue

        try:
            result = _parse_scored_submission(
                submission, inline_response.response.text or ""
            )
        except Exception as exc:
            logger.warning(
                "Failed to parse batch response for manager_id=%s: %s",
                submission.manager_id,
                exc,
            )
            result = None

        if result is None:
            failed.append(
                (
                    index,
                    "Gemini scoring failed or returned invalid JSON.",
                )
            )
            continue
        scored.append(result)

    for index in range(len(inline_responses), len(submissions)):
        failed.append(
            (
                index,
                "Gemini scoring failed or returned no response.",
            )
        )

    return scored, failed

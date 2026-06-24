import json
import logging
import os
import re

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.models import GeminiScores, ScoredSubmission, SubmissionInput

load_dotenv()

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-2.5-flash"

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
        raw = response.text
        if not raw:
            logger.warning(
                "Empty Gemini response for manager_id=%s", submission.manager_id)
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
    except Exception as exc:
        logger.warning(
            "Failed to score submission for manager_id=%s: %s",
            submission.manager_id,
            exc,
        )
        return None

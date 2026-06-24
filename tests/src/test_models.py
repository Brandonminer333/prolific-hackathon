import pytest
from pydantic import ValidationError

from src.models import (
    GeminiScores,
    ScoredSubmission,
    SubmissionInput,
    SubmitRequest,
)


@pytest.mark.unit
def test_submission_input_accepts_valid_worker_types():
    submission = SubmissionInput(
        manager_id="mgr-1",
        worker_type="remote",
        text_type="performance_review",
        raw_text="Strong performer.",
    )
    assert submission.worker_type == "remote"


@pytest.mark.unit
def test_submission_input_rejects_invalid_worker_type():
    with pytest.raises(ValidationError):
        SubmissionInput(
            manager_id="mgr-1",
            worker_type="hybrid",
            text_type="performance_review",
            raw_text="Strong performer.",
        )


@pytest.mark.unit
def test_gemini_scores_enforces_0_to_100_range():
    scores = GeminiScores(trust_score=0, criticism_score=100)
    assert scores.trust_score == 0
    assert scores.criticism_score == 100


@pytest.mark.unit
def test_gemini_scores_rejects_out_of_range_values():
    with pytest.raises(ValidationError):
        GeminiScores(trust_score=101, criticism_score=50)


@pytest.mark.unit
def test_scored_submission_accepts_normalized_scores():
    scored = ScoredSubmission(
        manager_id="mgr-1",
        worker_type="in_person",
        text_type="email",
        raw_text="Good work.",
        trust_score=0.75,
        criticism_score=0.25,
    )
    assert scored.trust_score == 0.75


@pytest.mark.unit
def test_submit_request_requires_at_least_one_submission():
    with pytest.raises(ValidationError):
        SubmitRequest(submissions=[])

from unittest.mock import MagicMock, patch

import pytest

from src.models import SubmissionInput
from src.scoring import _extract_json, score_submission


@pytest.mark.unit
def test_extract_json_parses_plain_json_object():
    payload = _extract_json('{"trust_score": 80, "criticism_score": 20}')
    assert payload["trust_score"] == 80
    assert payload["criticism_score"] == 20


@pytest.mark.unit
def test_extract_json_strips_markdown_code_fence():
    payload = _extract_json(
        '```json\n{"trust_score": 65, "criticism_score": 10}\n```'
    )
    assert payload["trust_score"] == 65


@pytest.mark.unit
def test_extract_json_raises_on_invalid_payload():
    with pytest.raises(Exception):
        _extract_json("not json at all")


@pytest.mark.functional
@patch("src.scoring._get_client")
def test_score_submission_returns_scored_submission(mock_get_client):
    mock_response = MagicMock()
    mock_response.text = '{"trust_score": 72, "criticism_score": 31}'
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    mock_get_client.return_value = mock_client

    submission = SubmissionInput(
        manager_id="mgr-1",
        worker_type="remote",
        text_type="performance_review",
        raw_text="Trusted to work independently.",
    )

    result = score_submission(submission)

    assert result is not None
    assert result.trust_score == pytest.approx(0.72)
    assert result.criticism_score == pytest.approx(0.31)
    assert result.manager_id == "mgr-1"


@pytest.mark.functional
@patch("src.scoring._get_client")
def test_score_submission_returns_none_on_invalid_gemini_json(mock_get_client):
    mock_response = MagicMock()
    mock_response.text = '{"trust_score": "not-a-number", "criticism_score": 10}'
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    mock_get_client.return_value = mock_client

    submission = SubmissionInput(
        manager_id="mgr-2",
        worker_type="in_person",
        text_type="performance_review",
        raw_text="Needs improvement.",
    )

    assert score_submission(submission) is None

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from src.models import ScoredSubmission


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.integration
def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.integration
def test_results_returns_empty_payload_when_no_csv(client, submissions_csv_path):
    assert not submissions_csv_path.exists()

    response = client.get("/results")
  assert response.status_code == 200
  payload = response.json()
  assert payload["submissions"] == []
  assert payload["interpretation"] == ["No submissions have been scored yet."]


@pytest.mark.integration
@patch("api.main.score_submission")
def test_submit_scores_and_persists_rows(mock_score, client, submissions_csv_path):
    mock_score.return_value = ScoredSubmission(
        manager_id="mgr-1",
        worker_type="remote",
        text_type="performance_review",
        raw_text="Independent contributor.",
        trust_score=0.8,
        criticism_score=0.2,
    )

    response = client.post(
        "/submit",
        json={
            "submissions": [
                {
                    "manager_id": "mgr-1",
                    "worker_type": "remote",
                    "text_type": "performance_review",
                    "raw_text": "Independent contributor.",
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["scored"]) == 1
    assert body["failed"] == []
    assert submissions_csv_path.exists()

    results_response = client.get("/results")
    assert results_response.status_code == 200
    assert len(results_response.json()["submissions"]) == 1


@pytest.mark.integration
@patch("api.main.score_submission")
def test_submit_reports_failed_rows(mock_score, client, submissions_csv_path):
    mock_score.return_value = None

    response = client.post(
        "/submit",
        json={
            "submissions": [
                {
                    "manager_id": "mgr-1",
                    "worker_type": "in_person",
                    "text_type": "performance_review",
                    "raw_text": "Some text.",
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["scored"] == []
    assert len(body["failed"]) == 1
    assert body["failed"][0]["row_index"] == 0
    assert not submissions_csv_path.exists()

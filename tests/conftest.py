from pathlib import Path

import pytest

from src.models import ScoredSubmission


@pytest.fixture
def sample_scored_submissions() -> list[ScoredSubmission]:
    return [
        ScoredSubmission(
            manager_id="m1",
            worker_type="remote",
            text_type="performance_review",
            raw_text="Needs close oversight.",
            trust_score=0.35,
            criticism_score=0.72,
        ),
        ScoredSubmission(
            manager_id="m2",
            worker_type="remote",
            text_type="performance_review",
            raw_text="Reliable but check in often.",
            trust_score=0.55,
            criticism_score=0.40,
        ),
        ScoredSubmission(
            manager_id="m3",
            worker_type="remote",
            text_type="performance_review",
            raw_text="Strong independent contributor.",
            trust_score=0.82,
            criticism_score=0.15,
        ),
        ScoredSubmission(
            manager_id="m4",
            worker_type="in_person",
            text_type="performance_review",
            raw_text="Excellent teammate, fully trusted.",
            trust_score=0.90,
            criticism_score=0.10,
        ),
        ScoredSubmission(
            manager_id="m5",
            worker_type="in_person",
            text_type="performance_review",
            raw_text="Consistently delivers with minimal guidance.",
            trust_score=0.85,
            criticism_score=0.12,
        ),
        ScoredSubmission(
            manager_id="m6",
            worker_type="in_person",
            text_type="performance_review",
            raw_text="Good performance overall.",
            trust_score=0.78,
            criticism_score=0.20,
        ),
    ]


@pytest.fixture
def sample_survey_response() -> dict:
    return {
        "participant_id": "participant-123",
        "submission_id": "submission-456",
        "sections": [
            {
                "section_id": "section-1",
                "questions": [
                    {
                        "question_id": "worker-q",
                        "question_title": "Worker type",
                        "answers": [{"value": "remote"}],
                    },
                    {
                        "question_id": "text-type-q",
                        "question_title": "Text type",
                        "answers": [{"value": "performance_review"}],
                    },
                    {
                        "question_id": "raw-text-q",
                        "question_title": "Review text",
                        "answers": [{"value": "Alex works independently."}],
                    },
                ],
            }
        ],
    }


@pytest.fixture
def submissions_csv_path(tmp_path: Path, monkeypatch):
    csv_path = tmp_path / "submissions.csv"
    data_dir = tmp_path

    import api.main as api_main

    monkeypatch.setattr(api_main, "DATA_DIR", data_dir)
    monkeypatch.setattr(api_main, "SUBMISSIONS_CSV", csv_path)
    return csv_path

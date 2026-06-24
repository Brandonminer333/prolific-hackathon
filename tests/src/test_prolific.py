from pathlib import Path

import pytest

from demo.prolific import (
    extract_question_answers,
    load_config,
    map_survey_response,
    prolific_headers,
    write_csv,
)


@pytest.mark.unit
def test_prolific_headers_uses_token_authorization():
    headers = prolific_headers("test-token-abc")
    assert headers["Authorization"] == "Token test-token-abc"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.unit
def test_extract_question_answers_flattens_sections_and_top_level_questions():
    survey_response = {
        "sections": [
            {
                "questions": [
                    {
                        "question_id": "q1",
                        "answers": [{"value": "remote"}],
                    }
                ]
            }
        ],
        "questions": [
            {
                "question_id": "q2",
                "answers": [{"value": "first"}, {"value": "second"}],
            }
        ],
    }
    answers = extract_question_answers(survey_response)
    assert answers["q1"] == "remote"
    assert answers["q2"] == "first; second"


@pytest.mark.functional
def test_map_survey_response_applies_field_mapping(sample_survey_response):
    field_mapping = {
        "manager_id": "participant_id",
        "worker_type": "worker-q",
        "text_type": "text-type-q",
        "raw_text": "raw-text-q",
    }
    row = map_survey_response(sample_survey_response, field_mapping)
    assert row["manager_id"] == "participant-123"
    assert row["worker_type"] == "remote"
    assert row["text_type"] == "performance_review"
    assert row["raw_text"] == "Alex works independently."


@pytest.mark.functional
def test_map_survey_response_defaults_text_type_when_missing(sample_survey_response):
    field_mapping = {
        "manager_id": "participant_id",
        "worker_type": "worker-q",
        "text_type": "missing-question",
        "raw_text": "raw-text-q",
    }
    row = map_survey_response(sample_survey_response, field_mapping)
    assert row["text_type"] == "performance_review"


@pytest.mark.functional
def test_load_config_returns_defaults_when_file_missing(tmp_path: Path):
    config = load_config(tmp_path / "missing.yaml")
    assert config["field_mapping"]["manager_id"] == "participant_id"


@pytest.mark.functional
def test_write_csv_writes_expected_columns(tmp_path: Path):
    output_path = tmp_path / "export.csv"
    rows = [
        {
            "manager_id": "p1",
            "worker_type": "remote",
            "text_type": "performance_review",
            "raw_text": "Great work.",
        }
    ]
    write_csv(rows, output_path)
    content = output_path.read_text(encoding="utf-8")
    assert "manager_id,worker_type,text_type,raw_text" in content
    assert "Great work." in content

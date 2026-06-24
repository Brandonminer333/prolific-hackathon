import pandas as pd
import pytest

from src.analysis import (
    _effect_size_label,
    _group_summary,
    _interpret_trust,
    _mann_whitney,
    analyze_submissions,
)
from src.models import LogisticResult, MannWhitneyResult, ScoredSubmission


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.05, "negligible"),
        (0.2, "small"),
        (0.4, "medium"),
        (0.6, "large"),
    ],
)
def test_effect_size_label(value, expected):
    assert _effect_size_label(value) == expected


@pytest.mark.unit
def test_mann_whitney_returns_message_when_group_too_small():
    frame = pd.DataFrame(
        {
            "worker_type": ["remote", "in_person"],
            "trust_score": [0.5, 0.8],
        }
    )
    result = _mann_whitney(frame, "trust_score")
    assert result.u_statistic is None
    assert "Not enough data" in (result.message or "")


@pytest.mark.unit
def test_group_summary_returns_zero_counts_for_missing_group():
    frame = pd.DataFrame(
        {
            "worker_type": ["remote"],
            "trust_score": [0.5],
            "criticism_score": [0.3],
        }
    )
    summary = _group_summary(frame, "in_person")
    assert summary.n == 0


@pytest.mark.unit
def test_interpret_trust_describes_direction_and_significance():
    result = _interpret_trust(
        MannWhitneyResult(u_statistic=1.0, p_value=0.04, rank_biserial=-0.35)
    )
    assert result is not None
    assert "significantly lower trust" in result


@pytest.mark.functional
def test_analyze_submissions_empty_returns_placeholder_interpretation():
    result = analyze_submissions([])
    assert result.submissions == []
    assert result.interpretation == ["No submissions have been scored yet."]
    assert result.summary["remote"].n == 0
    assert result.summary["in_person"].n == 0


@pytest.mark.functional
def test_analyze_submissions_computes_summary_and_tests(sample_scored_submissions):
    result = analyze_submissions(sample_scored_submissions)

    assert result.summary["remote"].n == 3
    assert result.summary["in_person"].n == 3
    assert result.tests["trust"].mann_whitney.u_statistic is not None
    assert result.plot_data["trust"].remote == pytest.approx(
        [0.35, 0.55, 0.82], rel=1e-3
    )
    assert any("Sample size is limited" in line for line in result.interpretation)


@pytest.mark.functional
def test_analyze_submissions_single_group_skips_mann_whitney_stats():
    submissions = [
        ScoredSubmission(
            manager_id="m1",
            worker_type="remote",
            text_type="performance_review",
            raw_text="text",
            trust_score=0.5,
            criticism_score=0.5,
        ),
        ScoredSubmission(
            manager_id="m2",
            worker_type="remote",
            text_type="performance_review",
            raw_text="text",
            trust_score=0.6,
            criticism_score=0.4,
        ),
    ]
    result = analyze_submissions(submissions)
    assert result.tests["trust"].mann_whitney.message is not None
    assert result.tests["trust"].logistic.message is not None or (
        result.tests["trust"].logistic.p_value is not None
    )

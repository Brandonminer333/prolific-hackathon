import math

import pandas as pd
import statsmodels.api as sm
from scipy.stats import mannwhitneyu

from src.models import (
    GroupSummary,
    LogisticResult,
    MannWhitneyResult,
    PlotData,
    ResultsResponse,
    ScoreTests,
    ScoredSubmission,
)

WORKER_TYPES = ("remote", "in_person")
SCORE_COLUMNS = ("trust_score", "criticism_score")


def _effect_size_label(abs_r: float) -> str:
    if abs_r < 0.1:
        return "negligible"
    if abs_r < 0.3:
        return "small"
    if abs_r < 0.5:
        return "medium"
    return "large"


def _group_summary(df: pd.DataFrame, worker_type: str) -> GroupSummary:
    group = df[df["worker_type"] == worker_type]
    if group.empty:
        return GroupSummary(n=0)

    return GroupSummary(
        n=len(group),
        mean_trust=float(group["trust_score"].mean()),
        mean_criticism=float(group["criticism_score"].mean()),
        median_trust=float(group["trust_score"].median()),
        median_criticism=float(group["criticism_score"].median()),
        std_trust=float(group["trust_score"].std(ddof=0)) if len(group) > 1 else 0.0,
        std_criticism=float(group["criticism_score"].std(ddof=0)) if len(group) > 1 else 0.0,
    )


def _mann_whitney(df: pd.DataFrame, score_column: str) -> MannWhitneyResult:
    remote = df.loc[df["worker_type"] == "remote", score_column].dropna()
    in_person = df.loc[df["worker_type"] == "in_person", score_column].dropna()

    if len(remote) < 2 or len(in_person) < 2:
        return MannWhitneyResult(
            message="Not enough data in one or both groups for Mann-Whitney U test (need at least 2 per group)."
        )

    u_stat, p_value = mannwhitneyu(remote, in_person, alternative="two-sided")
    rank_biserial = 1 - (2 * u_stat) / (len(remote) * len(in_person))

    return MannWhitneyResult(
        u_statistic=float(u_stat),
        p_value=float(p_value),
        rank_biserial=float(rank_biserial),
    )


def _logistic_regression(df: pd.DataFrame, score_column: str) -> LogisticResult:
    if df.empty:
        return LogisticResult(message="No data available for logistic regression.")

    median = float(df[score_column].median())
    outcome = (df[score_column] > median).astype(int)
    if outcome.nunique() < 2:
        return LogisticResult(
            message="Outcome is constant (all scores on one side of the median); logistic regression skipped."
        )

    predictor = (df["worker_type"] == "remote").astype(int)
    design = sm.add_constant(predictor)

    try:
        model = sm.Logit(outcome, design).fit(disp=0)
        coef = float(model.params.iloc[1])
        intercept = float(model.params.iloc[0])
        p_value = float(model.pvalues.iloc[1])
        odds_ratio = float(math.exp(coef))
        return LogisticResult(
            coefficient=coef,
            intercept=intercept,
            p_value=p_value,
            odds_ratio=odds_ratio,
        )
    except Exception as exc:
        return LogisticResult(message=f"Logistic regression failed: {exc}")


def _interpret_trust(mw: MannWhitneyResult) -> str | None:
    if mw.p_value is None or mw.rank_biserial is None:
        return None

    direction = "lower" if mw.rank_biserial < 0 else "higher"
    significance = "significantly" if mw.p_value < 0.05 else "not significantly"
    effect = _effect_size_label(abs(mw.rank_biserial))
    return (
        f"Remote workers received {significance} {direction} trust scores than in-person workers "
        f"(p={mw.p_value:.3f}, {effect} effect)."
    )


def _interpret_criticism(mw: MannWhitneyResult) -> str | None:
    if mw.p_value is None or mw.rank_biserial is None:
        return None

    direction = "higher" if mw.rank_biserial > 0 else "lower"
    significance = "significantly" if mw.p_value < 0.05 else "not significantly"
    effect = _effect_size_label(abs(mw.rank_biserial))
    return (
        f"Remote workers received {significance} {direction} criticism than in-person workers "
        f"(p={mw.p_value:.3f}, {effect} effect). Higher criticism means harsher language."
    )


def _interpret_logistic(lr: LogisticResult, score_label: str) -> str | None:
    if lr.p_value is None or lr.odds_ratio is None:
        return None

    if lr.p_value >= 0.05:
        return (
            f"Logistic regression for {score_label} (above median) did not show a significant "
            f"association with worker type (p={lr.p_value:.3f})."
        )

    if lr.odds_ratio > 1:
        return (
            f"Remote worker type is associated with higher odds of above-median {score_label} "
            f"(odds ratio={lr.odds_ratio:.2f}, p={lr.p_value:.3f})."
        )

    return (
        f"Remote worker type is associated with lower odds of above-median {score_label} "
        f"(odds ratio={lr.odds_ratio:.2f}, p={lr.p_value:.3f})."
    )


def _build_interpretation(
    df: pd.DataFrame,
    trust_tests: ScoreTests,
    criticism_tests: ScoreTests,
) -> list[str]:
    messages: list[str] = []

    trust_line = _interpret_trust(trust_tests.mann_whitney)
    if trust_line:
        messages.append(trust_line)

    criticism_line = _interpret_criticism(criticism_tests.mann_whitney)
    if criticism_line:
        messages.append(criticism_line)

    trust_lr = _interpret_logistic(trust_tests.logistic, "trust")
    if trust_lr:
        messages.append(trust_lr)

    criticism_lr = _interpret_logistic(criticism_tests.logistic, "criticism")
    if criticism_lr:
        messages.append(criticism_lr)

    total_n = len(df)
    if total_n < 20:
        messages.append(
            f"Sample size is limited (n={total_n}). Treat these results as directional, not conclusive."
        )

    for worker_type in WORKER_TYPES:
        group_n = int((df["worker_type"] == worker_type).sum())
        if 0 < group_n < 5:
            messages.append(
                f"The {worker_type.replace('_', '-')} group has only {group_n} submissions; "
                "group comparisons may be unstable."
            )

    if not messages:
        messages.append("Not enough data to produce statistical interpretations yet.")

    return messages


def analyze_submissions(submissions: list[ScoredSubmission]) -> ResultsResponse:
    if not submissions:
        empty_summary = {worker_type: GroupSummary(n=0) for worker_type in WORKER_TYPES}
        empty_tests = ScoreTests(
            mann_whitney=MannWhitneyResult(message="No data available."),
            logistic=LogisticResult(message="No data available."),
        )
        empty_plot = PlotData(remote=[], in_person=[])
        return ResultsResponse(
            submissions=[],
            summary=empty_summary,
            tests={"trust": empty_tests, "criticism": empty_tests},
            plot_data={"trust": empty_plot, "criticism": empty_plot},
            interpretation=["No submissions have been scored yet."],
        )

    records = [submission.model_dump() for submission in submissions]
    df = pd.DataFrame(records)

    summary = {worker_type: _group_summary(df, worker_type) for worker_type in WORKER_TYPES}

    trust_mw = _mann_whitney(df, "trust_score")
    criticism_mw = _mann_whitney(df, "criticism_score")
    trust_lr = _logistic_regression(df, "trust_score")
    criticism_lr = _logistic_regression(df, "criticism_score")

    trust_tests = ScoreTests(mann_whitney=trust_mw, logistic=trust_lr)
    criticism_tests = ScoreTests(mann_whitney=criticism_mw, logistic=criticism_lr)

    plot_data = {
        "trust": PlotData(
            remote=df.loc[df["worker_type"] == "remote", "trust_score"].tolist(),
            in_person=df.loc[df["worker_type"] == "in_person", "trust_score"].tolist(),
        ),
        "criticism": PlotData(
            remote=df.loc[df["worker_type"] == "remote", "criticism_score"].tolist(),
            in_person=df.loc[df["worker_type"] == "in_person", "criticism_score"].tolist(),
        ),
    }

    interpretation = _build_interpretation(df, trust_tests, criticism_tests)

    return ResultsResponse(
        submissions=submissions,
        summary=summary,
        tests={"trust": trust_tests, "criticism": criticism_tests},
        plot_data=plot_data,
        interpretation=interpretation,
    )

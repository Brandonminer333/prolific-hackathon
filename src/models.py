from typing import Literal

from pydantic import BaseModel, Field, field_validator


WorkerType = Literal["remote", "in_person"]


class SubmissionInput(BaseModel):
    manager_id: str
    worker_type: WorkerType
    text_type: str
    raw_text: str


class GeminiScores(BaseModel):
    trust_score: int = Field(ge=0, le=100)
    criticism_score: int = Field(ge=0, le=100)


class ScoredSubmission(SubmissionInput):
    trust_score: float = Field(ge=0.0, le=1.0)
    criticism_score: float = Field(ge=0.0, le=1.0)


class SubmitRequest(BaseModel):
    submissions: list[SubmissionInput]

    @field_validator("submissions")
    @classmethod
    def require_at_least_one(cls, value: list[SubmissionInput]) -> list[SubmissionInput]:
        if not value:
            raise ValueError("At least one submission is required")
        return value


class FailedSubmission(BaseModel):
    row_index: int
    reason: str


class SubmitResponse(BaseModel):
    scored: list[ScoredSubmission]
    failed: list[FailedSubmission]


class GroupSummary(BaseModel):
    n: int
    mean_trust: float | None = None
    mean_criticism: float | None = None
    median_trust: float | None = None
    median_criticism: float | None = None
    std_trust: float | None = None
    std_criticism: float | None = None


class MannWhitneyResult(BaseModel):
    u_statistic: float | None = None
    p_value: float | None = None
    rank_biserial: float | None = None
    message: str | None = None


class LogisticResult(BaseModel):
    coefficient: float | None = None
    intercept: float | None = None
    p_value: float | None = None
    odds_ratio: float | None = None
    message: str | None = None


class ScoreTests(BaseModel):
    mann_whitney: MannWhitneyResult
    logistic: LogisticResult


class PlotData(BaseModel):
    remote: list[float]
    in_person: list[float]


class ResultsResponse(BaseModel):
    submissions: list[ScoredSubmission]
    summary: dict[str, GroupSummary]
    tests: dict[str, ScoreTests]
    plot_data: dict[str, PlotData]
    interpretation: list[str]

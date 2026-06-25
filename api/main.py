import logging
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.analysis import analyze_submissions
from src.models import FailedSubmission, ResultsResponse, ScoredSubmission, SubmitRequest, SubmitResponse
from src.scoring import score_submissions_batch

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SUBMISSIONS_CSV = DATA_DIR / "submissions.csv"

CSV_COLUMNS = [
    "manager_id",
    "worker_type",
    "text_type",
    "raw_text",
    "trust_score",
    "criticism_score",
]

app = FastAPI(title="Prolific Bias Audit API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "*",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_submissions() -> list[ScoredSubmission]:
    if not SUBMISSIONS_CSV.exists():
        return []

    df = pd.read_csv(SUBMISSIONS_CSV)
    if df.empty:
        return []

    submissions: list[ScoredSubmission] = []
    for _, row in df.iterrows():
        submissions.append(ScoredSubmission.model_validate(row.to_dict()))
    return submissions


def _append_submissions(scored: list[ScoredSubmission]) -> None:
    if not scored:
        return

    _ensure_data_dir()
    frame = pd.DataFrame([submission.model_dump() for submission in scored])
    frame = frame[CSV_COLUMNS]
    write_header = not SUBMISSIONS_CSV.exists()
    frame.to_csv(SUBMISSIONS_CSV, mode="a", header=write_header, index=False)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/submit", response_model=SubmitResponse)
def submit(request: SubmitRequest) -> SubmitResponse:
    scored, batch_failed = score_submissions_batch(request.submissions)
    failed = [
        FailedSubmission(row_index=index, reason=reason)
        for index, reason in batch_failed
    ]

    _append_submissions(scored)
    logger.info("Scored %s submissions; %s failed", len(scored), len(failed))

    return SubmitResponse(scored=scored, failed=failed)


@app.get("/results", response_model=ResultsResponse)
def results() -> ResultsResponse:
    submissions = _load_submissions()
    return analyze_submissions(submissions)

# Work Location Bias Among Mangers

The purpose of this product is to be a method for HR or bosses to assess that remote and in-person workers are treated equally.

To this end, this products utilizes AI (Gemini 2.5 Flash) to assess managers' emails, perfomance reviews, etc. All documentation composed my managers about an employee.

## How to run locally

```bash
cd prolific-hackathon
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Set GEMINI_API_KEY (and PROLIFIC_API_KEY for demo script) in .env
uvicorn api.main:app --reload
```

## Tests

Use the project virtualenv so pytest picks up `pytest.ini` and the local `tests/` package:

```bash
source .venv/bin/activate
pip install -r requirements.txt

# Unit + functional (also run by pre-commit)
pytest -m "unit or functional"

# Integration (API via TestClient)
pytest -m integration
```

Do not paste inline shell comments on the same line as commands (e.g. `pytest ... # comment`);
zsh will treat `#` as an argument and pytest will fail.

### Pre-commit

Initialize git once, then install hooks:

```bash
git init
pre-commit install
```

Pre-commit requires a git repository. It runs unit and functional tests before each commit.

## Limitations / Points to Consider

1. Focussing exclusively onemployees who are 100% remote or 100% in-person.
2. The nature of the scenereo is that we'll have a small sample size. Most managers have less than 10 employees under them. This attributes to only 10 performance reviews.
3. We are going to ignroe the fact that there will probably be more communication with remote workers due to the fact that they cannot be talked to in-person.

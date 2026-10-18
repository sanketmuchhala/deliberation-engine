# Deliberation Engine

A proposer / critic / summarizer loop that deliberates on a question over multiple rounds.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
cp config.example.json config.json
```

## Run

```bash
python -m src.main "Your question here"
```

Outputs are written to `outputs/`.

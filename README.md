# The Deliberation Engine

A multi-agent deliberation system that turns a vague stakeholder feature request into an audited, scope-bounded decision document. It is modeled on a Government CRM used across ~100 member countries, where ministry contacts and engagement history are diplomatically sensitive.

## Core idea

Multi-agent LLM loops tend to fail in one of two opposite ways: **sycophantic collapse**, where the agents agree on vague terms almost at once, or **unbounded drift**, where they argue without end or the final summary contradicts what was decided.

This engine keeps a hard boundary between the two kinds of work:

1. **The models supply** proposals, critiques, and explanatory prose.
2. **Python owns** the issue ledger, the stopping rules, the dependency links, and the structure of the decision document.

The Summarizer cannot drop an escalated risk, invent agreed scope, or skip a human decision. Python builds every list in the document from the ledger; the Summarizer only writes the prose.

## Architecture

```text
Feature request
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│            PYTHON ORCHESTRATOR & ISSUE LEDGER            │
│  • Validates unique IDs and cross-references (one retry) │
│  • Fingerprints accepted proposals across rounds         │
│  • Never stops in round 1; deterministic stopping gate   │
└───────────┬──────────────────────────────────┬───────────┘
            │                                  │
            ▼ round N proposal                 ▼ round N challenges
   ┌─────────────────┐                ┌─────────────────┐
   │     PROPOSER    │   structured   │      CRITIC     │
   │  shippability,  │ ◄────────────► │ confidentiality,│
   │schema simplicity│   issue moves  │ least privilege,│
   │  cost vs. risk  │                │ turnover, alerts│
   └────────┬────────┘                └─────────────────┘
            │
            ▼ all issues settled or escalated, or round limit reached
┌──────────────────────────────────────────────────────────┐
│            DECISION DOCUMENT BUILDER (Python)            │
│  • Resolves criterion → scope item → assumption → issue  │
│  • Splits agreed items from pending human decisions      │
│  • Merges the Summarizer's prose; logs any mismatch      │
└──────────────────────────────────────────────────────────┘
   │
   ▼
decision_doc.md + sample_trace.json
```

## Key guarantees

- **Opposing incentives (`prompts/`):** The Proposer optimizes for shippability, schema simplicity, and no extra data entry for Regional Coordinators. The Critic reviews for diplomatic confidentiality, least privilege, staff turnover, and alert fatigue. The Proposer weighs each objection with a cost-versus-residual-risk rubric rather than a defense quota.
- **Deterministic stopping (`src/engine.py`):** Python moves each issue through `CHALLENGED` → `DEFENDED` / `REVISED` / `CONCEDED` → `ACCEPTED` / `ESCALATED_TO_HUMAN` and computes a disagreement score every round. It never stops in round 1 and stops once every issue is settled. From round 3 it escalates an issue as deadlocked only when the Critic re-challenges an answer the Proposer gave that same round. At `--max-rounds` it escalates whatever is still open, labeling one-sided issues (never answered, or answered but never reviewed) separately from real stalemates.
- **Dependency chain:** `success criterion → scope item → assumption → escalated issue`. Scope items (`S1..Sn`) are tagged with the assumptions they rely on, and each success criterion links to the scope items it measures. When an issue is escalated, every scope item tagged with its assumption, and every criterion measuring those items, moves to a **Pending Human Decision** list.
- **Acceptance fingerprints:** An acceptance is bound to a normalized fingerprint of the targeted assumption, the scope items tagged with it, and the criteria measuring them. If the Proposer later changes any of these, the issue reopens for the Critic.
- **Turn validation with one corrective retry:** Every turn is checked for unique IDs and for references that point at real assumptions and scope items. A failing turn gets one retry that names the bad IDs; if it still fails, the run stops with an error. A challenge counts at most once per issue per round.
- **Python-built document:** The Summarizer returns only the executive summary, assumption notes, and question wording. Any mismatch with the ledger is logged in the trace as `summary_corrections`.

The reasoning behind these choices, and what I would change next, is in [DECISIONS.md](DECISIONS.md).

## Quick start

### 1. Install (Python 3.9+)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then put your OpenRouter key in LLM_API_KEY
```

`.env.example` points `LLM_BASE_URL` at OpenRouter and sets `PROPOSER_MODEL`, `CRITIC_MODEL`, and `SUMMARIZER_MODEL` to `anthropic/claude-sonnet-5.5`. Any OpenAI-compatible endpoint works, as long as its models support structured outputs (JSON schema).

### 2. Run

```bash
python3 -m src.main                                      # runs official example 1
python3 -m src.main --request "The CRM should alert us when our relationship with a country goes cold."
python3 -m src.main --config config.example.json         # reads "feature_request" from the JSON file
python3 -m src.main --request "..." --max-rounds 5       # default 4, minimum 2
python3 -m src.main --request "..." --output-dir runs/   # default outputs/
```

Each round prints a Proposer panel and a Critic panel with the disagreement score and gate status. The run ends by printing the decision document and writing `decision_doc.md` and `sample_trace.json` to the output directory.

### 3. Test

```bash
python3 -m unittest discover -s tests
```

Eighteen offline tests drive the engine with scripted Proposer and Critic turns, so no API key is needed. They cover convergence, deadlock and the round-3 reply window, terminal-state locking, fingerprint reopening, the dependency chain, duplicate and dangling IDs with the corrective retry, single counting per round, concession handling, the max-rounds labels, and a deliberately wrong Summarizer draft that cannot change any ledger fact.

## Golden runs (`outputs/`)

| Files | Request | Rounds | Disagreement score | Defended in round 2 | Escalated to humans | Pending a human decision |
|---|---|---|---|---|---|---|
| `example1_right_contact_*` | Track who is the right person to contact in each country | 2 | 0.87 → 0.0 | 0 of 5 | C5 | 3 of 6 scope items, 8 of 9 criteria |
| `example2_country_history_*` | Project managers see full engagement history before a new mission | 2 | 0.89 → 0.0 | 0 of 5 | none | none |
| `example3_relationship_cold_*` | Alert when a relationship with a country goes cold | 3 | 0.88 → 0.07 → 0.0 | 1 of 6 | none | none |

All three ended with `CONVERGENCE_ALL_ISSUES_RESOLVED_OR_ESCALATED (CRITIC_SIGNALED_CONVERGENCE)`. No turn failed ID validation, and the Summarizer's draft needed no corrections (`summary_corrections` is empty). Each example has a `_trace.json` (every round plus ledger snapshots), a `_decision.md` (the final document), and a `_console.log` (the console output). `sample_trace.json` and `decision_doc.md` are copies of example 3, which shows the round-1 lock, a continue round, a defense the Critic accepted, a re-challenge resolved by a round-3 revision, and the reopen guard firing live: a new round-3 success criterion touched scope behind three accepted issues (`C2`, `C4`, `C6`), and the Critic re-reviewed and accepted them in the same round. Example 1 shows escalation: `C5` challenges the definition of the "right person", so the card, the ranking, and the fallback states that rely on it, plus 8 of the 9 criteria that measure them, wait on a human decision. Runs vary (the previous golden set, commit `9768ec2`, took 2 rounds each). Deadlock and the max-rounds labels did not occur in these runs; the offline tests cover them. All runs used `anthropic/claude-sonnet-5.5` for all three agents.

## Layout

```text
DECISIONS.md          design reasoning: prompts, termination, trade-offs
config.example.json   example input for --config
.env.example          endpoint and model settings (copy to .env)
prompts/              proposer.md, critic.md, summarizer.md
src/                  schemas.py (Pydantic contracts), engine.py (ledger, gate, validation, document builder), main.py (CLI)
tests/                test_engine.py (18 offline state-machine tests)
outputs/              golden runs: example1_*, example2_*, example3_*, plus sample_trace.json and decision_doc.md
```

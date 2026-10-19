# Architectural & Design Decisions (`DECISIONS.md`)

## 1. Agent Prompt Design, Asymmetric Incentives, and Iteration

### Core Design Philosophy: Structural Asymmetry Over Roleplay
Multi-agent LLM loops tend to collapse into premature consensus: instruction-tuned models are trained to be agreeable, and telling agents to "debate thoroughly" rarely helps.

For the Government CRM (~100 member countries, high diplomatic sensitivity), I designed the prompts around **asymmetric optimization functions** and an explicit **authority boundary**:
> *Agents decide product-design proposals; humans decide diplomatic policy, clearance authority, and institutional classification.*

- **The Proposer (`prompts/proposer.md`)** optimizes for **MVP shippability, schema simplicity, and zero field-user friction**, guarding a *Complexity Budget*.
- **The Critic (`prompts/critic.md`)** optimizes for **diplomatic confidentiality, least privilege, turnover resilience, and false-positive suppression**. Every challenge (`C1..Cn`) must target an assumption (`A1..An`) with a concrete operational failure mode.
- **The Summarizer (`prompts/summarizer.md`)** writes prose only; Python owns every fact in the document (Section 2).

### Empirical Prompt & Model Iteration
1. **Model capability floor:** On `gpt-4o-mini`, Example 1 produced shallow UI complaints, repeated Round 1 challenges verbatim in Round 3, and deadlocked all 3 issues into non-policy escalations. Claude Sonnet surfaced real domain risks such as cross-country confidentiality leaks and stale ministry roles.
2. **Calibrating Proposer pushback (v1 → v2 → v3):**
   - **v1**, qualitative anti-sycophancy rules: **1 of 5** challenges defended, 2 rounds.
   - **v2** (commit `bc97c22`) required at least 2 `DEFENDED` moves. All three examples ran 3 rounds, but the model treated the floor as an exact quota (2 of 4, 2 of 5, 2 of 5), not as judgment.
   - **v3** (current) has no quota. The Proposer classifies the cost of each requested fix (*cheap*: a rule over existing data or one auto-filled column; *expensive*: a new table, a screen or queue someone must watch, a per-country setting, an approval step, a model) and weighs it against the residual risk. It revises cheap fixes and defends expensive ones only when it can name the bound on the risk. A first v3 draft let "several small columns plus a monitoring view" pass as cheap until I tightened the classes.

   With v3, runs are shorter (2, 2, 3 rounds) and `DEFENDED` is rare (0 of 4, 1 of 5, 1 of 5), but pushback moved inside the responses rather than disappearing. In Example 3, `C1` is labeled `REVISED` but says "I am DEFENDING the single global threshold" because per-country thresholds are a setting someone must maintain. `C2` is defended with four explicit risk bounds; the Critic accepted the false-positive argument and re-challenged only the false-negative gap, which the Proposer then revised in Round 3.

---

## 2. Termination Design, State Math, and Alternatives Considered

### Deterministic Ledger State Machine
Python owns an explicit `IssueLedgerEntry` state machine. Each challenge moves through six states on a uniform **0.25 step-down weight** $w(s)$: `CHALLENGED` (1.00); the Proposer's `DEFENDED` (0.75), `REVISED` (0.50), or `CONCEDED` (0.25); and the terminal `ACCEPTED` or `ESCALATED_TO_HUMAN` (0.00). At the end of round $r$ the engine computes a **Disagreement Score** modulated by Proposer and Critic confidence ($p_{i,r}, c_{i,r} \in [0, 1]$):

$$D_r = \frac{1}{N} \sum_{i=1}^{N} w(s_{i,r}) \cdot (0.50 + 0.25 p_{i,r} + 0.25 c_{i,r})$$

Bounding the multiplier to $[0.50, 1.00]$ means low confidence never masks an open challenge; $D_r = 0.0$ if and only if every issue is terminal.

### Stopping Gate & Ledger Guarantees
Verified by 13 scripted scenarios (`tests/test_engine.py`, no API calls):
1. **Round 1 minimum lock (`ROUND_1_MINIMUM_LOCK`):** Termination is blocked in Round 1; later non-terminating rounds log `CONTINUE`.
2. **Terminal locking, bound to assumption text:** Neither agent can reopen an `ACCEPTED` or `ESCALATED_TO_HUMAN` issue, and an unchallenged concession closes automatically. An acceptance is bound to the text of the assumption it targets: if the Proposer later changes or drops that assumption, the engine reopens the issue for the Critic to re-judge. No accepted assumption was reworded in any of the 12 live runs I traced, so the guard added no rounds.
3. **Convergence (`CRITIC_SIGNALED_CONVERGENCE` vs. `ALL_ISSUES_TERMINAL_GATE_CLOSE`):** The engine stops when every issue is terminal; a hallucinated `ready_to_conclude=False` cannot trap a settled loop.
4. **Deadlock & round-3 response window:** From Round 3, an issue is deadlocked only when, in the same round, the Proposer answered it and the Critic explicitly re-challenged that answer. A new Round-3 challenge, an issue the Proposer skipped, or an answer the Critic did not rule on gets another round instead of a punitive escalation. At `max_rounds`, such one-sided issues are labeled `UNANSWERED_AT_ROUND_LIMIT` or `UNREVIEWED_AT_ROUND_LIMIT`, separate from a true `MAX_ROUNDS_STILL_CONTESTED` stalemate.
5. **Python-built decision document:** The Summarizer returns only an executive summary, assumption notes, and question wording. Python builds everything else from the ledger and the Proposer's final turn: scope, success criteria, dispositions, exactly one open question per escalated issue, and the metrics. Each in-scope item is tagged with the assumptions it relies on; an item tied to an escalated issue moves to **Pending Human Decision** (4 of 8 items in Example 2, 3 of 9 in Example 3). Mismatches are logged as `summary_corrections`; there were none in the golden runs.

### Alternatives Considered
- **Fixed `max_rounds` only:** Wastes tokens on simple requests and passes off exhaustion as consensus on hard ones.
- **An LLM "judge" boolean:** Vulnerable to sycophancy, and gives no audit trail when an issue is silently dropped.
- **LLM-computed disagreement floats:** Uncalibrated across rounds; tying the score to discrete state transitions keeps the trajectory (`0.88 -> 0.12 -> 0.0`) auditable.

---

## 3. What I Would Do Differently With More Time

**Record pushback per sub-demand, not per challenge.**
Under v3 the Proposer usually takes the cheap part of a challenge and refuses the expensive part in the same answer, but one move per issue records that as `REVISED`. The ledger therefore undercounts real disagreement, and the Critic is never made to rule on the refused part. I would let a response split a challenge into parts with their own moves, so each refused demand becomes an open `DEFENDED` item the Critic must accept, re-challenge, or escalate.

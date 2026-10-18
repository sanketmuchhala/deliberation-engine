# Architectural & Design Decisions (`DECISIONS.md`)

## 1. Agent Prompt Design, Asymmetric Incentives, and Iteration

### Core Design Philosophy: Structural Asymmetry Over Roleplay
Multi-agent LLM loops frequently collapse into premature consensus because instruction-tuned models are trained to be agreeable. Telling two agents to "debate thoroughly" in prose rarely prevents the Proposer from capitulating to every Critic objection in Round 2.

To produce genuine deliberation for the Government CRM (~100 member countries, ministry contacts, mission history, and high diplomatic sensitivity), I designed the prompts around **asymmetric optimization functions** and an explicit **authority boundary**:
> *Agents decide product-design proposals; humans decide diplomatic policy, clearance authority, and institutional classification.*

- **The Proposer (`prompts/proposer.md`)** optimizes for **MVP shippability, schema simplicity, and zero field-user friction**. It guards a strict *Complexity Budget*: deterministic rules over existing CRM tables instead of new ML models, manual coordinator workflows, or bespoke role-graph tables.
- **The Critic (`prompts/critic.md`)** optimizes for **diplomatic confidentiality (least-privilege access), cross-ministry turnover resilience, and false-positive suppression**. Every challenge (`C1..Cn`) must target a specific assumption (`A1..An`) with a concrete operational failure mode rather than generic UX commentary.
- **The Summarizer (`prompts/summarizer.md`)** acts strictly as a **state serializer**, mapping the final ledger into `FinalDecisionDocument` without reopening settled issues.

### Empirical Prompt & Model Iteration
Testing exposed two concrete failure modes that drove our prompt and model revisions:

1. **Model Capability Floor (`gpt-4o-mini` vs. `Claude Sonnet`):**
   Running Example 1 on `gpt-4o-mini` across all three roles produced shallow UI complaints ("is not intuitive"), repeated Round 1 challenge text verbatim in Round 3, and deadlocked all 3 issues (`0.90 -> 0.44 -> 0.0`) into non-policy human escalations. The same input on Claude Sonnet surfaced domain-specific risks: cross-country confidentiality leaks, stale ministry role assignments on turnover, and countries left without an owner when coordinators change.
2. **Calibrating Proposer Pushback (v1 vs. v2 Prompts):**
   In our v1 Sonnet run on Example 1, qualitative anti-sycophancy rules ("Agreeing with the Critic is not the goal") yielded weak pushback: the Proposer defended only **1 of 5** challenges (defending a fixed 180-day staleness threshold against tunable per-country settings) and revised the other 4 immediately, terminating in 2 rounds (`0.875 -> 0.0`).
   In commit `bc97c22`, we tightened `proposer.md` to require defending at least 2 challenges where the Critic requests extra schema attributes, configuration UIs, or manual coordinator upkeep, and updated `critic.md` to scrutinize `DEFENDED` responses before accepting them. On Example 1 this pushed deliberation from 2 rounds to **3 rounds**, and all three official examples ran 3 rounds (`0.88 -> 0.10/0.12 -> 0.0`) with substantive pushback—for example, rejecting per-tier alert thresholds in Example 3 because a country-tier attribute needs someone to maintain it plus a configuration UI.

---

## 2. Termination Design, State Math, and Alternatives Considered

### Deterministic Ledger State Machine
Rather than allowing the LLM to manage state in free text, Python owns an explicit `IssueLedgerEntry` state machine (`src/schemas.py`, `src/engine.py`). Each Critic challenge moves through six states on a uniform **0.25 ordinal step-down weight** $w(s)$: `CHALLENGED` (1.00); the Proposer's `DEFENDED` (0.75), `REVISED` (0.50), or `CONCEDED` (0.25); and the terminal `ACCEPTED` or `ESCALATED_TO_HUMAN` (0.00), meaning resolved or handed to humans as a policy question.

At the end of round $r$, the engine computes an aggregate **Disagreement Score** $D_r \in [0.0, 1.0]$ modulated by Proposer and Critic confidence ($p_{i,r}, c_{i,r} \in [0, 1]$):

$$D_r = \frac{1}{N} \sum_{i=1}^{N} w(s_{i,r}) \cdot (0.50 + 0.25 p_{i,r} + 0.25 c_{i,r})$$

Bounding the confidence multiplier to $[0.50, 1.00]$ guarantees that low agent confidence never masks an unresolved challenge; $D_r$ reaches $0.0$ if and only if every issue reaches a terminal state (`ACCEPTED` or `ESCALATED_TO_HUMAN`).

### Four-Tier Stopping Gate & Scripted Verification
Commit `aba4f6d` was verified against 8 scripted edge-case scenarios (`tests/test_engine.py`, no API calls):
1. **Round 1 Minimum Lock (`ROUND_1_MINIMUM_LOCK`):** Hard-blocks termination in Round 1 (`round_no < 2`) regardless of model flags; non-terminating subsequent rounds explicitly log `CONTINUE`.
2. **Terminal State Immutability & Concession Closure:** Once an issue is `ACCEPTED` or `ESCALATED_TO_HUMAN`, neither agent can reopen it. A `CONCEDED` issue closes automatically unless the Critic re-challenges the concession.
3. **Ledger Convergence & Critic Signal (`CRITIC_SIGNALED_CONVERGENCE` vs. `ALL_ISSUES_TERMINAL_GATE_CLOSE`):** The engine stops when every issue is terminal ($D_r = 0.0$). So that a hallucinated `ready_to_conclude=False` cannot trap a settled loop, the flag only records whether the Critic signaled convergence (Examples 1 and 2) or the ledger gate closed it.
4. **Deadlock Escalation (`DEADLOCK_ESCALATED_TO_HUMAN`) & `max_rounds` Failsafe:** In Round $\ge 3$, any issue still open after the Critic has challenged it in two or more rounds is escalated to `ESCALATED_TO_HUMAN` and routed to **Open Questions for Humans** with both positions preserved (`C2` in Example 3); at `max_rounds`, anything still open is escalated the same way. The engine also overwrites the Summarizer's score, confidence, and termination fields from Python state so they cannot drift from the ledger.

### Alternatives Considered
- **Fixed `max_rounds` only:** Wastes tokens on simple requests and masquerades exhaustion as consensus on hard requests.
- **Unstructured LLM "Judge" boolean:** Vulnerable to premature sycophancy and offers zero auditability when an issue is silently dropped between turns.
- **LLM-computed disagreement floats:** Uncalibrated across rounds; anchoring the score to discrete state transitions in Python makes the trajectory (`0.88 -> 0.12 -> 0.0`) auditable.

---

## 3. What I Would Do Differently With More Time

**Replace the Hard Defense Floor with a Structured Complexity-Cost Rubric.**
The "defend at least 2" floor stopped Round-2 capitulation, but our golden traces showed the model treating it as an exact quota: it defended exactly 2 challenges in every example (2 of 4, 2 of 5, 2 of 5). With more time, I would replace the numeric floor with a deterministic **Complexity Impact Tag** (`ZERO_SCHEMA_CHANGE`, `NEW_COLUMN_OR_VIEW`, `NEW_TABLE_OR_UI_WORKFLOW`) on each Critic suggestion, instructing the Proposer to `DEFEND` any `NEW_TABLE_OR_UI_WORKFLOW` demand and judge the rest case by case.

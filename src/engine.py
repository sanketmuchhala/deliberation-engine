from __future__ import annotations
import hashlib
import os
import re
from pathlib import Path
from statistics import fmean
from openai import OpenAI
from src.schemas import (
    ChallengeState,
    CriticTurn,
    FinalDecisionDocument,
    IssueLedgerEntry,
    OpenQuestion,
    PendingItem,
    ProposerTurn,
    STATE_WEIGHT,
    SummarizerDraft,
    SurfacedAssumptionSummary,
    TERMINAL_STATES,
)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def compute_disagreement(ledger: dict[str, IssueLedgerEntry]) -> float:
    if not ledger:
        return 1.0
    scores = [
        STATE_WEIGHT[item.current_state]
        * (0.50 + 0.25 * item.proposer_confidence + 0.25 * item.critic_confidence)
        for item in ledger.values()
    ]
    return round(fmean(scores), 4)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(".").casefold()


def proposal_fingerprint(p_turn: ProposerTurn, assumption_id: str) -> str:
    """Hash of what the Critic accepts for an assumption: its statement, every scope item tagged with
    it, and every success criterion that measures one of those items. Whitespace, case, and order
    changes do not alter it."""
    statement = next((a.statement for a in p_turn.assumptions if a.assumption_id == assumption_id), "")
    items = [x for x in p_turn.proposed_scope_in if assumption_id in x.assumption_ids]
    item_ids = {x.scope_id for x in items}
    dependents = sorted(
        [normalize(x.item) for x in items]
        + [normalize(c.criterion) for c in p_turn.success_criteria if item_ids & set(c.scope_item_ids)]
    )
    return hashlib.sha256("\n".join([normalize(statement), *dependents]).encode()).hexdigest()[:16]


def duplicates(ids: list[str]) -> list[str]:
    return sorted({i for i in ids if ids.count(i) > 1})


def proposer_turn_errors(p_turn: ProposerTurn) -> list[str]:
    """Unique IDs, and every reference pointing at something that exists in this turn."""
    errors = []
    for kind, ids in [
        ("assumption IDs", [a.assumption_id for a in p_turn.assumptions]),
        ("scope IDs", [x.scope_id for x in p_turn.proposed_scope_in]),
        ("challenge responses", [r.issue_id for r in p_turn.challenge_responses]),
    ]:
        if duplicates(ids):
            errors.append(f"Duplicate {kind}: {', '.join(duplicates(ids))}; each ID may appear once per turn")
    for kind, text, refs, valid in [
        ("Scope item", x.item, x.assumption_ids, {a.assumption_id for a in p_turn.assumptions})
        for x in p_turn.proposed_scope_in
    ] + [
        ("Success criterion", c.criterion, c.scope_item_ids, {x.scope_id for x in p_turn.proposed_scope_in})
        for c in p_turn.success_criteria
    ]:
        unknown = sorted(set(refs) - valid)
        if not refs or unknown:
            problem = f"references unknown {', '.join(unknown)}" if unknown else "lists no references"
            errors.append(f"{kind} '{text[:60]}' {problem}; valid IDs are {', '.join(sorted(valid))}")
    return errors


def critic_turn_errors(c_turn: CriticTurn, ledger: dict[str, IssueLedgerEntry], valid: set[str]) -> list[str]:
    ids = [ch.issue_id for ch in c_turn.challenges]
    errors = []
    if duplicates(ids):
        errors.append(f"Duplicate issue IDs: {', '.join(duplicates(ids))}; give each issue one entry per turn")
    return errors + [
        f"New issue {ch.issue_id} targets unknown {ch.target_assumption_id}; "
        f"use a Proposer assumption ID ({', '.join(sorted(valid))})"
        for ch in c_turn.challenges
        if ch.issue_id not in ledger and ch.target_assumption_id not in valid
    ]


def split_pending(items: list[tuple[str, list[str]]]) -> tuple[list[str], list[PendingItem]]:
    """Split (text, blocking issue IDs) pairs into agreed text and items pending a human decision."""
    agreed = [text for text, blocked_by in items if not blocked_by]
    pending = [PendingItem(item=text, blocked_by=blocked_by) for text, blocked_by in items if blocked_by]
    return agreed, pending


def assumption_disposition(issues: list[IssueLedgerEntry]) -> str:
    if any(e.current_state == ChallengeState.ESCALATED_TO_HUMAN for e in issues):
        return "ESCALATED_TO_HUMAN"
    if any(e.proposer_last_move == ChallengeState.CONCEDED for e in issues):
        return "CONCEDED_AND_REMOVED"
    if any(e.proposer_last_move == ChallengeState.REVISED for e in issues):
        return "REVISED_AND_ACCEPTED"
    return "ACCEPTED"


def build_decision_skeleton(
    feature_request: str, ledger: dict[str, IssueLedgerEntry], rounds_log: list[dict], termination_reason: str
) -> FinalDecisionDocument:
    """Every fact in the decision document, computed from the ledger and the Proposer's final turn.

    Scope and success criteria come from the Proposer's final structured turn. A scope item that relies
    on an assumption targeted by an escalated issue is held as pending a human decision, and so is
    every success criterion that measures it. The Summarizer later fills in the prose (executive
    summary, notes, question wording) and nothing else.
    """
    final = rounds_log[-1]
    proposer = final["proposer"]
    escalated = [e for e in ledger.values() if e.current_state == ChallengeState.ESCALATED_TO_HUMAN]
    blocking: dict[str, list[str]] = {}
    for e in escalated:
        blocking.setdefault(e.target_assumption_id, []).append(e.issue_id)

    scope_blocked = {
        x["scope_id"]: sorted({i for aid in x["assumption_ids"] for i in blocking.get(aid, [])})
        for x in proposer["proposed_scope_in"]
    }
    included, pending = split_pending(
        [(f"[{x['scope_id']}] {x['item']}", scope_blocked[x["scope_id"]]) for x in proposer["proposed_scope_in"]]
    )
    criteria, pending_criteria = split_pending([
        (
            f"{c['criterion']} (measures {', '.join(c['scope_item_ids'])})",
            sorted({i for sid in c["scope_item_ids"] for i in scope_blocked.get(sid, [])}),
        )
        for c in proposer["success_criteria"]
    ])

    statements: dict[str, str] = {}
    for record in rounds_log:
        for a in record["proposer"]["assumptions"]:
            statements[a["assumption_id"]] = a["statement"]
    assumptions = []
    for aid, statement in statements.items():
        issues = [e for e in ledger.values() if e.target_assumption_id == aid]
        assumptions.append(SurfacedAssumptionSummary(
            assumption_id=aid, assumption=statement, was_challenged=bool(issues),
            final_disposition=assumption_disposition(issues),
            resolution_notes="; ".join(f"{e.issue_id} ended {e.current_state.value}" for e in issues) or "Not challenged.",
        ))

    return FinalDecisionDocument(
        feature_request=feature_request,
        executive_summary="",
        agreed_scope_included=included,
        scope_pending_human_decision=pending,
        agreed_scope_excluded=list(proposer["proposed_scope_out"]),
        success_criteria=criteria,
        success_criteria_pending=pending_criteria,
        surfaced_assumptions=assumptions,
        open_questions_for_humans=[
            OpenQuestion(
                issue_id=e.issue_id,
                decision_owner="Unassigned: product owner to route",
                question=f"Decide how v1 should handle this risk: {e.challenge_text}",
            )
            for e in escalated
        ],
        final_disagreement_score=final["disagreement_score"],
        proposer_confidence=proposer["overall_confidence"],
        critic_confidence=final["critic"]["overall_confidence"],
        termination_reason=termination_reason,
    )


def apply_summarizer_prose(doc: FinalDecisionDocument, draft: SummarizerDraft) -> list[str]:
    """Merge the Summarizer's prose into the Python-built document. Returns every mismatch with the ledger."""
    corrections: list[str] = []
    doc.executive_summary = draft.executive_summary

    notes = {n.assumption_id.strip(): n.resolution_notes for n in draft.assumption_notes}
    known = {a.assumption_id for a in doc.surfaced_assumptions}
    for extra in sorted(set(notes) - known):
        corrections.append(f"{extra}: note dropped (the Proposer never surfaced it)")
    for a in doc.surfaced_assumptions:
        if a.assumption_id in notes:
            a.resolution_notes = notes[a.assumption_id]
        else:
            corrections.append(f"{a.assumption_id}: note missing; engine note kept")

    drafted: dict[str, OpenQuestion] = {}
    for q in draft.open_questions_for_humans:
        q.issue_id = q.issue_id.strip().strip("[]")
        drafted.setdefault(q.issue_id, q)
    escalated_ids = [q.issue_id for q in doc.open_questions_for_humans]
    for extra in sorted(set(drafted) - set(escalated_ids)):
        corrections.append(f"{extra}: open question dropped (issue was not escalated)")
    for i, issue_id in enumerate(escalated_ids):
        if issue_id in drafted:
            doc.open_questions_for_humans[i] = drafted[issue_id]
        else:
            corrections.append(f"{issue_id}: open question missing; engine fallback kept")
    return corrections


class DeliberationEngine:
    def __init__(self, max_rounds: int = 4) -> None:
        self.max_rounds = max(2, max_rounds)
        self.client = OpenAI(
            api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "test-key",
            base_url=os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
            default_headers={
                "HTTP-Referer": "https://github.com/sanketmuchhala/deliberation-engine",
                "X-Title": "The Deliberation Engine",
            },
        )
        self.proposer_model = os.getenv("PROPOSER_MODEL", "gpt-4o-mini")
        self.critic_model = os.getenv("CRITIC_MODEL", "gpt-4o-mini")
        self.summarizer_model = os.getenv("SUMMARIZER_MODEL", "gpt-4o-mini")

    def _call_structured(self, model: str, system_prompt: str, user_content: str, schema: type):
        resp = self.client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            response_format=schema,
            temperature=0.2,
        )
        return resp.choices[0].message.parsed

    def _call_checked(
        self, model: str, system_prompt: str, user_content: str, schema: type, check, rejected: list[str]
    ):
        """Ask again once if a turn has duplicate or dangling IDs; fail loudly if it still does."""
        turn = self._call_structured(model, system_prompt, user_content, schema)
        errors = check(turn)
        if errors:
            rejected.extend(errors)
            feedback = "\n".join(f"- {e}" for e in errors)
            turn = self._call_structured(
                model, system_prompt,
                f"{user_content}\n\nYOUR PREVIOUS OUTPUT WAS REJECTED BY THE ENGINE:\n{feedback}\n"
                "Fix these IDs and answer again.",
                schema,
            )
            errors = check(turn)
            if errors:
                raise ValueError(f"{schema.__name__} still fails validation after one retry: {errors}")
        return turn

    def run(self, feature_request: str, on_round_callback=None) -> tuple[FinalDecisionDocument, dict]:
        proposer_sys = load_prompt("proposer")
        critic_sys = load_prompt("critic")
        summarizer_sys = load_prompt("summarizer")

        ledger: dict[str, IssueLedgerEntry] = {}
        rounds_log: list[dict] = []
        known_assumptions: set[str] = set()

        for round_no in range(1, self.max_rounds + 1):
            proposer_ctx = (
                f"FEATURE REQUEST:\n{feature_request}\n\n"
                f"CURRENT ROUND: {round_no}\n"
                f"ACTIVE ISSUE LEDGER:\n{[v.model_dump() for v in ledger.values()]}\n"
                f"PREVIOUS ROUNDS:\n{rounds_log}"
            )
            rejected: list[str] = []
            p_turn: ProposerTurn = self._call_checked(
                self.proposer_model, proposer_sys, proposer_ctx, ProposerTurn, proposer_turn_errors, rejected
            )
            known_assumptions |= {a.assumption_id for a in p_turn.assumptions}

            for resp in p_turn.challenge_responses:
                entry = ledger.get(resp.issue_id)
                if entry is None or entry.current_state in TERMINAL_STATES:
                    continue
                entry.proposer_last_move = ChallengeState(resp.move)
                entry.current_state = ChallengeState(resp.move)
                entry.proposer_confidence = resp.confidence
                entry.last_proposer_round = round_no
                entry.history.append(f"R{round_no}:Proposer:{resp.move}")

            # An acceptance is bound to what the Critic accepted: the target assumption plus every scope
            # item and success criterion tagged with it. If any of that changes, the issue reopens.
            for entry in ledger.values():
                if (
                    entry.current_state == ChallengeState.ACCEPTED
                    and entry.accepted_fingerprint is not None
                    and proposal_fingerprint(p_turn, entry.target_assumption_id) != entry.accepted_fingerprint
                ):
                    entry.current_state = ChallengeState.REVISED
                    entry.proposer_last_move = ChallengeState.REVISED
                    entry.accepted_fingerprint = None
                    entry.history.append(f"R{round_no}:Gate:REOPENED_PROPOSAL_CHANGED")

            critic_ctx = (
                f"FEATURE REQUEST:\n{feature_request}\n\n"
                f"CURRENT ROUND: {round_no}\n"
                f"PROPOSER OUTPUT THIS ROUND:\n{p_turn.model_dump_json(indent=2)}\n"
                f"CURRENT ISSUE LEDGER:\n{[v.model_dump() for v in ledger.values()]}"
            )
            c_turn: CriticTurn = self._call_checked(
                self.critic_model, critic_sys, critic_ctx, CriticTurn,
                lambda turn: critic_turn_errors(turn, ledger, known_assumptions), rejected,
            )

            for ch in c_turn.challenges:
                if ch.issue_id not in ledger:
                    ledger[ch.issue_id] = IssueLedgerEntry(
                        issue_id=ch.issue_id,
                        target_assumption_id=ch.target_assumption_id,
                        challenge_text=ch.challenge_text,
                        current_state=ChallengeState.CHALLENGED,
                        critic_confidence=ch.confidence,
                        rounds_contested=1,
                        last_critic_challenge_round=round_no,
                        history=[f"R{round_no}:Critic:CHALLENGED"],
                    )
                else:
                    entry = ledger[ch.issue_id]
                    if entry.current_state in TERMINAL_STATES:
                        continue
                    entry.critic_confidence = ch.confidence
                    if round_no == 1:
                        entry.current_state = ChallengeState.CHALLENGED
                    elif ch.status == "ACCEPTED":
                        entry.current_state = ChallengeState.ACCEPTED
                        entry.accepted_fingerprint = proposal_fingerprint(p_turn, entry.target_assumption_id)
                    elif ch.status == "ESCALATED_TO_HUMAN":
                        entry.current_state = ChallengeState.ESCALATED_TO_HUMAN
                        entry.escalation_reason = "POLICY_ESCALATED_BY_CRITIC"
                    else:
                        if entry.last_critic_challenge_round != round_no:  # count each round once
                            entry.rounds_contested += 1
                        entry.last_critic_challenge_round = round_no
                        if entry.proposer_last_move in (ChallengeState.DEFENDED, ChallengeState.REVISED):
                            entry.current_state = entry.proposer_last_move
                        else:
                            entry.current_state = ChallengeState.CHALLENGED
                    entry.history.append(f"R{round_no}:Critic:{entry.current_state.value}")

            mentioned = {ch.issue_id for ch in c_turn.challenges}
            for entry in ledger.values():
                if entry.current_state == ChallengeState.CONCEDED and entry.issue_id not in mentioned:
                    entry.current_state = ChallengeState.ACCEPTED
                    entry.accepted_fingerprint = proposal_fingerprint(p_turn, entry.target_assumption_id)
                    entry.history.append(f"R{round_no}:Gate:CONCESSION_ACCEPTED")

            # Deadlock only when, in this round, the Proposer answered and the Critic explicitly
            # re-challenged that answer. An unanswered or unreviewed issue gets another round.
            deadlocked_ids = []
            if round_no >= 3:
                for entry in ledger.values():
                    if (
                        entry.current_state not in TERMINAL_STATES
                        and entry.rounds_contested >= 2
                        and entry.last_proposer_round == round_no
                        and entry.last_critic_challenge_round == round_no
                    ):
                        entry.current_state = ChallengeState.ESCALATED_TO_HUMAN
                        entry.escalation_reason = "DEADLOCK"
                        entry.history.append(f"R{round_no}:Gate:DEADLOCK_ESCALATED")
                        deadlocked_ids.append(entry.issue_id)

            disagreement_score = compute_disagreement(ledger)
            all_terminal = bool(ledger) and all(e.current_state in TERMINAL_STATES for e in ledger.values())

            should_stop = False
            termination_reason = "CONTINUE"
            if round_no < 2:
                termination_reason = "ROUND_1_MINIMUM_LOCK"
            elif all_terminal and deadlocked_ids:
                should_stop = True
                termination_reason = f"DEADLOCK_ESCALATED_TO_HUMAN ({', '.join(deadlocked_ids)})"
            elif all_terminal:
                should_stop = True
                signal = "CRITIC_SIGNALED_CONVERGENCE" if c_turn.ready_to_conclude else "ALL_ISSUES_TERMINAL_GATE_CLOSE"
                termination_reason = f"CONVERGENCE_ALL_ISSUES_RESOLVED_OR_ESCALATED ({signal})"
            elif round_no >= self.max_rounds:
                for entry in ledger.values():
                    if entry.current_state not in TERMINAL_STATES:
                        # Separate a real stalemate from an issue one side never got to answer.
                        if entry.last_proposer_round < round_no:
                            reason = "UNANSWERED_AT_ROUND_LIMIT"
                        elif entry.last_critic_challenge_round < round_no:
                            reason = "UNREVIEWED_AT_ROUND_LIMIT"
                        else:
                            reason = "MAX_ROUNDS_STILL_CONTESTED"
                        entry.current_state = ChallengeState.ESCALATED_TO_HUMAN
                        entry.escalation_reason = reason
                        entry.history.append(f"R{round_no}:Gate:{reason}")
                disagreement_score = compute_disagreement(ledger)
                should_stop = True
                termination_reason = "MAX_ROUNDS_FAILSAFE_ESCALATED"

            round_record = {
                "round": round_no,
                "proposer": p_turn.model_dump(),
                "critic": c_turn.model_dump(),
                "ledger_snapshot": {k: v.model_dump() for k, v in ledger.items()},
                "validation_errors": rejected,
                "disagreement_score": disagreement_score,
                "termination_reason": termination_reason,
                "should_stop": should_stop,
            }
            rounds_log.append(round_record)
            if on_round_callback:
                on_round_callback(round_record)

            if should_stop:
                break

        final_doc = build_decision_skeleton(feature_request, ledger, rounds_log, termination_reason)
        summary_ctx = (
            f"FEATURE REQUEST:\n{feature_request}\n\n"
            f"DECISION DOCUMENT FACTS (computed by the engine, final):\n{final_doc.model_dump_json(indent=2)}\n\n"
            f"FINAL LEDGER:\n{[v.model_dump() for v in ledger.values()]}\n"
            f"FULL DELIBERATION TRACE:\n{rounds_log}"
        )
        draft: SummarizerDraft = self._call_structured(
            self.summarizer_model, summarizer_sys, summary_ctx, SummarizerDraft
        )
        corrections = apply_summarizer_prose(final_doc, draft)
        return final_doc, {
            "feature_request": feature_request,
            "rounds": rounds_log,
            "final_decision": final_doc.model_dump(),
            "summary_corrections": corrections,
        }

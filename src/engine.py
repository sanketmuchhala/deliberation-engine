from __future__ import annotations
import os
from pathlib import Path
from statistics import fmean
from openai import OpenAI
from src.schemas import (
    ChallengeState,
    CriticTurn,
    FinalDecisionDocument,
    IssueLedgerEntry,
    ProposerTurn,
    STATE_WEIGHT,
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


class DeliberationEngine:
    def __init__(self, max_rounds: int = 4) -> None:
        self.max_rounds = max(2, max_rounds)
        self.client = OpenAI(
            api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "test-key",
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
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

    def run(self, feature_request: str, on_round_callback=None) -> tuple[FinalDecisionDocument, dict]:
        proposer_sys = load_prompt("proposer")
        critic_sys = load_prompt("critic")
        summarizer_sys = load_prompt("summarizer")

        ledger: dict[str, IssueLedgerEntry] = {}
        rounds_log: list[dict] = []
        termination_reason = "CONTINUE"

        for round_no in range(1, self.max_rounds + 1):
            proposer_ctx = (
                f"FEATURE REQUEST:\n{feature_request}\n\n"
                f"CURRENT ROUND: {round_no}\n"
                f"ACTIVE ISSUE LEDGER:\n{[v.model_dump() for v in ledger.values()]}\n"
                f"PREVIOUS ROUNDS:\n{rounds_log}"
            )
            p_turn: ProposerTurn = self._call_structured(
                self.proposer_model, proposer_sys, proposer_ctx, ProposerTurn
            )

            for resp in p_turn.challenge_responses:
                if resp.issue_id in ledger:
                    entry = ledger[resp.issue_id]
                    entry.proposer_last_move = ChallengeState(resp.move)
                    entry.current_state = ChallengeState(resp.move)
                    entry.proposer_confidence = resp.confidence
                    entry.history.append(f"R{round_no}:Proposer:{resp.move}")

            critic_ctx = (
                f"FEATURE REQUEST:\n{feature_request}\n\n"
                f"CURRENT ROUND: {round_no}\n"
                f"PROPOSER OUTPUT THIS ROUND:\n{p_turn.model_dump_json(indent=2)}\n"
                f"CURRENT ISSUE LEDGER:\n{[v.model_dump() for v in ledger.values()]}"
            )
            c_turn: CriticTurn = self._call_structured(
                self.critic_model, critic_sys, critic_ctx, CriticTurn
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
                        history=[f"R{round_no}:Critic:CHALLENGED"],
                    )
                else:
                    entry = ledger[ch.issue_id]
                    entry.critic_confidence = ch.confidence
                    if round_no == 1:
                        entry.current_state = ChallengeState.CHALLENGED
                    elif ch.status in ("ACCEPTED", "ESCALATED_TO_HUMAN"):
                        entry.current_state = ChallengeState(ch.status)
                    else:
                        entry.rounds_contested += 1
                        if entry.proposer_last_move in (ChallengeState.DEFENDED, ChallengeState.REVISED):
                            entry.current_state = entry.proposer_last_move
                        else:
                            entry.current_state = ChallengeState.CHALLENGED
                    entry.history.append(f"R{round_no}:Critic:{entry.current_state.value}")

            deadlocked_ids = []
            if round_no >= 3:
                for entry in ledger.values():
                    if entry.current_state not in TERMINAL_STATES and entry.rounds_contested >= 2:
                        entry.current_state = ChallengeState.ESCALATED_TO_HUMAN
                        entry.history.append(f"R{round_no}:Gate:DEADLOCK_ESCALATED")
                        deadlocked_ids.append(entry.issue_id)

            disagreement_score = compute_disagreement(ledger)
            all_terminal = bool(ledger) and all(e.current_state in TERMINAL_STATES for e in ledger.values())

            should_stop = False
            if round_no < 2:
                termination_reason = "ROUND_1_MINIMUM_LOCK"
            elif all_terminal and deadlocked_ids:
                should_stop = True
                termination_reason = f"DEADLOCK_ESCALATED_TO_HUMAN ({', '.join(deadlocked_ids)})"
            elif all_terminal or (c_turn.ready_to_conclude and disagreement_score == 0.0):
                should_stop = True
                termination_reason = "CONVERGENCE_ALL_ISSUES_RESOLVED_OR_ESCALATED"
            elif round_no >= self.max_rounds:
                for entry in ledger.values():
                    if entry.current_state not in TERMINAL_STATES:
                        entry.current_state = ChallengeState.ESCALATED_TO_HUMAN
                disagreement_score = compute_disagreement(ledger)
                should_stop = True
                termination_reason = "MAX_ROUNDS_FAILSAFE_ESCALATED"

            round_record = {
                "round": round_no,
                "proposer": p_turn.model_dump(),
                "critic": c_turn.model_dump(),
                "ledger_snapshot": {k: v.model_dump() for k, v in ledger.items()},
                "disagreement_score": disagreement_score,
                "termination_reason": termination_reason,
                "should_stop": should_stop,
            }
            rounds_log.append(round_record)
            if on_round_callback:
                on_round_callback(round_record)

            if should_stop:
                break

        summary_ctx = (
            f"FEATURE REQUEST:\n{feature_request}\n\n"
            f"FINAL TERMINATION REASON: {termination_reason}\n"
            f"FINAL DISAGREEMENT SCORE: {rounds_log[-1]['disagreement_score']}\n"
            f"FINAL LEDGER:\n{[v.model_dump() for v in ledger.values()]}\n"
            f"FULL DELIBERATION TRACE:\n{rounds_log}"
        )
        final_doc: FinalDecisionDocument = self._call_structured(
            self.summarizer_model, summarizer_sys, summary_ctx, FinalDecisionDocument
        )
        return final_doc, {
            "feature_request": feature_request,
            "rounds": rounds_log,
            "final_decision": final_doc.model_dump(),
        }

"""Offline tests for the deliberation state machine: scripted agent turns, no API calls."""
import unittest

from src.engine import DeliberationEngine
from src.schemas import CriticTurn, FinalDecisionDocument, ProposerTurn

ASSUMPTIONS = [{"assumption_id": f"A{i}", "statement": "s", "rationale": "r"} for i in (1, 2, 3)]
CONVERGED = "CONVERGENCE_ALL_ISSUES_RESOLVED_OR_ESCALATED (CRITIC_SIGNALED_CONVERGENCE)"


def proposer(*moves):
    return ProposerTurn(
        proposed_scope_in=["x"], proposed_scope_out=["y"], assumptions=ASSUMPTIONS,
        success_criteria=["z"], overall_confidence=0.7,
        challenge_responses=[{"issue_id": i, "move": m, "response": "r", "confidence": 0.8} for i, m in moves],
    )


def critic(*statuses, ready=False):
    return CriticTurn(
        challenges=[
            {"issue_id": i, "target_assumption_id": "A1", "challenge_text": "t",
             "evaluation_of_proposer": "e", "status": s, "confidence": 0.8}
            for i, s in statuses
        ],
        ready_to_conclude=ready, overall_confidence=0.6,
    )


# Deliberately wrong metadata: the engine must overwrite it from its own state.
SUMMARY = FinalDecisionDocument(
    feature_request="f", executive_summary="e", agreed_scope_included=[], agreed_scope_excluded=[],
    success_criteria=[], surfaced_assumptions=[], open_questions_for_humans=[],
    final_disagreement_score=9.9, proposer_confidence=0.01, critic_confidence=0.01, termination_reason="LLM_TYPO",
)

ROUND_1 = [proposer(), critic(("C1", "CHALLENGED"), ("C2", "CHALLENGED"), ("C3", "CHALLENGED"))]


class DeliberationStateMachineTest(unittest.TestCase):
    def run_script(self, *turns):
        engine = DeliberationEngine(max_rounds=4)
        replies = iter([*ROUND_1, *turns, SUMMARY])
        engine._call_structured = lambda *args, **kwargs: next(replies)
        doc, trace = engine.run("test request")
        last = trace["rounds"][-1]
        self.assertEqual(doc.termination_reason, last["termination_reason"])
        self.assertEqual(doc.final_disagreement_score, last["disagreement_score"])
        self.assertEqual((doc.proposer_confidence, doc.critic_confidence), (0.7, 0.6))
        return trace

    def states(self, trace, round_index=-1):
        snapshot = trace["rounds"][round_index]["ledger_snapshot"]
        return {issue_id: entry["current_state"].value for issue_id, entry in snapshot.items()}

    def history(self, trace, issue_id):
        return trace["rounds"][-1]["ledger_snapshot"][issue_id]["history"]

    def test_converges_in_round_2_when_critic_settles_everything(self):
        trace = self.run_script(
            proposer(("C1", "DEFENDED"), ("C2", "REVISED"), ("C3", "CONCEDED")),
            critic(("C1", "ACCEPTED"), ("C2", "ACCEPTED"), ("C3", "ESCALATED_TO_HUMAN"), ready=True),
        )
        self.assertEqual([r["disagreement_score"] for r in trace["rounds"]], [0.9, 0.0])
        self.assertEqual([r["termination_reason"] for r in trace["rounds"]], ["ROUND_1_MINIMUM_LOCK", CONVERGED])
        self.assertEqual(self.states(trace), {"C1": "ACCEPTED", "C2": "ACCEPTED", "C3": "ESCALATED_TO_HUMAN"})

    def test_deadlock_in_round_3_escalates_and_round_2_reports_continue(self):
        trace = self.run_script(
            proposer(("C1", "DEFENDED"), ("C2", "REVISED"), ("C3", "CONCEDED")),
            critic(("C1", "ACCEPTED"), ("C2", "CHALLENGED"), ("C3", "ESCALATED_TO_HUMAN")),
            proposer(("C2", "DEFENDED")),
            critic(("C1", "ACCEPTED"), ("C2", "CHALLENGED"), ("C3", "ESCALATED_TO_HUMAN")),
        )
        self.assertEqual(trace["rounds"][1]["termination_reason"], "CONTINUE")
        self.assertEqual(trace["rounds"][-1]["termination_reason"], "DEADLOCK_ESCALATED_TO_HUMAN (C2)")
        self.assertEqual(self.states(trace)["C2"], "ESCALATED_TO_HUMAN")
        self.assertIn("R3:Gate:DEADLOCK_ESCALATED", self.history(trace, "C2"))

    def test_proposer_cannot_reopen_accepted_issue(self):
        trace = self.run_script(
            proposer(("C1", "DEFENDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED")),
            critic(("C1", "ACCEPTED"), ("C2", "ACCEPTED"), ("C3", "CHALLENGED")),
            proposer(("C1", "DEFENDED"), ("C3", "REVISED")),
            critic(("C2", "ACCEPTED"), ("C3", "ACCEPTED"), ready=True),
        )
        self.assertEqual(trace["rounds"][-1]["termination_reason"], CONVERGED)
        self.assertEqual(self.states(trace)["C1"], "ACCEPTED")
        self.assertNotIn("R3:Proposer:DEFENDED", self.history(trace, "C1"))

    def test_concession_omitted_by_critic_is_accepted(self):
        trace = self.run_script(
            proposer(("C1", "CONCEDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED")),
            critic(("C2", "ACCEPTED"), ("C3", "ACCEPTED"), ready=True),
        )
        self.assertEqual(len(trace["rounds"]), 2)
        self.assertEqual(self.states(trace)["C1"], "ACCEPTED")
        self.assertIn("R2:Gate:CONCESSION_ACCEPTED", self.history(trace, "C1"))

    def test_rechallenged_concession_stays_open(self):
        trace = self.run_script(
            proposer(("C1", "CONCEDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED")),
            critic(("C1", "CHALLENGED"), ("C2", "ACCEPTED"), ("C3", "ACCEPTED")),
            proposer(("C1", "REVISED")),
            critic(("C1", "ACCEPTED"), ("C2", "ACCEPTED"), ready=True),
        )
        self.assertEqual(self.states(trace, round_index=1)["C1"], "CHALLENGED")
        self.assertEqual(len(trace["rounds"]), 3)
        self.assertEqual(self.states(trace)["C1"], "ACCEPTED")

    def test_critic_cannot_reopen_escalated_issue(self):
        trace = self.run_script(
            proposer(("C1", "DEFENDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED")),
            critic(("C1", "ACCEPTED"), ("C2", "CHALLENGED"), ("C3", "ESCALATED_TO_HUMAN")),
            proposer(("C2", "REVISED")),
            critic(("C2", "ACCEPTED"), ("C3", "CHALLENGED"), ready=True),
        )
        self.assertEqual(trace["rounds"][-1]["termination_reason"], CONVERGED)
        self.assertEqual(self.states(trace)["C3"], "ESCALATED_TO_HUMAN")

    def test_all_terminal_without_critic_signal_still_closes(self):
        trace = self.run_script(
            proposer(("C1", "DEFENDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED")),
            critic(("C1", "ACCEPTED"), ("C2", "ACCEPTED"), ("C3", "ACCEPTED"), ready=False),
        )
        self.assertEqual(
            trace["rounds"][-1]["termination_reason"],
            "CONVERGENCE_ALL_ISSUES_RESOLVED_OR_ESCALATED (ALL_ISSUES_TERMINAL_GATE_CLOSE)",
        )

    def test_max_rounds_failsafe_escalates_open_issues(self):
        trace = self.run_script(
            proposer(("C1", "DEFENDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED")),
            critic(("C1", "ACCEPTED"), ("C2", "ACCEPTED"), ("C3", "ACCEPTED"), ("C4", "CHALLENGED")),
            proposer(("C4", "DEFENDED")),
            critic(("C4", "ACCEPTED"), ("C5", "CHALLENGED")),
            proposer(("C5", "DEFENDED")),
            critic(("C5", "ACCEPTED"), ("C6", "CHALLENGED")),
        )
        self.assertEqual(len(trace["rounds"]), 4)
        self.assertEqual(trace["rounds"][-1]["termination_reason"], "MAX_ROUNDS_FAILSAFE_ESCALATED")
        self.assertEqual(self.states(trace)["C6"], "ESCALATED_TO_HUMAN")
        self.assertIn("R4:Gate:MAX_ROUNDS_ESCALATED", self.history(trace, "C6"))


if __name__ == "__main__":
    unittest.main()

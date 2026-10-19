"""Offline tests for the deliberation state machine: scripted agent turns, no API calls."""
import unittest
from unittest import mock

from src.engine import DeliberationEngine
from src.schemas import CriticTurn, ProposerTurn, SummarizerDraft

CONVERGED = "CONVERGENCE_ALL_ISSUES_RESOLVED_OR_ESCALATED (CRITIC_SIGNALED_CONVERGENCE)"


def proposer(*moves, a1="s", x="x", w="w", x_ids=("A1",), z_scope=("S1",), a3_id="A3"):
    return ProposerTurn(
        proposed_scope_in=[
            {"scope_id": "S1", "item": x, "assumption_ids": list(x_ids)},
            {"scope_id": "S2", "item": w, "assumption_ids": ["A2"]},
        ],
        proposed_scope_out=["y"],
        assumptions=[
            {"assumption_id": aid, "statement": a1 if aid == "A1" else "s", "rationale": "r"} for aid in ("A1", "A2", a3_id)
        ],
        success_criteria=[
            {"criterion": "z", "scope_item_ids": list(z_scope)},
            {"criterion": "v", "scope_item_ids": ["S2"]},
        ],
        overall_confidence=0.7,
        challenge_responses=[{"issue_id": i, "move": m, "response": "r", "confidence": 0.8} for i, m in moves],
    )


def critic(*statuses, ready=False, target="A1"):
    return CriticTurn(
        challenges=[
            {"issue_id": i, "target_assumption_id": target, "challenge_text": "t",
             "evaluation_of_proposer": "e", "status": s, "confidence": 0.8}
            for i, s in statuses
        ],
        ready_to_conclude=ready, overall_confidence=0.6,
    )


# An empty draft: the engine must still produce a complete document from its own state.
SUMMARY = SummarizerDraft(executive_summary="e", assumption_notes=[], open_questions_for_humans=[])

ROUND_1 = [proposer(), critic(("C1", "CHALLENGED"), ("C2", "CHALLENGED"), ("C3", "CHALLENGED"))]


class DeliberationStateMachineTest(unittest.TestCase):
    def run_script(self, *turns, summary=SUMMARY, max_rounds=4):
        engine = DeliberationEngine(max_rounds=max_rounds)
        replies = iter([*ROUND_1, *turns, summary.model_copy(deep=True)])
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

    def reason(self, trace, issue_id):
        return trace["rounds"][-1]["ledger_snapshot"][issue_id]["escalation_reason"]

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
        self.assertEqual((self.reason(trace, "C2"), self.reason(trace, "C3")), ("DEADLOCK", "POLICY_ESCALATED_BY_CRITIC"))

    def test_round_3_challenges_get_a_reply_before_escalation(self):
        trace = self.run_script(
            proposer(("C1", "DEFENDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED")),
            critic(("C1", "ACCEPTED"), ("C2", "CHALLENGED"), ("C3", "ACCEPTED")),
            proposer(),  # skips C2 this round
            critic(("C1", "ACCEPTED"), ("C2", "CHALLENGED"), ("C3", "ACCEPTED"), ("C4", "CHALLENGED")),
            proposer(("C2", "REVISED"), ("C4", "DEFENDED")),
            critic(("C2", "ACCEPTED"), ("C4", "ACCEPTED"), ready=True),
        )
        self.assertEqual(trace["rounds"][2]["termination_reason"], "CONTINUE")
        self.assertEqual(trace["rounds"][-1]["termination_reason"], CONVERGED)
        self.assertEqual(self.states(trace), {"C1": "ACCEPTED", "C2": "ACCEPTED", "C3": "ACCEPTED", "C4": "ACCEPTED"})
        self.assertNotIn("R3:Gate:DEADLOCK_ESCALATED", self.history(trace, "C2"))
        self.assertIn("R4:Proposer:DEFENDED", self.history(trace, "C4"))

    def test_answer_the_critic_did_not_rule_on_is_not_deadlocked(self):
        trace = self.run_script(
            proposer(("C1", "DEFENDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED")),
            critic(("C1", "ACCEPTED"), ("C2", "CHALLENGED"), ("C3", "ACCEPTED")),
            proposer(("C2", "REVISED")),
            critic(("C1", "ACCEPTED"), ("C3", "ACCEPTED")),  # omits C2
            proposer(("C2", "REVISED")),
            critic(("C2", "ACCEPTED"), ("C3", "ACCEPTED"), ready=True),
        )
        self.assertEqual(trace["rounds"][2]["termination_reason"], "CONTINUE")
        self.assertEqual(self.states(trace, round_index=2)["C2"], "REVISED")
        self.assertEqual(trace["rounds"][-1]["termination_reason"], CONVERGED)
        self.assertNotIn("R3:Gate:DEADLOCK_ESCALATED", self.history(trace, "C2"))

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

    def test_changed_assumption_reopens_its_accepted_issues(self):
        trace = self.run_script(
            proposer(("C1", "DEFENDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED")),
            critic(("C1", "ACCEPTED"), ("C2", "ACCEPTED"), ("C3", "CHALLENGED")),
            proposer(("C3", "REVISED"), a1="s, now with an expiry date"),
            critic(("C1", "ACCEPTED"), ("C2", "CHALLENGED"), ("C3", "ACCEPTED")),
            proposer(("C2", "REVISED"), a1="  S, NOW WITH AN EXPIRY DATE. "),  # cosmetic change only
            critic(("C2", "ACCEPTED"), ("C3", "ACCEPTED"), ready=True),
        )
        self.assertEqual(self.states(trace, round_index=2), {"C1": "ACCEPTED", "C2": "REVISED", "C3": "ACCEPTED"})
        self.assertIn("R3:Gate:REOPENED_PROPOSAL_CHANGED", self.history(trace, "C1"))
        self.assertEqual(trace["rounds"][-1]["termination_reason"], CONVERGED)
        self.assertNotIn("R4:Gate:REOPENED_PROPOSAL_CHANGED", self.history(trace, "C1"))

    def test_changed_scope_item_reopens_only_issues_on_its_assumption(self):
        accepted = [
            proposer(("C1", "DEFENDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED")),
            critic(("C1", "ACCEPTED"), ("C2", "ACCEPTED"), ("C3", "CHALLENGED")),
        ]
        settle = critic(("C1", "ACCEPTED"), ("C2", "ACCEPTED"), ("C3", "ACCEPTED"), ready=True)
        trace = self.run_script(*accepted, proposer(("C3", "REVISED"), x="x, active missions only"), settle)
        self.assertIn("R3:Gate:REOPENED_PROPOSAL_CHANGED", self.history(trace, "C1"))
        trace = self.run_script(*accepted, proposer(("C3", "REVISED"), w="w, active missions only"), settle)
        self.assertNotIn("R3:Gate:REOPENED_PROPOSAL_CHANGED", self.history(trace, "C1"))  # w relies on A2, not A1

    def test_invalid_references_get_one_corrective_retry(self):
        trace = self.run_script(
            proposer(("C1", "DEFENDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED"), x_ids=("A9",)),
            proposer(("C1", "DEFENDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED")),
            critic(("C1", "ACCEPTED"), ("C2", "ACCEPTED"), ("C3", "ACCEPTED"), ("C4", "CHALLENGED"), target="A9"),
            critic(("C1", "ACCEPTED"), ("C2", "ACCEPTED"), ("C3", "ACCEPTED"), ready=True),
        )
        self.assertEqual(trace["rounds"][-1]["termination_reason"], CONVERGED)
        rejected = trace["rounds"][1]["validation_errors"]
        self.assertEqual(len(rejected), 2)
        self.assertIn("references unknown A9", rejected[0])
        self.assertIn("New issue C4 targets unknown A9", rejected[1])

    def test_references_still_invalid_after_retry_fail_loudly(self):
        engine = DeliberationEngine()
        replies = iter([*ROUND_1, proposer(x_ids=()), proposer(x_ids=())])
        engine._call_structured = lambda *args, **kwargs: next(replies)
        with self.assertRaisesRegex(ValueError, "lists no references"):
            engine.run("test request")

    def test_duplicate_and_dangling_ids_are_rejected_before_they_touch_the_ledger(self):
        trace = self.run_script(
            proposer(("C1", "DEFENDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED"), a3_id="A2", z_scope=("S9",)),
            proposer(("C1", "DEFENDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED")),
            critic(("C1", "ACCEPTED"), ("C2", "CHALLENGED"), ("C2", "CHALLENGED"), ("C3", "ACCEPTED")),
            critic(("C1", "ACCEPTED"), ("C2", "CHALLENGED"), ("C3", "ACCEPTED")),
            proposer(("C2", "REVISED")),
            critic(("C2", "ACCEPTED"), ("C3", "ACCEPTED"), ready=True),
        )
        rejected = trace["rounds"][1]["validation_errors"]
        self.assertEqual(len(rejected), 3)
        self.assertIn("Duplicate assumption IDs: A2", rejected[0])
        self.assertIn("Success criterion 'z' references unknown S9", rejected[1])
        self.assertIn("Duplicate issue IDs: C2", rejected[2])
        self.assertEqual(trace["rounds"][1]["ledger_snapshot"]["C2"]["rounds_contested"], 2)

    def test_challenge_count_rises_once_per_round_even_if_a_duplicate_slips_through(self):
        with mock.patch("src.engine.critic_turn_errors", return_value=[]):
            trace = self.run_script(
                proposer(("C1", "DEFENDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED")),
                critic(("C1", "ACCEPTED"), ("C2", "CHALLENGED"), ("C2", "CHALLENGED"), ("C3", "ACCEPTED")),
                proposer(("C2", "REVISED")),
                critic(("C2", "ACCEPTED"), ("C3", "ACCEPTED"), ready=True),
            )
        self.assertEqual(trace["rounds"][1]["ledger_snapshot"]["C2"]["rounds_contested"], 2)

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
        self.assertIn("R4:Gate:UNANSWERED_AT_ROUND_LIMIT", self.history(trace, "C6"))

    def test_max_rounds_separates_stalemate_from_one_sided_issues(self):
        trace = self.run_script(
            proposer(("C1", "DEFENDED"), ("C2", "DEFENDED"), ("C3", "DEFENDED")),
            critic(("C1", "CHALLENGED"), ("C2", "ACCEPTED"), ("C4", "CHALLENGED")),  # omits C3
            max_rounds=2,
        )
        self.assertEqual(trace["rounds"][-1]["termination_reason"], "MAX_ROUNDS_FAILSAFE_ESCALATED")
        self.assertEqual(
            {i: self.reason(trace, i) for i in ("C1", "C3", "C4")},
            {"C1": "MAX_ROUNDS_STILL_CONTESTED", "C3": "UNREVIEWED_AT_ROUND_LIMIT", "C4": "UNANSWERED_AT_ROUND_LIMIT"},
        )

    def test_summary_prose_cannot_change_ledger_facts(self):
        draft = SummarizerDraft(
            executive_summary="Everything is agreed.",
            assumption_notes=[
                {"assumption_id": "A1", "resolution_notes": "kept"},
                {"assumption_id": "A9", "resolution_notes": "invented"},
            ],
            open_questions_for_humans=[
                {"issue_id": "C1", "decision_owner": "x", "question": "settled already"},
                {"issue_id": "[C3]", "decision_owner": "Legal", "question": "Who may see it?"},
            ],
        )
        trace = self.run_script(
            proposer(("C1", "DEFENDED"), ("C2", "REVISED"), ("C3", "CONCEDED")),
            critic(("C1", "ACCEPTED"), ("C2", "CHALLENGED"), ("C3", "ESCALATED_TO_HUMAN")),
            proposer(("C2", "DEFENDED")),
            critic(("C1", "ACCEPTED"), ("C2", "CHALLENGED"), ("C3", "ESCALATED_TO_HUMAN")),
            summary=draft,
        )
        doc = trace["final_decision"]
        self.assertEqual(doc["agreed_scope_included"], ["[S2] w"])
        self.assertEqual(doc["scope_pending_human_decision"], [{"item": "[S1] x", "blocked_by": ["C2", "C3"]}])
        self.assertEqual(doc["success_criteria"], ["v (measures S2)"])
        self.assertEqual(doc["success_criteria_pending"], [{"item": "z (measures S1)", "blocked_by": ["C2", "C3"]}])
        questions = {q["issue_id"]: q for q in doc["open_questions_for_humans"]}
        self.assertEqual(list(questions), ["C2", "C3"])
        self.assertEqual(questions["C3"]["decision_owner"], "Legal")
        self.assertTrue(questions["C2"]["decision_owner"].startswith("Unassigned"))
        dispositions = {a["assumption_id"]: (a["was_challenged"], a["final_disposition"]) for a in doc["surfaced_assumptions"]}
        self.assertEqual(dispositions, {"A1": (True, "ESCALATED_TO_HUMAN"), "A2": (False, "ACCEPTED"), "A3": (False, "ACCEPTED")})
        self.assertEqual(trace["summary_corrections"], [
            "A9: note dropped (the Proposer never surfaced it)",
            "A2: note missing; engine note kept",
            "A3: note missing; engine note kept",
            "C1: open question dropped (issue was not escalated)",
            "C2: open question missing; engine fallback kept",
        ])


if __name__ == "__main__":
    unittest.main()

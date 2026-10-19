from __future__ import annotations
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class ChallengeState(str, Enum):
    CHALLENGED = "CHALLENGED"
    DEFENDED = "DEFENDED"
    REVISED = "REVISED"
    CONCEDED = "CONCEDED"
    ACCEPTED = "ACCEPTED"
    ESCALATED_TO_HUMAN = "ESCALATED_TO_HUMAN"


STATE_WEIGHT: dict[ChallengeState, float] = {
    ChallengeState.CHALLENGED: 1.00,          # Brand-new challenge from Critic (100% open)
    ChallengeState.DEFENDED: 0.75,            # Proposer pushed back & kept scope (75% open)
    ChallengeState.REVISED: 0.50,             # Proposer compromised & tweaked scope (50% open)
    ChallengeState.CONCEDED: 0.25,            # Proposer yielded position (25% open)
    ChallengeState.ACCEPTED: 0.00,            # Critic satisfied -> Resolved (0% open)
    ChallengeState.ESCALATED_TO_HUMAN: 0.00,  # Policy/diplomatic issue -> Open Questions (0% open)
}

TERMINAL_STATES = {ChallengeState.ACCEPTED, ChallengeState.ESCALATED_TO_HUMAN}
CONTESTED_STATES = {ChallengeState.CHALLENGED, ChallengeState.DEFENDED, ChallengeState.REVISED}

# Why the engine handed an issue to humans (set by Python, never by an agent).
EscalationReason = Literal[
    "POLICY_ESCALATED_BY_CRITIC",   # Critic routed it as an institutional policy question
    "DEADLOCK",                     # Critic rejected the Proposer's latest answer again in round >= 3
    "MAX_ROUNDS_STILL_CONTESTED",   # Proposer answered and Critic re-challenged in the final round
    "UNANSWERED_AT_ROUND_LIMIT",    # Proposer did not answer the latest challenge before the limit
    "UNREVIEWED_AT_ROUND_LIMIT",    # Proposer answered in the final round; Critic never ruled on it
]


class AssumptionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assumption_id: str = Field(description="e.g., A1, A2, A3")
    statement: str = Field(description="Implicit assumption surfaced from the request")
    rationale: str = Field(description="Why this assumption keeps the MVP lean and workable")


class ScopeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_id: str = Field(description="Unique within the turn, e.g., S1")
    item: str = Field(description="One in-scope capability or rule")
    assumption_ids: list[str] = Field(description="Assumption IDs this item relies on (at least one), e.g., [\"A2\"]")


class SuccessCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion: str = Field(description="A measurable success criterion")
    scope_item_ids: list[str] = Field(description="In-scope item IDs this criterion measures (at least one), e.g., [\"S2\"]")


class ProposerResponseItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issue_id: str = Field(description="Matches Critic challenge ID, e.g., C1")
    move: Literal["DEFENDED", "REVISED", "CONCEDED"]
    response: str = Field(description="Concrete technical defense, scope revision, or concession")
    confidence: float = Field(ge=0.0, le=1.0)


class ProposerTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposed_scope_in: list[ScopeItem] = Field(min_length=1)
    proposed_scope_out: list[str] = Field(min_length=1)
    assumptions: list[AssumptionItem] = Field(min_length=2)
    success_criteria: list[SuccessCriterion] = Field(min_length=1)
    challenge_responses: list[ProposerResponseItem] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)


class CriticChallengeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issue_id: str = Field(description="e.g., C1, C2, C3")
    target_assumption_id: str = Field(description="Target assumption ID, e.g., A1")
    challenge_text: str = Field(description="Specific risk, missing constraint, or edge case")
    evaluation_of_proposer: str = Field(description="Assessment of Proposer's current stance")
    status: Literal["CHALLENGED", "ACCEPTED", "ESCALATED_TO_HUMAN"]
    confidence: float = Field(ge=0.0, le=1.0)


class CriticTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenges: list[CriticChallengeUpdate] = Field(min_length=2)
    ready_to_conclude: bool
    overall_confidence: float = Field(ge=0.0, le=1.0)


class SurfacedAssumptionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assumption_id: str
    assumption: str
    was_challenged: bool
    final_disposition: Literal[
        "ACCEPTED", "REVISED_AND_ACCEPTED", "CONCEDED_AND_REMOVED", "ESCALATED_TO_HUMAN"
    ]
    resolution_notes: str


class OpenQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issue_id: str = Field(description="Escalated ledger issue, e.g., C2")
    decision_owner: str = Field(description="Who should decide, e.g., Head of Diplomatic Security")
    question: str = Field(description="A decision the owner can answer")


class AssumptionNote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assumption_id: str
    resolution_notes: str = Field(description="One or two sentences citing the issue IDs and how they ended")


class SummarizerDraft(BaseModel):
    """Everything the Summarizer writes: prose only. Python assembles the decision document."""
    model_config = ConfigDict(extra="forbid")
    executive_summary: str
    assumption_notes: list[AssumptionNote]
    open_questions_for_humans: list[OpenQuestion]


class PendingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: str
    blocked_by: list[str] = Field(description="Escalated issue IDs this item waits on")


class FinalDecisionDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feature_request: str
    executive_summary: str
    agreed_scope_included: list[str]
    scope_pending_human_decision: list[PendingItem]
    agreed_scope_excluded: list[str]
    success_criteria: list[str]
    success_criteria_pending: list[PendingItem]
    surfaced_assumptions: list[SurfacedAssumptionSummary]
    open_questions_for_humans: list[OpenQuestion]
    final_disagreement_score: float
    proposer_confidence: float
    critic_confidence: float
    termination_reason: str


class IssueLedgerEntry(BaseModel):
    issue_id: str
    target_assumption_id: str
    challenge_text: str
    proposer_last_move: ChallengeState = ChallengeState.CHALLENGED
    current_state: ChallengeState = ChallengeState.CHALLENGED
    proposer_confidence: float = 0.8
    critic_confidence: float = 0.8
    rounds_contested: int = 1
    last_proposer_round: int = 0
    last_critic_challenge_round: int = 0
    accepted_fingerprint: Optional[str] = None
    escalation_reason: Optional[EscalationReason] = None
    history: list[str] = Field(default_factory=list)

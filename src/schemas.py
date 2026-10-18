from __future__ import annotations
from enum import Enum
from typing import Literal
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


class AssumptionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assumption_id: str = Field(description="e.g., A1, A2, A3")
    statement: str = Field(description="Implicit assumption surfaced from the request")
    rationale: str = Field(description="Why this assumption keeps the MVP lean and workable")


class ProposerResponseItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issue_id: str = Field(description="Matches Critic challenge ID, e.g., C1")
    move: Literal["DEFENDED", "REVISED", "CONCEDED"]
    response: str = Field(description="Concrete technical defense, scope revision, or concession")
    confidence: float = Field(ge=0.0, le=1.0)


class ProposerTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposed_scope_in: list[str] = Field(min_length=1)
    proposed_scope_out: list[str] = Field(min_length=1)
    assumptions: list[AssumptionItem] = Field(min_length=2)
    success_criteria: list[str] = Field(min_length=1)
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


class FinalDecisionDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feature_request: str
    executive_summary: str
    agreed_scope_included: list[str]
    agreed_scope_excluded: list[str]
    success_criteria: list[str]
    surfaced_assumptions: list[SurfacedAssumptionSummary]
    open_questions_for_humans: list[str]
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
    history: list[str] = Field(default_factory=list)

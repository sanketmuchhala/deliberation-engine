from typing import List, Optional

from pydantic import BaseModel


class Turn(BaseModel):
    round: int
    role: str
    content: str


class DeliberationResult(BaseModel):
    question: str
    turns: List[Turn] = []
    summary: Optional[str] = None

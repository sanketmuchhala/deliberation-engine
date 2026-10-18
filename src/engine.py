from pathlib import Path

from src.schemas import DeliberationResult

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text()


def run(question: str, config: dict) -> DeliberationResult:
    raise NotImplementedError

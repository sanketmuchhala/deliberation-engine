from __future__ import annotations
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from src.engine import DeliberationEngine
from src.schemas import FinalDecisionDocument

console = Console()


def render_markdown(doc: FinalDecisionDocument) -> str:
    lines = [
        "# Deliberation Decision Document",
        f"**Feature Request:** {doc.feature_request}\n",
        f"**Termination Reason:** `{doc.termination_reason}` | "
        f"**Final Disagreement Score:** `{doc.final_disagreement_score}` | "
        f"**Confidence (Proposer / Critic):** `{doc.proposer_confidence:.2f}` / `{doc.critic_confidence:.2f}`\n",
        f"## Executive Summary\n{doc.executive_summary}\n",
        "## 1. Agreed Scope",
        "### Included in Scope (v1 MVP)",
        *[f"- {item}" for item in doc.agreed_scope_included],
        "\n### Explicitly Excluded from Scope",
        *[f"- {item}" for item in doc.agreed_scope_excluded],
        "\n### Success Criteria",
        *[f"- {item}" for item in doc.success_criteria],
        "\n## 2. Surfaced Assumptions & Deliberation Outcomes",
        *[
            f"- **[{a.assumption_id}] {a.assumption}** "
            f"(Challenged: `{a.was_challenged}` -> Disposition: `{a.final_disposition}`)\n  - *Notes:* {a.resolution_notes}"
            for a in doc.surfaced_assumptions
        ],
        "\n## 3. Open Questions Requiring Human / Policy Sign-Off",
        *[f"- {q}" for q in doc.open_questions_for_humans],
    ]
    return "\n".join(lines) + "\n"


def print_round(r: dict) -> None:
    p, c = r["proposer"], r["critic"]
    assumptions = [f"{a['assumption_id']}: {a['statement']}" for a in p["assumptions"]]
    console.print(Panel(
        f"[bold cyan]Proposed Scope (In):[/bold cyan] {p['proposed_scope_in']}\n"
        f"[bold cyan]Assumptions:[/bold cyan] {assumptions}\n"
        f"[bold cyan]Challenge Responses:[/bold cyan] {p['challenge_responses']}",
        title=f"Round {r['round']} · PROPOSER (Conf: {p['overall_confidence']:.2f})",
    ))
    console.print(Panel(
        "\n".join(
            f"• [{ch['issue_id']} -> {ch['target_assumption_id']}] ({ch['status']}): {ch['challenge_text']}\n"
            f"  Eval: {ch['evaluation_of_proposer']}"
            for ch in c["challenges"]
        ) + f"\n\n[bold yellow]Disagreement Score:[/bold yellow] {r['disagreement_score']} | "
            f"[bold green]Gate Status:[/bold green] {r['termination_reason']}",
        title=f"Round {r['round']} · CRITIC (Conf: {c['overall_confidence']:.2f}, Ready: {c['ready_to_conclude']})",
    ))


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="The Deliberation Engine")
    parser.add_argument("--request", type=str, help="Vague feature request string")
    parser.add_argument("--config", type=str, help="Path to JSON config with feature_request")
    parser.add_argument("--max-rounds", type=int, default=4)
    parser.add_argument("--output-dir", type=str, default="outputs")
    args = parser.parse_args()

    request_text = args.request
    if not request_text and args.config:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
        request_text = cfg.get("feature_request")
    if not request_text:
        request_text = "We need a better way to track who is the right person to contact in each country."

    console.rule("[bold magenta]The Deliberation Engine[/bold magenta]")
    console.print(f"[bold]Input Feature Request:[/bold] {request_text}\n")

    engine = DeliberationEngine(max_rounds=args.max_rounds)
    final_doc, trace = engine.run(request_text, on_round_callback=print_round)

    md_output = render_markdown(final_doc)
    console.rule("[bold green]Final Decision Document[/bold green]")
    console.print(md_output)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sample_trace.json").write_text(json.dumps(trace, indent=2), encoding="utf-8")
    (out_dir / "decision_doc.md").write_text(md_output, encoding="utf-8")


if __name__ == "__main__":
    main()

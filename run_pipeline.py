"""
run_pipeline.py — Part 3: The Architect

Reusable prompt iteration pipeline. Given any system prompt + transcript folder,
simulates agent behavior, scores every conversation, and reports aggregate performance.

Usage:
  # Basic run — simulate + score all transcripts against one prompt
  python run_pipeline.py --prompt system-prompt.md --transcripts transcripts/

  # Compare two prompts — shows which performs better
  python run_pipeline.py \
      --prompt system-prompt-fixed.md \
      --baseline system-prompt.md \
      --transcripts transcripts/

  # With auto-suggestions (bonus)
  python run_pipeline.py --prompt system-prompt.md --transcripts transcripts/ --suggest

Options:
  --max-turns N    Max customer turns per call simulation (default: 20)
  --budget X       Hard stop if API cost exceeds X USD (default: 1.00)
  --output DIR     Where to save the report JSON (default: pipeline/results/)
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Add project root to path so pipeline package is importable
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from pipeline.runner import simulate_call, load_prompt_text
from pipeline.scorer import score_simulated_call
from pipeline.report import (
    build_aggregate, build_comparison, save_report,
    print_console_report, calc_cost
)
from pipeline.suggest import generate_suggestions

load_dotenv(ROOT / ".env")

COST_PER_1M_IN = 0.15
COST_PER_1M_OUT = 0.60


def run_prompt(prompt_path: Path, transcript_files: list, client: OpenAI,
               max_turns: int, budget: float, cost_tracker: dict) -> list:
    """
    Simulate + score all transcripts against a single prompt.
    Returns list of per-call score results.
    """
    prompt_text = load_prompt_text(prompt_path)
    results = []

    for tf in transcript_files:
        call_id = tf.stem
        current_cost = calc_cost(cost_tracker)
        if current_cost >= budget:
            print(f"  [STOP] Budget guard hit: ${current_cost:.4f} >= ${budget} — stopping")
            break

        print(f"  [{call_id}] Simulating...", end=" ", flush=True)

        # Step 1: Simulate
        sim_result = simulate_call(tf, prompt_text, client, max_turns, cost_tracker)

        # Step 2: Score
        scored = score_simulated_call(sim_result, prompt_text, client, cost_tracker)

        print(f"score={scored['score']}  disposition={scored['disposition']}  [{scored['verdict'].upper()}]")
        results.append(scored)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Prompt iteration pipeline — simulate + score + compare"
    )
    parser.add_argument("--prompt", required=True,
                        help="Path to system prompt file (.md or .txt)")
    parser.add_argument("--transcripts", required=True,
                        help="Path to folder containing call_*.json transcript files")
    parser.add_argument("--baseline",
                        help="Optional: path to baseline prompt file for comparison")
    parser.add_argument("--suggest", action="store_true",
                        help="Generate auto-suggestions for prompt improvement (bonus)")
    parser.add_argument("--max-turns", type=int, default=20,
                        help="Max customer turns per call simulation (default: 20)")
    parser.add_argument("--budget", type=float, default=1.00,
                        help="Hard stop if API cost exceeds this USD amount (default: 1.00)")
    parser.add_argument("--output", default="pipeline/results",
                        help="Output directory for report JSON (default: pipeline/results/)")
    args = parser.parse_args()

    # Validate inputs
    prompt_path = Path(args.prompt)
    if not prompt_path.exists():
        print(f"ERROR: Prompt file not found: {prompt_path}")
        sys.exit(1)

    transcripts_dir = Path(args.transcripts)
    transcript_files = sorted(transcripts_dir.glob("call_*.json"))
    if not transcript_files:
        print(f"ERROR: No call_*.json files found in {transcripts_dir}")
        sys.exit(1)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set. Create a .env file.")
        sys.exit(1)

    client = OpenAI(api_key=api_key)
    output_dir = Path(args.output)
    cost_tracker = {"input": 0, "output": 0}

    print(f"\n=== Prompt Iteration Pipeline ===")
    print(f"Prompt:      {prompt_path}")
    print(f"Transcripts: {transcripts_dir} ({len(transcript_files)} files)")
    print(f"Max turns:   {args.max_turns}")
    print(f"Budget:      ${args.budget}")
    if args.baseline:
        print(f"Baseline:    {args.baseline}")
    print()

    # ── Run current prompt ────────────────────────────────────────────────────
    print(f"[1/{'3' if args.baseline else '2'}] Running prompt: {prompt_path.name}")
    current_results = run_prompt(
        prompt_path, transcript_files, client,
        args.max_turns, args.budget, cost_tracker
    )

    # ── Run baseline prompt (optional) ───────────────────────────────────────
    comparison = None
    if args.baseline:
        baseline_path = Path(args.baseline)
        if not baseline_path.exists():
            print(f"WARNING: Baseline file not found: {baseline_path} — skipping comparison")
        else:
            baseline_tracker = {"input": 0, "output": 0}
            print(f"\n[2/3] Running baseline: {baseline_path.name}")
            baseline_results = run_prompt(
                baseline_path, transcript_files, client,
                args.max_turns, args.budget, baseline_tracker
            )
            cost_tracker["input"] += baseline_tracker["input"]
            cost_tracker["output"] += baseline_tracker["output"]
            comparison = build_comparison(
                current_results, baseline_results,
                prompt_path.name, baseline_path.name
            )

    # ── Auto-suggest (bonus) ──────────────────────────────────────────────────
    suggestions = None
    if args.suggest:
        step = "3/3" if args.baseline else "2/2"
        print(f"\n[{step}] Generating prompt improvement suggestions...")
        all_worst = []
        for r in current_results:
            for msg in r.get("worst_messages", []):
                msg["call_id"] = r["call_id"]
                all_worst.append(msg)
        prompt_text = load_prompt_text(prompt_path)
        suggestions = generate_suggestions(all_worst, prompt_text, client, cost_tracker)
        print("  Suggestions generated.")

    # ── Print + Save report ───────────────────────────────────────────────────
    cost = calc_cost(cost_tracker)
    print_console_report(prompt_path.name, current_results, cost, comparison)

    saved_path = save_report(
        prompt_path=prompt_path,
        transcripts_dir=transcripts_dir,
        results=current_results,
        cost_tracker=cost_tracker,
        output_dir=output_dir,
        comparison=comparison,
        suggestions=suggestions,
        max_turns=args.max_turns,
    )
    print(f"\nReport saved: {saved_path}")

    if args.suggest and suggestions:
        suggestions_path = saved_path.with_name(
            saved_path.stem.replace("_report", "_suggestions") + ".md"
        )
        suggestions_path.write_text(f"# Prompt Improvement Suggestions\n\n{suggestions}", encoding="utf-8")
        print(f"Suggestions: {suggestions_path}")

    print(f"Total API cost: ${cost:.5f}")


if __name__ == "__main__":
    main()

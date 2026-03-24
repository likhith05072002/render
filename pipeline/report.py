"""
pipeline/report.py — Aggregate stats + console output + report builder.
"""

import json
import statistics
from datetime import datetime
from pathlib import Path


COST_PER_1M_IN = 0.15
COST_PER_1M_OUT = 0.60


def calc_cost(cost_tracker: dict) -> float:
    inp = cost_tracker.get("input", 0)
    out = cost_tracker.get("output", 0)
    return round((inp / 1_000_000 * COST_PER_1M_IN) + (out / 1_000_000 * COST_PER_1M_OUT), 5)


def build_aggregate(results: list) -> dict:
    """Compute aggregate stats from a list of per-call score results."""
    if not results:
        return {}

    scores = [r["score"] for r in results]
    good = [r for r in results if r["verdict"] == "good"]
    bad = [r for r in results if r["verdict"] == "bad"]

    # Per-dimension averages
    dims = ["language_handling", "protocol_adherence", "discovery_quality", "empathy_tone"]
    dim_avgs = {}
    for d in dims:
        vals = [r["score_breakdown"].get(d, 0) for r in results]
        dim_avgs[d] = round(statistics.mean(vals), 1)

    weakest = min(dim_avgs, key=lambda d: dim_avgs[d] / (15 if d in ("language_handling", "protocol_adherence") else 10))
    strongest = max(dim_avgs, key=lambda d: dim_avgs[d] / (15 if d in ("language_handling", "protocol_adherence") else 10))

    return {
        "mean_score": round(statistics.mean(scores), 1),
        "median_score": round(statistics.median(scores), 1),
        "min_score": min(scores),
        "max_score": max(scores),
        "good_count": len(good),
        "bad_count": len(bad),
        "good_pct": round(len(good) / len(results) * 100, 1),
        "dim_averages": dim_avgs,
        "weakest_dimension": weakest,
        "strongest_dimension": strongest,
    }


def build_comparison(current_results: list, baseline_results: list,
                     current_prompt: str, baseline_prompt: str) -> dict:
    """Build comparison delta between two prompt runs."""
    curr_scores = {r["call_id"]: r for r in current_results}
    base_scores = {r["call_id"]: r for r in baseline_results}

    per_call = []
    for call_id in sorted(curr_scores.keys()):
        c = curr_scores.get(call_id, {})
        b = base_scores.get(call_id, {})
        if not c or not b:
            continue
        delta = c["score"] - b["score"]
        flipped = (b["verdict"] == "bad" and c["verdict"] == "good")
        worsened = (b["verdict"] == "good" and c["verdict"] == "bad")
        per_call.append({
            "call_id": call_id,
            "baseline_score": b["score"],
            "current_score": c["score"],
            "delta": delta,
            "baseline_verdict": b["verdict"],
            "current_verdict": c["verdict"],
            "flipped": flipped,
            "worsened": worsened,
        })

    curr_mean = statistics.mean(c["score"] for c in current_results) if current_results else 0
    base_mean = statistics.mean(b["score"] for b in baseline_results) if baseline_results else 0
    delta_mean = round(curr_mean - base_mean, 1)

    flipped_count = sum(1 for p in per_call if p["flipped"])
    worsened_count = sum(1 for p in per_call if p["worsened"])

    if delta_mean > 2:
        verdict = "IMPROVED"
    elif delta_mean < -2:
        verdict = "REGRESSED"
    else:
        verdict = "UNCHANGED"

    return {
        "baseline_prompt": baseline_prompt,
        "current_prompt": current_prompt,
        "baseline_mean": round(base_mean, 1),
        "current_mean": round(curr_mean, 1),
        "delta_mean": delta_mean,
        "verdict": verdict,
        "flipped_to_good": flipped_count,
        "flipped_to_bad": worsened_count,
        "per_call_deltas": per_call,
    }


def save_report(
    prompt_path: Path,
    transcripts_dir: Path,
    results: list,
    cost_tracker: dict,
    output_dir: Path,
    comparison: dict = None,
    suggestions: str = None,
    max_turns: int = 20,
) -> Path:
    """Save a timestamped JSON report to output_dir. Returns the saved path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    prompt_slug = prompt_path.stem.replace(" ", "-")
    out_path = output_dir / f"{timestamp}_{prompt_slug}_report.json"

    report = {
        "meta": {
            "prompt_file": str(prompt_path),
            "transcripts_dir": str(transcripts_dir),
            "timestamp": datetime.now().isoformat(),
            "total_calls": len(results),
            "max_turns_per_call": max_turns,
            "model": "gpt-4o-mini",
            "temperature": 0,
            "total_tokens_input": cost_tracker.get("input", 0),
            "total_tokens_output": cost_tracker.get("output", 0),
            "total_cost_usd": calc_cost(cost_tracker),
            "scoring": "Tier A (50pts rule-based) + Tier B (50pts LLM-judged, dynamic prompt adherence)"
        },
        "aggregate": build_aggregate(results),
        "results": results,
    }
    if comparison:
        report["comparison"] = comparison
    if suggestions:
        report["suggestions"] = suggestions

    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def print_console_report(
    prompt_name: str,
    results: list,
    cost: float,
    comparison: dict = None,
):
    """Print a formatted summary to the console."""
    agg = build_aggregate(results)
    print(f"\n{'='*62}")
    print(f"Pipeline Report: {prompt_name}")
    print(f"{'='*62}")
    print(f"  {'CALL':<10} {'CUSTOMER':<22} {'DISPOSITION':<18} {'SCORE':>5}  VERDICT")
    print(f"  {'-'*60}")
    for r in sorted(results, key=lambda x: x.get("score", 0), reverse=True):
        flag = "+" if r["verdict"] == "good" else "-"
        print(f"  [{flag}] {r['call_id']:<7} {r.get('customer_name','?'):<22} "
              f"{r.get('disposition','?'):<18} {r.get('score',0):>3}   [{r['verdict'].upper()}]")
    print(f"\n  Aggregate: {agg.get('good_count',0)}/{len(results)} good ({agg.get('good_pct',0)}%)"
          f"  |  Mean score: {agg.get('mean_score',0)}/100")
    print(f"  Weakest dimension: {agg.get('weakest_dimension','?')}"
          f"  (avg {agg.get('dim_averages',{}).get(agg.get('weakest_dimension','?'),0)})")
    print(f"  Cost: ${cost:.5f}")

    if comparison:
        c = comparison
        sign = "+" if c["delta_mean"] >= 0 else ""
        print(f"\n  COMPARISON vs {c['baseline_prompt']}:")
        print(f"  Mean: {c['current_mean']} vs {c['baseline_mean']}"
              f"  ({sign}{c['delta_mean']}) — {c['verdict']}")
        if c["flipped_to_good"]:
            print(f"  Verdict improved: {c['flipped_to_good']} call(s) bad -> good")
        if c["flipped_to_bad"]:
            print(f"  Verdict worsened: {c['flipped_to_bad']} call(s) good -> bad")

    print(f"{'='*62}")

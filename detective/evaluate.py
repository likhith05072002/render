"""
detective/evaluate.py — Part 1: Accuracy check against ground truth
Compares predicted verdicts in results.json against the sealed verdicts.json.

IMPORTANT: Only run this AFTER score.py has completed and you're ready to reveal accuracy.
Usage: python detective/evaluate.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
RESULTS_FILE = ROOT / "detective" / "results.json"
VERDICTS_FILE = ROOT / "verdicts.json"


def main():
    # Load predicted results
    if not RESULTS_FILE.exists():
        print("ERROR: detective/results.json not found. Run python detective/score.py first.")
        return

    with open(RESULTS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    predictions = {r["call_id"]: r["verdict"] for r in data["results"]}

    # Load ground truth
    if not VERDICTS_FILE.exists():
        print("ERROR: verdicts.json not found. Run python setup.py first.")
        return

    with open(VERDICTS_FILE, encoding="utf-8") as f:
        verdicts_raw = json.load(f)

    # verdicts.json format: {"instructions": "...", "verdicts": {"call_01": {"verdict": "good", "reason": "..."}, ...}}
    inner = verdicts_raw.get("verdicts", verdicts_raw)
    ground_truth = {}
    for call_id, value in inner.items():
        if isinstance(value, dict):
            ground_truth[call_id] = value.get("verdict", value.get("label", "?"))
        else:
            ground_truth[call_id] = str(value)

    # Compare
    all_calls = sorted(set(list(predictions.keys()) + list(ground_truth.keys())))
    correct = 0
    mismatches = []
    matches = []

    print("=== Part 1: Accuracy Evaluation ===\n")
    print(f"{'Call':<12} {'Predicted':<12} {'Actual':<12} {'Result'}")
    print("-" * 50)

    for call_id in all_calls:
        pred = predictions.get(call_id, "N/A")
        actual = ground_truth.get(call_id, "N/A")

        # Find score for this call
        score_entry = next((r for r in data["results"] if r["call_id"] == call_id), {})
        score = score_entry.get("score", "?")

        if pred == actual:
            correct += 1
            status = "[MATCH]   "
            matches.append(call_id)
        else:
            status = "[MISMATCH]"
            mismatches.append({
                "call_id": call_id,
                "predicted": pred,
                "actual": actual,
                "score": score,
                "reasoning": score_entry.get("reasoning", ""),
            })

        print(f"{call_id:<12} {pred:<12} {actual:<12} {status}  (score={score})")

    total = len(all_calls)
    accuracy = correct / total * 100 if total > 0 else 0

    print(f"\n{'='*50}")
    print(f"Accuracy: {correct}/{total} = {accuracy:.0f}%")
    print(f"{'='*50}")

    if mismatches:
        print(f"\n=== MISMATCHES ({len(mismatches)}) ===")
        for m in mismatches:
            print(f"\n  {m['call_id']} — predicted {m['predicted'].upper()}, actually {m['actual'].upper()} (score={m['score']})")
            if m["reasoning"]:
                print(f"  Reasoning: {m['reasoning']}")

    # Save evaluation to results file
    with open(RESULTS_FILE, encoding="utf-8") as f:
        results_data = json.load(f)

    results_data["evaluation"] = {
        "accuracy_pct": round(accuracy, 1),
        "correct": correct,
        "total": total,
        "mismatches": mismatches,
    }

    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results_data, f, indent=2, ensure_ascii=False)

    print(f"\nEvaluation saved -> {RESULTS_FILE}")

    # Also save a standalone eval report
    eval_path = ROOT / "detective" / "evaluation_report.json"
    with open(eval_path, "w", encoding="utf-8") as f:
        json.dump({
            "accuracy_pct": round(accuracy, 1),
            "correct": correct,
            "total": total,
            "matches": matches,
            "mismatches": mismatches,
        }, f, indent=2)
    print(f"Eval report -> {eval_path}")


if __name__ == "__main__":
    main()

"""
ui/app.py — Flask API server (JSON only, no templates)
React dev server (Vite) proxies /api/* requests here.

Usage: python ui/app.py
Runs on: http://localhost:5000
"""

import json
import os
import sys
import tempfile
import shutil
from pathlib import Path
from flask import Flask, jsonify, abort, request, send_from_directory
from flask_cors import CORS

ROOT = Path(__file__).parent.parent
UI_DIST_DIR = ROOT / "ui" / "dist"
RESULTS_FILE = ROOT / "detective" / "results.json"
TRANSCRIPTS_DIR = ROOT / "transcripts"
SURGEON_RESULTS = ROOT / "surgeon" / "results.json"
SIMULATIONS_DIR = ROOT / "surgeon" / "simulations"
PIPELINE_RESULTS_DIR = ROOT / "pipeline" / "results"
DEFAULT_PROMPT = ROOT / "system-prompt.md"
FIXED_PROMPT = ROOT / "system-prompt-fixed.md"

# Add root to sys.path so pipeline package is importable
sys.path.insert(0, str(ROOT))

app = Flask(__name__, static_folder=str(UI_DIST_DIR), static_url_path="")
CORS(app)


def _get_openai_client():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def load_results():
    if not RESULTS_FILE.exists():
        return None
    with open(RESULTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _validate_transcript(data: dict) -> bool:
    """Check uploaded transcript JSON has minimum required keys."""
    required = {"call_id", "transcript", "customer"}
    return required.issubset(data.keys())


def _build_sim_result_from_transcript(data: dict) -> dict:
    """
    Build a sim_result-compatible dict from an existing transcript JSON.
    Used for Test A (Detective) so we can feed real transcripts into the scorer.
    """
    fn_calls_raw = data.get("function_calls", [])
    # Strip 'turn' field — scorer expects [{function, params}]
    simulated_fn_calls = [
        {"function": fc["function"], "params": fc.get("params", {})}
        for fc in fn_calls_raw
        if "function" in fc
    ]

    # Build transcript in sim format: [{turn, speaker, text, function_calls}]
    simulated_transcript = []
    turn_num = 0
    # Group function calls by turn number for annotation
    fn_by_turn = {}
    for fc in fn_calls_raw:
        t = fc.get("turn")
        if t is not None:
            fn_by_turn.setdefault(t, []).append(fc["function"])

    for i, msg in enumerate(data.get("transcript", [])):
        turn_num = i + 1
        simulated_transcript.append({
            "turn": turn_num,
            "speaker": msg.get("speaker", ""),
            "text": msg.get("text", ""),
            "function_calls": fn_by_turn.get(turn_num, []),
        })

    # Count customer turns
    customer_turns = sum(
        1 for msg in data.get("transcript", [])
        if msg.get("speaker") == "customer"
    )

    return {
        "call_id": data.get("call_id", "?"),
        "customer": data.get("customer", {}),
        "original_disposition": data.get("disposition", "?"),
        "simulated_fn_calls": simulated_fn_calls,
        "inferred_disposition": data.get("disposition", "BLANK_CALL").upper(),
        "inferred_phases": data.get("phases_visited", ["opening"]),
        "customer_turns_used": customer_turns,
        "simulated_transcript": simulated_transcript,
    }


def _score_existing_transcript(data: dict, client, cost_tracker: dict) -> dict:
    """
    Score an already-completed transcript using Tier A + LLM judge.
    Reuses pipeline/scorer.py functions.
    """
    from pipeline.scorer import score_tier_a, call_llm_judge, VERDICT_THRESHOLD

    sim_result = _build_sim_result_from_transcript(data)

    # Load default system prompt for the judge (evaluates against original instructions)
    prompt_text = ""
    if DEFAULT_PROMPT.exists():
        prompt_text = DEFAULT_PROMPT.read_text(encoding="utf-8")

    tier_a = score_tier_a(sim_result)
    llm = call_llm_judge(sim_result, prompt_text, client, cost_tracker)

    llm_total = llm.get("total", 0)
    total_score = tier_a["total"] + llm_total

    disposition = sim_result["inferred_disposition"]
    if disposition == "BLANK_CALL":
        verdict = "bad"
    else:
        verdict = "good" if total_score >= VERDICT_THRESHOLD else "bad"

    return {
        "call_id": sim_result["call_id"],
        "customer_name": sim_result["customer"].get("name", "?"),
        "disposition": disposition,
        "score": total_score,
        "rule_score": tier_a["total"],
        "llm_score": llm_total,
        "verdict": verdict,
        "confidence": llm.get("confidence", 0.5),
        "score_breakdown": {
            **tier_a["breakdown"],
            "language_handling": llm.get("language_handling", 0),
            "protocol_adherence": llm.get("protocol_adherence", 0),
            "discovery_quality": llm.get("discovery_quality", 0),
            "empathy_tone": llm.get("empathy_tone", 0),
        },
        "worst_messages": llm.get("worst_messages", []),
        "reasoning": llm.get("reasoning", ""),
        "phases": sim_result["inferred_phases"],
    }


# ── Existing GET endpoints ────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/results")
def results():
    data = load_results()
    if data is None:
        return jsonify({"error": "No results yet. Run python detective/score.py first."}), 404
    return jsonify(data)


@app.route("/api/transcript/<call_id>")
def transcript(call_id):
    path = TRANSCRIPTS_DIR / f"{call_id}.json"
    if not path.exists():
        abort(404)
    with open(path, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/surgeon/results")
def surgeon_results():
    if not SURGEON_RESULTS.exists():
        return jsonify({"error": "No simulation results yet. Run python surgeon/simulate.py first."}), 404
    with open(SURGEON_RESULTS, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/surgeon/simulation/<call_id>")
def surgeon_simulation(call_id):
    path = SIMULATIONS_DIR / f"{call_id}_comparison.json"
    if not path.exists():
        abort(404)
    with open(path, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/pipeline/latest")
def pipeline_latest():
    if not PIPELINE_RESULTS_DIR.exists():
        return jsonify({"error": "No pipeline results. Run python run_pipeline.py first."}), 404
    reports = sorted(PIPELINE_RESULTS_DIR.glob("*_report.json"), reverse=True)
    if not reports:
        return jsonify({"error": "No pipeline results. Run python run_pipeline.py first."}), 404
    with open(reports[0], encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/pipeline/list")
def pipeline_list():
    if not PIPELINE_RESULTS_DIR.exists():
        return jsonify([])
    reports = sorted(PIPELINE_RESULTS_DIR.glob("*_report.json"), reverse=True)
    result = []
    for r in reports:
        try:
            with open(r, encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("meta", {})
            agg = data.get("aggregate", {})
            result.append({
                "filename": r.name,
                "prompt_file": meta.get("prompt_file", "?"),
                "timestamp": meta.get("timestamp", "?"),
                "mean_score": agg.get("mean_score", 0),
                "good_pct": agg.get("good_pct", 0),
                "total_calls": meta.get("total_calls", 0),
                "has_comparison": "comparison" in data,
                "has_suggestions": "suggestions" in data,
            })
        except Exception:
            pass
    return jsonify(result)


# ── Test Lab POST endpoints ───────────────────────────────────────────────────

MAX_TEST_FILES = 20
TEST_BUDGET = 0.50
MAX_TEST_TURNS = 15


@app.route("/api/test/detective", methods=["POST"])
def test_detective():
    """
    Test A — Score uploaded transcripts using Tier A + LLM judge.
    Accepts: transcripts[] (JSON files), verdicts (optional verdicts.json)
    """
    client = _get_openai_client()
    if not client:
        return jsonify({"error": "OPENAI_API_KEY not configured on server."}), 500

    transcript_files = request.files.getlist("transcripts[]")
    if not transcript_files:
        return jsonify({"error": "No transcript files uploaded."}), 400
    if len(transcript_files) > MAX_TEST_FILES:
        return jsonify({"error": f"Max {MAX_TEST_FILES} transcripts per run."}), 400

    verdicts_file = request.files.get("verdicts")

    tmpdir = tempfile.mkdtemp()
    try:
        from pipeline.scorer import VERDICT_THRESHOLD
        from pipeline.report import build_aggregate, calc_cost

        cost_tracker = {"input": 0, "output": 0}
        results_list = []
        errors = []

        for f in transcript_files:
            try:
                data = json.loads(f.read().decode("utf-8"))
            except Exception:
                errors.append(f"{f.filename}: invalid JSON")
                continue

            if not _validate_transcript(data):
                errors.append(f"{f.filename}: missing required fields (call_id, transcript, customer)")
                continue

            # Budget guard
            if calc_cost(cost_tracker) >= TEST_BUDGET:
                errors.append("Budget limit reached — remaining transcripts skipped.")
                break

            try:
                scored = _score_existing_transcript(data, client, cost_tracker)
                results_list.append(scored)
            except Exception as e:
                errors.append(f"{data.get('call_id', f.filename)}: scoring failed — {str(e)}")

        aggregate = build_aggregate(results_list) if results_list else {}

        # Accuracy evaluation if verdicts.json provided
        evaluation = None
        if verdicts_file and results_list:
            try:
                verdicts_data = json.loads(verdicts_file.read().decode("utf-8"))
                # Support both {call_id: verdict} and list of {call_id, verdict}
                if isinstance(verdicts_data, list):
                    vdict = {v["call_id"]: v.get("verdict", v.get("label", "")) for v in verdicts_data}
                else:
                    vdict = verdicts_data

                correct = 0
                mismatches = []
                total_compared = 0
                for r in results_list:
                    cid = r["call_id"]
                    if cid not in vdict:
                        continue
                    total_compared += 1
                    expected = str(vdict[cid]).lower()
                    predicted = r["verdict"].lower()
                    if predicted == expected:
                        correct += 1
                    else:
                        mismatches.append({
                            "call_id": cid,
                            "expected": expected,
                            "predicted": predicted,
                            "score": r["score"],
                        })

                evaluation = {
                    "accuracy_pct": round(correct / total_compared * 100, 1) if total_compared > 0 else 0,
                    "correct": correct,
                    "total": total_compared,
                    "mismatches": mismatches,
                }
            except Exception as e:
                evaluation = {"error": f"Could not parse verdicts.json: {str(e)}"}

        cost = calc_cost(cost_tracker)
        return jsonify({
            "results": results_list,
            "aggregate": aggregate,
            "evaluation": evaluation,
            "errors": errors,
            "meta": {
                "total_calls": len(results_list),
                "cost_usd": round(cost, 5),
            }
        })

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.route("/api/test/surgeon", methods=["POST"])
def test_surgeon():
    """
    Test B — Simulate transcripts with an uploaded (or default) prompt,
    compare against the fixed prompt as baseline.
    Accepts: transcripts[] (JSON files), prompt (optional system prompt file)
    """
    client = _get_openai_client()
    if not client:
        return jsonify({"error": "OPENAI_API_KEY not configured on server."}), 500

    transcript_files = request.files.getlist("transcripts[]")
    if not transcript_files:
        return jsonify({"error": "No transcript files uploaded."}), 400
    if len(transcript_files) > 10:
        return jsonify({"error": "Max 10 transcripts for simulation."}), 400

    prompt_file = request.files.get("prompt")

    tmpdir = tempfile.mkdtemp()
    try:
        from pipeline.runner import simulate_call, load_prompt_text
        from pipeline.scorer import score_simulated_call
        from pipeline.report import build_aggregate, build_comparison, calc_cost

        # Save uploaded transcripts to temp files
        saved_paths = []
        for f in transcript_files:
            try:
                data = json.loads(f.read().decode("utf-8"))
                if not _validate_transcript(data):
                    continue
                tmp_path = Path(tmpdir) / (data.get("call_id", f.filename) + ".json")
                tmp_path.write_text(json.dumps(data), encoding="utf-8")
                saved_paths.append(tmp_path)
            except Exception:
                continue

        if not saved_paths:
            return jsonify({"error": "No valid transcripts found."}), 400

        # Load prompt text
        if prompt_file:
            prompt_text = prompt_file.read().decode("utf-8")
            prompt_name = prompt_file.filename or "uploaded-prompt.md"
        elif DEFAULT_PROMPT.exists():
            prompt_text = DEFAULT_PROMPT.read_text(encoding="utf-8")
            prompt_name = "system-prompt.md (default)"
        else:
            return jsonify({"error": "No prompt provided and system-prompt.md not found."}), 400

        # Load fixed prompt for comparison
        fixed_text = FIXED_PROMPT.read_text(encoding="utf-8") if FIXED_PROMPT.exists() else None
        fixed_name = "system-prompt-fixed.md"

        cost_tracker = {"input": 0, "output": 0}
        current_results = []
        fixed_results = []

        for tp in saved_paths:
            if calc_cost(cost_tracker) >= TEST_BUDGET:
                break

            try:
                sim = simulate_call(tp, prompt_text, client, MAX_TEST_TURNS, cost_tracker)
                scored = score_simulated_call(sim, prompt_text, client, cost_tracker)
                current_results.append(scored)
            except Exception as e:
                current_results.append({
                    "call_id": tp.stem, "error": str(e), "score": 0, "verdict": "bad"
                })

            if fixed_text and calc_cost(cost_tracker) < TEST_BUDGET:
                try:
                    sim_f = simulate_call(tp, fixed_text, client, MAX_TEST_TURNS, cost_tracker)
                    scored_f = score_simulated_call(sim_f, fixed_text, client, cost_tracker)
                    fixed_results.append(scored_f)
                except Exception:
                    pass

        aggregate = build_aggregate(current_results) if current_results else {}
        comparison = None
        if fixed_results:
            comparison = build_comparison(
                current_results, fixed_results,
                prompt_name, fixed_name
            )

        cost = calc_cost(cost_tracker)
        return jsonify({
            "results": current_results,
            "aggregate": aggregate,
            "comparison": comparison,
            "meta": {
                "prompt_name": prompt_name,
                "total_calls": len(current_results),
                "max_turns": MAX_TEST_TURNS,
                "cost_usd": round(cost, 5),
            }
        })

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.route("/api/test/pipeline", methods=["POST"])
def test_pipeline():
    """
    Test C — Full pipeline: simulate any prompt, optional A/B comparison, auto-suggestions.
    Accepts: prompt (required), baseline (optional), transcripts[] (JSON files)
    """
    client = _get_openai_client()
    if not client:
        return jsonify({"error": "OPENAI_API_KEY not configured on server."}), 500

    transcript_files = request.files.getlist("transcripts[]")
    prompt_file = request.files.get("prompt")
    baseline_file = request.files.get("baseline")

    if not prompt_file:
        return jsonify({"error": "prompt file is required for Test C."}), 400
    if not transcript_files:
        return jsonify({"error": "No transcript files uploaded."}), 400
    if len(transcript_files) > 10:
        return jsonify({"error": "Max 10 transcripts for pipeline test."}), 400

    tmpdir = tempfile.mkdtemp()
    try:
        from pipeline.runner import simulate_call
        from pipeline.scorer import score_simulated_call
        from pipeline.report import build_aggregate, build_comparison, calc_cost
        from pipeline.suggest import generate_suggestions

        prompt_text = prompt_file.read().decode("utf-8")
        prompt_name = prompt_file.filename or "uploaded-prompt.md"

        baseline_text = None
        baseline_name = None
        if baseline_file:
            baseline_text = baseline_file.read().decode("utf-8")
            baseline_name = baseline_file.filename or "baseline-prompt.md"

        # Save uploaded transcripts
        saved_paths = []
        for f in transcript_files:
            try:
                raw = f.read().decode("utf-8")
                data = json.loads(raw)
                if not _validate_transcript(data):
                    continue
                tp = Path(tmpdir) / (data.get("call_id", f.filename) + ".json")
                tp.write_text(raw, encoding="utf-8")
                saved_paths.append(tp)
            except Exception:
                continue

        if not saved_paths:
            return jsonify({"error": "No valid transcripts found."}), 400

        cost_tracker = {"input": 0, "output": 0}
        current_results = []
        baseline_results = []

        # Run current prompt
        for tp in saved_paths:
            if calc_cost(cost_tracker) >= TEST_BUDGET:
                break
            try:
                sim = simulate_call(tp, prompt_text, client, MAX_TEST_TURNS, cost_tracker)
                scored = score_simulated_call(sim, prompt_text, client, cost_tracker)
                current_results.append(scored)
            except Exception as e:
                current_results.append({
                    "call_id": tp.stem, "error": str(e), "score": 0, "verdict": "bad"
                })

        # Run baseline if provided
        if baseline_text:
            for tp in saved_paths:
                if calc_cost(cost_tracker) >= TEST_BUDGET:
                    break
                try:
                    sim_b = simulate_call(tp, baseline_text, client, MAX_TEST_TURNS, cost_tracker)
                    scored_b = score_simulated_call(sim_b, baseline_text, client, cost_tracker)
                    baseline_results.append(scored_b)
                except Exception:
                    pass

        aggregate = build_aggregate(current_results) if current_results else {}
        comparison = None
        if baseline_results:
            comparison = build_comparison(
                current_results, baseline_results,
                prompt_name, baseline_name
            )

        # Auto-suggestions
        suggestions = None
        all_worst = []
        for r in current_results:
            for msg in r.get("worst_messages", []):
                msg["call_id"] = r["call_id"]
                all_worst.append(msg)
        if all_worst and calc_cost(cost_tracker) < TEST_BUDGET:
            try:
                suggestions = generate_suggestions(all_worst, prompt_text, client, cost_tracker)
            except Exception:
                pass

        cost = calc_cost(cost_tracker)
        return jsonify({
            "results": current_results,
            "aggregate": aggregate,
            "comparison": comparison,
            "suggestions": suggestions,
            "meta": {
                "prompt_name": prompt_name,
                "baseline_name": baseline_name,
                "total_calls": len(current_results),
                "max_turns": MAX_TEST_TURNS,
                "cost_usd": round(cost, 5),
            }
        })

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def frontend(path):
    """
    Serve the built React frontend in production.
    Non-API routes fall back to index.html for client-side routing.
    """
    if path.startswith("api/"):
        abort(404)

    if not UI_DIST_DIR.exists():
        return jsonify({
            "error": "UI build not found. Run `cd ui && npm run build` before serving the frontend."
        }), 404

    target = UI_DIST_DIR / path
    if path and target.exists() and target.is_file():
        return send_from_directory(UI_DIST_DIR, path)

    return send_from_directory(UI_DIST_DIR, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"API server running at http://localhost:{port}")
    app.run(debug=True, host="0.0.0.0", port=port)

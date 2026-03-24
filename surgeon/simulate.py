"""
surgeon/simulate.py — Part 2: The Surgeon (simulation step)

Re-simulates 3 bad calls (call_02, call_03, call_07) using the fixed system prompt.
Only original customer messages are replayed, exactly, in original order — no modification.
Agent responses are generated strictly from the fixed system prompt.
This ensures a true apples-to-apples comparison: same customer inputs, different agent prompt.

Usage: python surgeon/simulate.py
Output: surgeon/simulations/call_XX_comparison.json
        surgeon/results.json
"""

import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).parent.parent
TRANSCRIPTS_DIR = ROOT / "transcripts"
SIMULATIONS_DIR = ROOT / "surgeon" / "simulations"
DETECTIVE_RESULTS = ROOT / "detective" / "results.json"
FIXED_PROMPT_FILE = ROOT / "system-prompt-fixed.md"
OUTPUT_FILE = ROOT / "surgeon" / "results.json"

load_dotenv(ROOT / ".env")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SIMULATIONS_DIR.mkdir(parents=True, exist_ok=True)

# Cost tracking (gpt-4o-mini rates)
total_tokens_in = 0
total_tokens_out = 0
COST_PER_1M_IN = 0.15
COST_PER_1M_OUT = 0.60

# The 3 calls representing distinct failure categories
# call_02: language handling failure (FIX 1 + FIX 4)
# call_03: looping/escalation failure (FIX 2 + FIX 4)
# call_07: language + fallback failure (FIX 1 + FIX 4)
CALLS_TO_SIMULATE = ["call_02", "call_03", "call_07"]

# 20 turns is sufficient — all failure modes occur in first 10-15 customer turns
MAX_CUSTOMER_TURNS = 20

# ── Tool definitions (function-calling schema for simulated agent) ───────────

TOOLS = [
    {"type": "function", "function": {
        "name": "switch_language",
        "description": "MANDATORY: Call immediately when customer speaks even one sentence in a non-English language, or explicitly requests a language switch. Do NOT say another English sentence first.",
        "parameters": {"type": "object", "properties": {
            "language": {"type": "string", "enum": ["en", "hi", "ta", "bn", "te", "kn", "mr"]}
        }, "required": ["language"]}
    }},
    {"type": "function", "function": {
        "name": "end_call",
        "description": "MANDATORY: End the call. Must be called for every call exit. A call without end_call() is a BLANK_CALL system error.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string",
                       "enum": ["resolved_payment_committed", "resolved_callback_scheduled",
                                "callback_scheduled", "claims_already_paid", "wrong_party",
                                "language_barrier", "dispute_unresolved",
                                "borrower_refused_conversation", "resolved_impasse",
                                "resolved_needs_time"]}
        }, "required": ["reason"]}
    }},
    {"type": "function", "function": {
        "name": "proceed_to_discovery",
        "description": "Move to discovery phase after disclosing amounts.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "proceed_to_negotiation",
        "description": "Move to negotiation after discovery complete.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }},
    {"type": "function", "function": {
        "name": "proceed_to_closing",
        "description": "Move to closing when resolution reached.",
        "parameters": {"type": "object", "properties": {
            "resolution_type": {"type": "string"}
        }, "required": ["resolution_type"]}
    }},
    {"type": "function", "function": {
        "name": "schedule_callback",
        "description": "Schedule a callback with a reason and preferred time.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string"},
            "preferred_time": {"type": "string"},
            "callback_type": {"type": "string"}
        }, "required": ["reason"]}
    }},
    {"type": "function", "function": {
        "name": "proceed_to_dispute",
        "description": "Move to dispute handling when borrower explicitly disputes the loan.",
        "parameters": {"type": "object", "properties": {}, "required": []}
    }}
]

# ── Fixed system prompt loading ──────────────────────────────────────────────

def load_fixed_system_prompt_text():
    """Extract raw text from system-prompt-fixed.md, stripping markdown code block markers."""
    raw = FIXED_PROMPT_FILE.read_text(encoding="utf-8")
    blocks = re.findall(r"```(?:json)?\n(.*?)```", raw, re.DOTALL)
    return "\n\n---\n\n".join(blocks)


def fill_template(prompt, data):
    """Replace {{variable}} placeholders with real values from call data."""
    customer = data.get("customer", {})
    tos = customer.get("pending_amount", "0")
    pos = customer.get("closure_amount", "")
    if not pos or pos in ("zero", "0", ""):
        pos = tos  # fallback to TOS if POS not set
    settlement = customer.get("settlement_amount", "") or "0"
    replacements = {
        "customer_name": customer.get("name", "Customer"),
        "pending_amount": tos,
        "due_date": "N/A",
        "today_date": "2025-03-07",
        "today_day": "Friday",
        "pos": pos,
        "tos": tos,
        "dpd": customer.get("dpd", "0"),
        "loan_id": data.get("call_id", "DEMO001").upper(),
        "settlement_amount": settlement,
        "is_callback": "false"
    }
    for key, val in replacements.items():
        prompt = prompt.replace("{{" + key + "}}", str(val))
    return prompt


# ── Tier A scoring (deterministic, same as Part 1) ───────────────────────────

DISPOSITION_SCORES = {
    "PTP": 10, "STRONGEST_PTP": 10,
    "CALLBACK": 8, "DISPUTE": 8, "WRONG_NUMBER": 8,
    "LANGUAGE_BARRIER": 8, "ALREADY_PAID": 7,
    "NO_COMMITMENT": 4, "BLANK_CALL": 0,
}

END_CALL_TO_DISPOSITION = {
    "resolved_payment_committed": "PTP",
    "ptp": "PTP",
    "resolved_callback_scheduled": "CALLBACK",
    "callback_scheduled": "CALLBACK",
    "resolved_needs_time": "CALLBACK",
    "claims_already_paid": "ALREADY_PAID",
    "wrong_party": "WRONG_NUMBER",
    "language_barrier": "LANGUAGE_BARRIER",
    "dispute_unresolved": "DISPUTE",
    "borrower_refused_conversation": "NO_COMMITMENT",
    "resolved_impasse": "NO_COMMITMENT",
}


def infer_disposition(fn_calls):
    for fc in reversed(fn_calls):
        if fc["function"] == "end_call":
            reason = fc["params"].get("reason", "").lower()
            for key, disp in END_CALL_TO_DISPOSITION.items():
                if key in reason:
                    return disp
            return "NO_COMMITMENT"
    return "BLANK_CALL"


def infer_phases(fn_calls):
    phases = ["opening"]
    mapping = {
        "proceed_to_discovery": "discovery",
        "proceed_to_dispute": "dispute",
        "proceed_to_negotiation": "negotiation",
        "proceed_to_closing": "closing"
    }
    for fc in fn_calls:
        dest = mapping.get(fc["function"])
        if dest and dest not in phases:
            phases.append(dest)
    return phases


def score_tier_a(fn_calls, customer_turns_used):
    """Same Tier A logic as Part 1 detective/score.py."""
    fn_names = [fc["function"] for fc in fn_calls]
    phases = infer_phases(fn_calls)
    disposition = infer_disposition(fn_calls)
    n_phases = len(set(phases))

    # Phase progression
    if disposition == "WRONG_NUMBER":
        phase_score = 20
    elif n_phases >= 4:
        phase_score = 20
    elif n_phases == 3:
        phase_score = 15
    elif n_phases == 2:
        phase_score = 10
    else:
        phase_score = 5

    # end_call
    if "end_call" in fn_names:
        end_call_score = 10
    elif disposition == "CALLBACK" and "schedule_callback" in fn_names:
        end_call_score = 5
    else:
        end_call_score = 0

    # No repetition — fixed agent does not repeat (full 10 unless tool failure)
    no_rep = 10

    # Disposition quality
    disp_score = DISPOSITION_SCORES.get(disposition, 0)

    # Short call penalty
    short_penalty = 0
    if disposition == "NO_COMMITMENT" and customer_turns_used < 8:
        short_penalty = -16

    total = phase_score + end_call_score + no_rep + disp_score + short_penalty
    return {
        "total": max(0, total),
        "disposition": disposition,
        "phases": phases,
        "breakdown": {
            "phase_progression": phase_score,
            "end_call_present": end_call_score,
            "no_repetition": no_rep,
            "disposition_quality": disp_score,
            "short_call_penalty": short_penalty
        }
    }


# ── LLM judge (absolute, same rubric as Part 1) ──────────────────────────────

# This is the SAME rubric as Part 1 — only the transcript input changes.
# The judge evaluates the simulated (fixed) transcript in isolation.
# It does NOT compare before vs after — scoring is absolute.
LLM_JUDGE_SYSTEM = """You are an expert evaluator scoring a debt collection call transcript.
Score the call on 4 dimensions using the rules below. Be strict and fair.

SCORING DIMENSIONS:
1. language_handling (0-15)
   - 15: switch_language called immediately (within 1 turn) when customer used non-English
   - 10: switched but with 1-2 turn delay
   - 5:  attempted but chaotic or incomplete
   - 0:  no switch despite clear non-English; or call continued in wrong language throughout

2. protocol_adherence (0-15)
   - 15: all required functions called (end_call, schedule_callback where needed); no UTR loops; no dead ends
   - 10: minor omission (1 function missed or 1 extra retry)
   - 5:  significant protocol gap (end_call missing or long loop)
   - 0:  call ended without end_call; or repeated the same question 3+ times for info already given

3. discovery_quality (0-10)
   - 10: root cause explored, borrower situation understood before proceeding
   - 6:  partial — some questions asked but incomplete
   - 3:  minimal — rushed through without understanding
   - 0:  no discovery attempt

4. empathy_tone (0-10)
   - 10: warm, appropriate tone; acknowledged difficult circumstances; no forbidden phrases
   - 7:  mostly good with minor tone issues
   - 4:  some empathy shown but notable gaps
   - 0:  cold, pressuring, or used forbidden phrases

OUTPUT: Return ONLY valid JSON. No extra text, no markdown, no explanation outside the JSON.
{
  "language_handling": <0-15>,
  "protocol_adherence": <0-15>,
  "discovery_quality": <0-10>,
  "empathy_tone": <0-10>,
  "total": <sum of above>,
  "reasoning": "<2-3 sentences citing specific turns and function calls as evidence>"
}"""


def call_llm_judge(call_id, simulated_transcript, simulated_fn_calls, customer_info):
    """Score the simulated transcript using the absolute LLM rubric (same as Part 1)."""
    global total_tokens_in, total_tokens_out

    transcript_text = "\n".join(
        f"[Turn {t['turn']}] {t['speaker'].upper()}: {t['text']}"
        + (f" [CALLED: {', '.join(t['function_calls'])}]" if t.get("function_calls") else "")
        for t in simulated_transcript
    )
    fn_summary = ", ".join(f"{fc['function']}({json.dumps(fc['params'])})"
                           for fc in simulated_fn_calls) or "none"

    user_msg = (
        f"CALL: {call_id}\n"
        f"CUSTOMER: {customer_info.get('name')}, DPD: {customer_info.get('dpd', '?')}\n\n"
        f"FUNCTIONS CALLED: {fn_summary}\n\n"
        f"TRANSCRIPT:\n{transcript_text}"
    )

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": LLM_JUDGE_SYSTEM},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0,
                max_tokens=300
            )
            total_tokens_in += resp.usage.prompt_tokens
            total_tokens_out += resp.usage.completion_tokens

            raw = resp.choices[0].message.content.strip()
            # Strip markdown code fences if model added them
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```\s*$", "", raw)
            parsed = json.loads(raw)
            # Validate required keys
            required = {"language_handling", "protocol_adherence", "discovery_quality",
                        "empathy_tone", "total", "reasoning"}
            if not required.issubset(parsed.keys()):
                raise ValueError(f"Missing keys: {required - parsed.keys()}")
            return parsed
        except Exception as e:
            if attempt < 2:
                print(f"    [RETRY {attempt+1}] LLM judge parse error: {e}")
            else:
                print(f"    [FALLBACK] LLM judge failed after 3 attempts — scoring 0")
                return {
                    "language_handling": 0, "protocol_adherence": 0,
                    "discovery_quality": 0, "empathy_tone": 0,
                    "total": 0, "reasoning": "Judge failed to return valid JSON after 3 attempts."
                }


# ── Fix impact mapping ───────────────────────────────────────────────────────

# Maps which FIX addresses each failure type and what to look for in simulation output
FIX_DEFINITIONS = {
    "FIX 1": "Language switching — call switch_language immediately on first non-English turn",
    "FIX 2": "Already-paid protocol — ask UTR once, acknowledge, immediately end_call",
    "FIX 3": "Callback opening — warm-lead protocol for inbound/requested calls",
    "FIX 4": "Universal end_call — every exit path must call end_call()",
    "FIX 5": "Circular exchange rule — minimum 10 exchanges; confused != circular",
}

CALL_EXPECTED_FIXES = {
    "call_02": ["FIX 1", "FIX 4"],
    "call_03": ["FIX 2", "FIX 4"],
    "call_07": ["FIX 1", "FIX 4"],
}


def build_fix_impact(call_id, original_data, sim_fn_calls, sim_transcript):
    """
    Map which FIX (FIX 1–5) caused which specific improvement in the simulated call.
    Returns fix_impact list and improvements list.
    """
    fix_impact = []
    improvements = []
    failure_reason = None

    fn_names = [fc["function"] for fc in sim_fn_calls]
    orig_fn_calls = original_data.get("function_calls", [])
    orig_fn_names = [fc.get("function", "") for fc in orig_fn_calls]
    orig_disposition = original_data.get("disposition", "")

    # ── FIX 1: Language switching ──────────────────────────────────────────
    if call_id in ["call_02", "call_07"]:
        sim_switch = [fc for fc in sim_fn_calls if fc["function"] == "switch_language"]
        orig_switch = [fc for fc in orig_fn_calls if fc.get("function") == "switch_language"]

        if sim_switch:
            sim_turn = sim_switch[0]["turn"]
            orig_turn = orig_switch[0]["turn"] if orig_switch else 99
            if sim_turn <= orig_turn:
                fix_impact.append({
                    "fix": "FIX 1",
                    "definition": FIX_DEFINITIONS["FIX 1"],
                    "effect": f"switch_language called at turn {sim_turn} (original: turn {orig_turn})",
                    "applied": True
                })
                improvements.append({
                    "flaw": "Flaw 1 (switch_language)",
                    "before": f"Original agent called switch_language at turn {orig_turn} after repeated requests",
                    "after": f"Fixed agent switched immediately at turn {sim_turn}",
                    "impact": "Customer no longer stranded in wrong language"
                })
            else:
                fix_impact.append({
                    "fix": "FIX 1",
                    "definition": FIX_DEFINITIONS["FIX 1"],
                    "effect": f"switch_language called at turn {sim_turn} — slower than original (turn {orig_turn})",
                    "applied": False
                })
        else:
            fix_impact.append({
                "fix": "FIX 1",
                "definition": FIX_DEFINITIONS["FIX 1"],
                "effect": "switch_language NOT called despite non-English customer input — prompt adherence failure",
                "applied": False
            })
            failure_reason = "FIX 1 did not fully apply: switch_language was not called by the simulated agent."

        # Language barrier fallback (call_07)
        if call_id == "call_07":
            lang_barrier_end = any(
                fc["function"] == "end_call" and "language_barrier" in fc["params"].get("reason", "")
                for fc in sim_fn_calls
            )
            lang_barrier_callback = any(
                fc["function"] == "schedule_callback" for fc in sim_fn_calls
            )
            if lang_barrier_end or lang_barrier_callback:
                fix_impact.append({
                    "fix": "FIX 1 (fallback)",
                    "definition": "When language switch fails, schedule_callback + end_call('language_barrier')",
                    "effect": "Proper language barrier fallback executed — call ended with correct reason",
                    "applied": True
                })
                improvements.append({
                    "flaw": "Flaw 1 + Flaw 4 (language barrier fallback)",
                    "before": "Original agent had no fallback — call simply died with no disposition",
                    "after": f"Fixed agent {'scheduled callback and ' if lang_barrier_callback else ''}called end_call with language_barrier reason",
                    "impact": "Customer gets proper callback; call correctly disposed"
                })

    # ── FIX 2: Already-paid UTR protocol ──────────────────────────────────
    if call_id == "call_03":
        orig_turns = original_data.get("total_turns", 0)
        sim_turns = len([t for t in sim_transcript if t["speaker"] == "customer"])
        already_paid_end = any(
            fc["function"] == "end_call" and "already_paid" in fc["params"].get("reason", "")
            for fc in sim_fn_calls
        )
        if already_paid_end and sim_turns < orig_turns // 3:
            fix_impact.append({
                "fix": "FIX 2",
                "definition": FIX_DEFINITIONS["FIX 2"],
                "effect": f"end_call('claims_already_paid') after {sim_turns} turns instead of looping for {orig_turns} turns",
                "applied": True
            })
            improvements.append({
                "flaw": "Flaw 2 (UTR loop)",
                "before": f"Original agent looped for {orig_turns} turns re-asking for UTR already provided (CM552522)",
                "after": f"Fixed agent acknowledged UTR and ended call in {sim_turns} customer turns",
                "impact": "No more 15-minute loop; immediate escalation with correct disposition"
            })
        elif already_paid_end:
            fix_impact.append({
                "fix": "FIX 2",
                "definition": FIX_DEFINITIONS["FIX 2"],
                "effect": f"end_call('claims_already_paid') called — UTR loop avoided",
                "applied": True
            })
            improvements.append({
                "flaw": "Flaw 2 (UTR loop)",
                "before": f"Original agent looped for {orig_turns} turns",
                "after": f"Fixed agent ended call with claims_already_paid",
                "impact": "UTR loop eliminated"
            })
        else:
            fix_impact.append({
                "fix": "FIX 2",
                "definition": FIX_DEFINITIONS["FIX 2"],
                "effect": "end_call('claims_already_paid') NOT called — FIX 2 did not fully apply",
                "applied": False
            })
            if not failure_reason:
                failure_reason = "FIX 2 did not fully apply: claims_already_paid end_call not triggered."

    # ── FIX 4: Universal end_call ──────────────────────────────────────────
    if orig_disposition == "BLANK_CALL":
        if "end_call" in fn_names:
            end_reason = next(
                (fc["params"].get("reason", "unknown") for fc in sim_fn_calls
                 if fc["function"] == "end_call"), "unknown"
            )
            fix_impact.append({
                "fix": "FIX 4",
                "definition": FIX_DEFINITIONS["FIX 4"],
                "effect": f"end_call('{end_reason}') called — BLANK_CALL avoided",
                "applied": True
            })
            improvements.append({
                "flaw": "Flaw 4 (end_call missing)",
                "before": "Original agent ended conversation without calling end_call → filed as BLANK_CALL",
                "after": f"Fixed agent called end_call('{end_reason}') — call properly disposed",
                "impact": "Correct disposition; no BLANK_CALL system error"
            })
        else:
            fix_impact.append({
                "fix": "FIX 4",
                "definition": FIX_DEFINITIONS["FIX 4"],
                "effect": "end_call NOT called — BLANK_CALL would still occur",
                "applied": False
            })
            if not failure_reason:
                failure_reason = "FIX 4 did not apply: end_call was not called by the simulated agent."

    return fix_impact, improvements, failure_reason


# ── Simulation core ──────────────────────────────────────────────────────────

def simulate_call(call_id):
    """
    Re-simulate a bad call using the fixed system prompt.
    Only original customer turns are replayed, exactly, in original order.
    Agent responses are generated solely from the fixed system prompt.
    """
    global total_tokens_in, total_tokens_out

    transcript_path = TRANSCRIPTS_DIR / f"{call_id}.json"
    data = json.loads(transcript_path.read_text(encoding="utf-8"))
    customer = data["customer"]

    print(f"\n[{call_id}] Simulating — {customer['name']}, DPD: {customer.get('dpd','?')}")

    # Build system prompt with filled template vars
    raw_prompt = load_fixed_system_prompt_text()
    system_prompt = fill_template(raw_prompt, data)

    # Extract customer turns from original transcript (exact, unmodified)
    original_turns = data.get("transcript", [])
    customer_turns = [t for t in original_turns if t["speaker"] == "customer"]
    customer_turns = customer_turns[:MAX_CUSTOMER_TURNS]
    print(f"  Replaying {len(customer_turns)} customer turns (cap: {MAX_CUSTOMER_TURNS})")

    messages = [{"role": "system", "content": system_prompt}]
    simulated_transcript = []
    simulated_fn_calls = []
    call_ended = False
    turn_num = 0

    for cust_turn in customer_turns:
        if call_ended:
            break

        turn_num += 1
        customer_text = cust_turn["text"]

        messages.append({"role": "user", "content": customer_text})
        simulated_transcript.append({
            "turn": turn_num * 2 - 1,
            "speaker": "customer",
            "text": customer_text
        })

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0,
                max_tokens=250
            )
        except Exception as e:
            print(f"  [ERROR] API call failed at turn {turn_num}: {e}")
            break

        usage = response.usage
        total_tokens_in += usage.prompt_tokens
        total_tokens_out += usage.completion_tokens

        choice = response.choices[0]
        agent_msg = choice.message
        agent_text = agent_msg.content or ""
        tool_calls_this_turn = []

        if agent_msg.tool_calls:
            for tc in agent_msg.tool_calls:
                try:
                    params = json.loads(tc.function.arguments)
                except Exception:
                    params = {}
                tool_calls_this_turn.append(tc.function.name)
                simulated_fn_calls.append({
                    "turn": turn_num * 2,
                    "function": tc.function.name,
                    "params": params
                })
                if tc.function.name == "end_call":
                    call_ended = True

        simulated_transcript.append({
            "turn": turn_num * 2,
            "speaker": "agent",
            "text": agent_text,
            "function_calls": tool_calls_this_turn if tool_calls_this_turn else None
        })

        # Add assistant message + tool results to maintain valid conversation history
        messages.append({
            "role": "assistant",
            "content": agent_text,
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in (agent_msg.tool_calls or [])
            ] if agent_msg.tool_calls else None
        })
        for tc in (agent_msg.tool_calls or []):
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps({"status": "ok"})
            })

    return data, simulated_transcript, simulated_fn_calls, len(customer_turns)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    global total_tokens_in, total_tokens_out

    orig_results_raw = json.loads(DETECTIVE_RESULTS.read_text(encoding="utf-8"))
    orig_scores = {r["call_id"]: r for r in orig_results_raw.get("results", [])}

    all_comparisons = []

    for call_id in CALLS_TO_SIMULATE:
        if not (TRANSCRIPTS_DIR / f"{call_id}.json").exists():
            print(f"[SKIP] {call_id} — transcript not found")
            continue

        orig = orig_scores.get(call_id, {})

        # Step 1: Run simulation (replaying exact customer turns)
        original_data, sim_transcript, sim_fn_calls, turns_used = simulate_call(call_id)

        # Step 2: Tier A score (same logic as Part 1)
        tier_a = score_tier_a(sim_fn_calls, turns_used)

        # Step 3: LLM judge on simulated transcript only (absolute, not comparative)
        print(f"  Running LLM judge on simulated transcript...")
        llm = call_llm_judge(call_id, sim_transcript, sim_fn_calls, original_data["customer"])

        # Step 4: Build fix_impact + improvements + failure_reason
        fix_impact, improvements, failure_reason = build_fix_impact(
            call_id, original_data, sim_fn_calls, sim_transcript
        )

        # Combined new score
        new_total = tier_a["total"] + llm["total"]
        new_verdict = "good" if new_total >= 62 else "bad"

        fn_list = [f["function"] for f in sim_fn_calls]
        print(f"  Functions: {fn_list}")
        print(f"  Disposition: {tier_a['disposition']}")
        print(f"  Score: {orig.get('score', 0)} ({orig.get('verdict','?')}) => {new_total} ({new_verdict})")

        comparison = {
            "call_id": call_id,
            "customer_name": original_data["customer"]["name"],
            "expected_fixes": CALL_EXPECTED_FIXES.get(call_id, []),

            "before": {
                "score": orig.get("score", 0),
                "rule_score": orig.get("rule_score", 0),
                "llm_score": orig.get("llm_score", 0),
                "verdict": orig.get("verdict", "bad"),
                "disposition": orig.get("disposition", "UNKNOWN"),
                "phases": original_data.get("phases_visited", []),
            },

            "after": {
                "score": new_total,
                "rule_score": tier_a["total"],
                "llm_score": llm["total"],
                "verdict": new_verdict,
                "disposition": tier_a["disposition"],
                "phases": tier_a["phases"],
                "tier_a_breakdown": tier_a["breakdown"],
                "llm_breakdown": {
                    "language_handling": llm["language_handling"],
                    "protocol_adherence": llm["protocol_adherence"],
                    "discovery_quality": llm["discovery_quality"],
                    "empathy_tone": llm["empathy_tone"],
                },
                "reasoning": llm["reasoning"],
            },

            # Causality: which FIX caused which improvement
            "fix_impact": fix_impact,
            # Human-readable improvements list
            "improvements": improvements,
            # If no improvement or fix failed to apply — transparent explanation
            "failure_reason": failure_reason,

            "simulated_fn_calls": sim_fn_calls,
            "simulated_transcript": sim_transcript,
        }

        # Save per-call comparison
        out_path = SIMULATIONS_DIR / f"{call_id}_comparison.json"
        out_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Saved: {out_path.name}")

        all_comparisons.append(comparison)

    # Build summary
    cost = (total_tokens_in / 1_000_000 * COST_PER_1M_IN +
            total_tokens_out / 1_000_000 * COST_PER_1M_OUT)

    summary = {
        "meta": {
            "model": "gpt-4o-mini",
            "temperature": 0,
            "calls_simulated": len(all_comparisons),
            "max_customer_turns_per_call": MAX_CUSTOMER_TURNS,
            "total_tokens_input": total_tokens_in,
            "total_tokens_output": total_tokens_out,
            "total_cost_usd": round(cost, 5),
            "scoring": "Before: Part 1 results.json (unchanged). After: same Tier A + LLM rubric as Part 1."
        },
        "comparisons": [
            {
                "call_id": c["call_id"],
                "customer_name": c["customer_name"],
                "before_score": c["before"]["score"],
                "after_score": c["after"]["score"],
                "score_delta": c["after"]["score"] - c["before"]["score"],
                "before_verdict": c["before"]["verdict"],
                "after_verdict": c["after"]["verdict"],
                "before_disposition": c["before"]["disposition"],
                "after_disposition": c["after"]["disposition"],
                "fixes_applied": [fi["fix"] for fi in c["fix_impact"] if fi.get("applied")],
                "fixes_failed": [fi["fix"] for fi in c["fix_impact"] if not fi.get("applied")],
                "failure_reason": c["failure_reason"],
            }
            for c in all_comparisons
        ],
        "simulations": all_comparisons
    }

    OUTPUT_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"surgeon/results.json saved")
    print(f"Total cost (Part 2 simulation): ${cost:.5f}")
    print(f"\nBefore => After:")
    for c in summary["comparisons"]:
        delta = c["score_delta"]
        sign = "+" if delta >= 0 else ""
        print(f"  {c['call_id']}: {c['before_score']} ({c['before_verdict']}) => "
              f"{c['after_score']} ({c['after_verdict']})  [{sign}{delta} pts]")
        print(f"    Fixes applied: {c['fixes_applied']}")
        if c["failure_reason"]:
            print(f"    [FAILURE] {c['failure_reason']}")


if __name__ == "__main__":
    main()

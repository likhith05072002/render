"""
pipeline/runner.py — Single-call simulation engine.

Given any system prompt text + a transcript file, replays customer turns through
GPT and captures the new agent's responses + function calls.

This is prompt-agnostic: works with any .md/.txt system prompt, not just the
ones written for this project.
"""

import json
import re
from pathlib import Path
from openai import OpenAI

# ── Tools available to the simulated agent ──────────────────────────────────
TOOLS = [
    {"type": "function", "function": {
        "name": "switch_language",
        "description": "MANDATORY: Call immediately when customer speaks even one sentence in a non-English language, or explicitly requests a language switch.",
        "parameters": {"type": "object", "properties": {
            "language": {"type": "string", "enum": ["en", "hi", "ta", "bn", "te", "kn", "mr"]}
        }, "required": ["language"]}
    }},
    {"type": "function", "function": {
        "name": "end_call",
        "description": "MANDATORY: End the call with a reason. Must be called for every call exit.",
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string"}
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
        "description": "Schedule a callback.",
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

# ── Disposition inference ─────────────────────────────────────────────────────

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


def infer_disposition(fn_calls: list) -> str:
    for fc in reversed(fn_calls):
        if fc["function"] == "end_call":
            reason = fc["params"].get("reason", "").lower()
            for key, disp in END_CALL_TO_DISPOSITION.items():
                if key in reason:
                    return disp
            return "NO_COMMITMENT"
    return "BLANK_CALL"


def infer_phases(fn_calls: list) -> list:
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


# ── Template filling ─────────────────────────────────────────────────────────

def fill_template(prompt_text: str, call_data: dict) -> str:
    """Replace {{variable}} placeholders in a system prompt with real call values."""
    customer = call_data.get("customer", {})
    tos = customer.get("pending_amount", "0")
    pos = customer.get("closure_amount", "")
    if not pos or pos in ("zero", "0", ""):
        pos = tos
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
        "loan_id": call_data.get("call_id", "DEMO001").upper(),
        "settlement_amount": settlement,
        "is_callback": "false",
        "bank_name": "DemoLender",
        "agent_name": "Alex",
        "lender_name": "DEMO_LENDER",
    }
    for key, val in replacements.items():
        prompt_text = prompt_text.replace("{{" + key + "}}", str(val))
    return prompt_text


def load_prompt_text(prompt_path: Path) -> str:
    """
    Load a system prompt file. If it's a markdown file with code blocks,
    extract the content from inside the code blocks. Otherwise use as-is.
    """
    raw = prompt_path.read_text(encoding="utf-8")
    # If the file contains markdown code blocks, extract their contents
    blocks = re.findall(r"```(?:json)?\n(.*?)```", raw, re.DOTALL)
    if blocks:
        return "\n\n---\n\n".join(blocks)
    return raw


# ── Simulation core ─────────────────────────────────────────────────────────

def simulate_call(
    transcript_path: Path,
    prompt_text: str,
    client: OpenAI,
    max_turns: int = 20,
    cost_tracker: dict = None,
) -> dict:
    """
    Simulate a single call by replaying exact customer turns through GPT
    using the provided system prompt.

    Returns a dict with:
      - call_id, customer
      - simulated_transcript: list of {turn, speaker, text, function_calls}
      - simulated_fn_calls: list of {turn, function, params}
      - inferred_disposition: string
      - inferred_phases: list of strings
      - customer_turns_used: int
    """
    call_data = json.loads(transcript_path.read_text(encoding="utf-8"))
    call_id = call_data.get("call_id", transcript_path.stem)
    customer = call_data.get("customer", {})

    # Fill template variables for this specific call
    system_prompt = fill_template(prompt_text, call_data)

    # Extract customer turns only (exact, unmodified)
    all_turns = call_data.get("transcript", [])
    customer_turns = [t for t in all_turns if t["speaker"] == "customer"][:max_turns]

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
                max_tokens=250,
            )
        except Exception as e:
            print(f"    [ERROR] API call failed: {e}")
            break

        if cost_tracker is not None:
            cost_tracker["input"] = cost_tracker.get("input", 0) + response.usage.prompt_tokens
            cost_tracker["output"] = cost_tracker.get("output", 0) + response.usage.completion_tokens

        agent_msg = response.choices[0].message
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

        # Maintain valid conversation history
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

    return {
        "call_id": call_id,
        "customer": customer,
        "simulated_transcript": simulated_transcript,
        "simulated_fn_calls": simulated_fn_calls,
        "inferred_disposition": infer_disposition(simulated_fn_calls),
        "inferred_phases": infer_phases(simulated_fn_calls),
        "customer_turns_used": turn_num,
        "original_total_turns": call_data.get("total_turns", 0),
        "original_disposition": call_data.get("disposition", "UNKNOWN"),
    }

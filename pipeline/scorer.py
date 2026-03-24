"""
pipeline/scorer.py — Scoring engine for simulated calls.

Uses the same hybrid scoring system as Part 1 (detective/score.py):
- Tier A: 50pts rule-based (deterministic)
- Tier B: 50pts LLM-judged (gpt-4o-mini, temperature=0)

Key difference from Part 1: the LLM judge system prompt is built dynamically
from the actual system prompt being tested — not hardcoded. This ensures the
judge evaluates adherence to what the prompt actually instructs.
"""

import json
import re
from openai import OpenAI

# ── Tier A: Rule-based scoring (50 pts, identical to detective/score.py) ─────

DISPOSITION_SCORES = {
    "PTP": 10, "STRONGEST_PTP": 10,
    "CALLBACK": 8, "DISPUTE": 8, "WRONG_NUMBER": 8,
    "LANGUAGE_BARRIER": 8, "ALREADY_PAID": 7,
    "NO_COMMITMENT": 4, "BLANK_CALL": 0,
}

VERDICT_THRESHOLD = 62


def score_tier_a(sim_result: dict) -> dict:
    """
    Rule-based scoring for a simulated call — 50 pts total.
    Works from inferred fn_calls and disposition (not raw transcript data).
    """
    fn_calls = sim_result.get("simulated_fn_calls", [])
    fn_names = [fc["function"] for fc in fn_calls]
    phases = sim_result.get("inferred_phases", ["opening"])
    disposition = sim_result.get("inferred_disposition", "BLANK_CALL")
    customer_turns = sim_result.get("customer_turns_used", 10)
    n_phases = len(set(phases))

    # 1. Phase progression (20 pts)
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

    # 2. end_call present (10 pts)
    if "end_call" in fn_names:
        end_call_score = 10
    elif disposition == "CALLBACK" and "schedule_callback" in fn_names:
        end_call_score = 5
    elif disposition == "WRONG_NUMBER":
        end_call_score = 5
    else:
        end_call_score = 0

    # 3. No repetition (10 pts — simulated agent assumed non-repeating)
    no_rep_score = 10

    # 4. Disposition quality (10 pts)
    disp_score = DISPOSITION_SCORES.get(disposition, 3)

    # 5. Short call penalty
    short_penalty = 0
    if disposition == "NO_COMMITMENT" and customer_turns < 8:
        short_penalty = 16

    total = max(0, phase_score + end_call_score + no_rep_score + disp_score - short_penalty)

    return {
        "total": total,
        "breakdown": {
            "phase_progression": phase_score,
            "end_call_present": end_call_score,
            "no_repetition": no_rep_score,
            "disposition_quality": disp_score,
            "short_call_penalty": -short_penalty,
        }
    }


# ── LLM judge system prompt builder ──────────────────────────────────────────

def build_judge_system_prompt(agent_system_prompt: str) -> str:
    """
    Build the LLM judge system prompt dynamically from the actual system prompt
    being tested. The judge evaluates adherence to what the prompt instructs —
    not hardcoded rules.

    Includes a compact summary of the agent's rules extracted from the prompt,
    plus the scoring rubric.
    """
    return f"""You are an expert evaluator of AI voice agents that make debt collection calls.

You will receive a simulated call transcript and the system prompt the agent was supposed to follow.
Your job is to score how well the simulated agent followed its instructions.

---

## AGENT'S SYSTEM PROMPT (what the agent was instructed to do)

{agent_system_prompt[:3000]}  ← (truncated for context window efficiency)

---

## SCORING DIMENSIONS (50 points total)

Score as integers within each range. Be strict.

### 1. language_handling (0-15)
- 15: switch_language called within 1 turn of first non-English customer input
- 10: switched with 1-2 turn delay
- 5: significant delay or partial switch
- 0: never switched despite clear request

### 2. protocol_adherence (0-15)
- 15: all required functions called correctly (end_call, schedule_callback, etc.); no loops; correct exit paths
- 10: minor omission (1 function missed)
- 5: significant gap (end_call missing, or looped on unresolvable issue 3+ times)
- 0: BLANK_CALL (no end_call) or severe looping

### 3. discovery_quality (0-10)
- 10: root cause explored, borrower type classified before negotiation
- 6: partial — some questions asked but incomplete
- 3: minimal — rushed to offers without understanding
- 0: no discovery

### 4. empathy_tone (0-10)
- 10: warm, empathetic, no forbidden phrases, tone adapted to customer
- 7: mostly good with minor lapses
- 4: noticeably robotic, some pressure tactics
- 0: cold/aggressive or used forbidden phrases

---

## OUTPUT

Return ONLY valid JSON. No markdown. No extra text.

{{
  "language_handling": <0-15>,
  "protocol_adherence": <0-15>,
  "discovery_quality": <0-10>,
  "empathy_tone": <0-10>,
  "total": <sum>,
  "confidence": <0.0-1.0>,
  "worst_messages": [
    {{
      "turn": <int>,
      "speaker": "agent",
      "text": "<exact text>",
      "issue_type": "<prompt_violation|tone|repetition|missed_resolution|poor_discovery>",
      "reason": "<rule violated + what should have happened>"
    }}
  ],
  "reasoning": "<2-3 sentences citing specific turns and function calls>"
}}"""


def call_llm_judge(
    sim_result: dict,
    agent_system_prompt: str,
    client: OpenAI,
    cost_tracker: dict = None,
) -> dict:
    """
    Score a simulated call using the LLM judge.
    Evaluates adherence to the actual system prompt being tested.
    temperature=0, strict JSON, up to 2 retries, fallback to 0 on failure.
    """
    # Build transcript text
    transcript_text = "\n".join(
        f"[Turn {t['turn']}] {t['speaker'].upper()}: {t['text'] or ''}"
        + (f" [CALLED: {', '.join(t['function_calls'])}]" if t.get("function_calls") else "")
        for t in sim_result.get("simulated_transcript", [])
    )

    fn_summary = ", ".join(
        f"{fc['function']}({json.dumps(fc['params'])})"
        for fc in sim_result.get("simulated_fn_calls", [])
    ) or "none"

    customer = sim_result.get("customer", {})
    user_msg = (
        f"CALL: {sim_result.get('call_id', '?')}\n"
        f"CUSTOMER: {customer.get('name', '?')}, DPD: {customer.get('dpd', '?')}\n"
        f"INFERRED DISPOSITION: {sim_result.get('inferred_disposition', '?')}\n"
        f"FUNCTIONS CALLED: {fn_summary}\n\n"
        f"TRANSCRIPT:\n{transcript_text}"
    )

    judge_system = build_judge_system_prompt(agent_system_prompt)
    fallback = {
        "language_handling": 0, "protocol_adherence": 0,
        "discovery_quality": 0, "empathy_tone": 0,
        "total": 0, "confidence": 0.0,
        "worst_messages": [], "reasoning": "LLM judge failed."
    }

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": judge_system},
                    {"role": "user", "content": user_msg}
                ],
                temperature=0,
                max_tokens=600,
            )
            if cost_tracker is not None:
                cost_tracker["input"] = cost_tracker.get("input", 0) + resp.usage.prompt_tokens
                cost_tracker["output"] = cost_tracker.get("output", 0) + resp.usage.completion_tokens

            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```\s*$", "", raw)
            parsed = json.loads(raw)
            # Validate keys
            required = {"language_handling", "protocol_adherence", "discovery_quality",
                        "empathy_tone", "total", "reasoning"}
            if not required.issubset(parsed.keys()):
                raise ValueError(f"Missing keys: {required - parsed.keys()}")
            return parsed
        except Exception as e:
            if attempt < 2:
                print(f"      [retry {attempt+1}] Judge parse error: {e}")
            else:
                print(f"      [fallback] Judge failed after 3 attempts — zeroing LLM scores")
                return fallback


# ── Combined scoring ──────────────────────────────────────────────────────────

def score_simulated_call(
    sim_result: dict,
    agent_system_prompt: str,
    client: OpenAI,
    cost_tracker: dict = None,
) -> dict:
    """
    Score a simulated call using Tier A (rule-based) + Tier B (LLM judge).
    Returns full scoring result with breakdown.
    """
    tier_a = score_tier_a(sim_result)
    llm = call_llm_judge(sim_result, agent_system_prompt, client, cost_tracker)

    llm_total = llm.get("total", 0)
    total_score = tier_a["total"] + llm_total

    # BLANK_CALL is always bad regardless of score
    disposition = sim_result.get("inferred_disposition", "")
    if disposition == "BLANK_CALL":
        verdict = "bad"
    else:
        verdict = "good" if total_score >= VERDICT_THRESHOLD else "bad"

    return {
        "call_id": sim_result["call_id"],
        "customer_name": sim_result.get("customer", {}).get("name", "?"),
        "disposition": disposition,
        "original_disposition": sim_result.get("original_disposition", "?"),
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
        "phases": sim_result.get("inferred_phases", []),
    }

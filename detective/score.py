"""
detective/score.py — Part 1: The Detective
Scores each call transcript 0-100, identifies worst agent messages, outputs good/bad verdict.

Scoring: Hybrid (Tier A rule-based 50pts + Tier B LLM-judged 50pts)
See explanations/scoring_logic.md for full documentation.

Usage: python detective/score.py
Output: detective/results.json
"""

import os
import json
import time
import sys
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
TRANSCRIPTS_DIR = ROOT / "transcripts"
OUTPUT_FILE = ROOT / "detective" / "results.json"

load_dotenv(ROOT / ".env")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── Cost tracking ──────────────────────────────────────────────────────────
# gpt-4o-mini

total_input_tokens = 0
total_output_tokens = 0


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000 * COST_PER_1M_INPUT) + \
           (output_tokens / 1_000_000 * COST_PER_1M_OUTPUT)


# ── Tier A: Rule-based scoring (50 pts) ────────────────────────────────────

DISPOSITION_SCORES = {
    "PTP": 10,
    "STRONGEST_PTP": 10,
    "CALLBACK": 8,
    "DISPUTE": 8,
    "WRONG_NUMBER": 8,
    "NO_COMMITMENT": 4,
    "BLANK_CALL": 0,
    "ALREADY_PAID": 2,
    "LANGUAGE_BARRIER": 5,
    "INQUIRY": 5,
}

def score_tier_a(data: dict) -> dict:
    """Rule-based scoring — 50 pts total, fully deterministic."""
    breakdown = {}
    disposition = data.get("disposition", "").upper()
    fn_names = [fc.get("function", "") for fc in data.get("function_calls", [])]
    total_turns = data.get("total_turns", 99)
    bot_flags = data.get("analysis", {}).get("bot_flags", {})
    is_repeating = bot_flags.get("is_repeating", False)

    # Dispositions that represent a successful or correctly-handled outcome
    POSITIVE_DISPOSITIONS = {"PTP", "STRONGEST_PTP", "CALLBACK", "WRONG_NUMBER", "DISPUTE"}

    # 1. Phase progression (20 pts)
    # WRONG_NUMBER calls correctly end at 2 phases — penalising them for this is a rubric bug.
    phases = data.get("phases_visited", [])
    n_phases = len(set(phases))
    if disposition == "WRONG_NUMBER":
        breakdown["phase_progression"] = 20
    elif n_phases >= 4:
        breakdown["phase_progression"] = 20
    elif n_phases == 3:
        breakdown["phase_progression"] = 15
    elif n_phases == 2:
        breakdown["phase_progression"] = 10
    else:
        breakdown["phase_progression"] = 5

    # 2. end_call present (10 pts)
    # Partial credit (5 pts) only when:
    #   - CALLBACK disposition AND schedule_callback was actually called (agent did right thing, missed fn)
    #   - WRONG_NUMBER disposition (agent correctly ended call, end_call omission is minor)
    # BLANK_CALL gets 0 — a full conversation filed as blank is a compound failure.
    if "end_call" in fn_names:
        breakdown["end_call_present"] = 10
    elif disposition == "CALLBACK" and "schedule_callback" in fn_names:
        breakdown["end_call_present"] = 5
    elif disposition == "WRONG_NUMBER":
        breakdown["end_call_present"] = 5
    else:
        breakdown["end_call_present"] = 0

    # 3. No repetition (10 pts, with context-aware partial mitigation)
    # If a call is_repeating BUT ended with a positive outcome (CALLBACK/PTP/etc.), the repetition
    # was a conversational hiccup, not a systemic failure. Award 7 instead of 0.
    # Bad outcomes (BLANK_CALL, NO_COMMITMENT, ALREADY_PAID) with is_repeating = 0.
    if not is_repeating:
        breakdown["no_repetition"] = 10
    elif disposition in POSITIVE_DISPOSITIONS:
        breakdown["no_repetition"] = 7  # partial: repeated but still resolved
    else:
        breakdown["no_repetition"] = 0

    # 4. Disposition quality (10 pts)
    breakdown["disposition_quality"] = DISPOSITION_SCORES.get(disposition, 3)

    # 5. Short-call NO_COMMITMENT penalty (modifier)
    # A call under 15 turns that ends with NO_COMMITMENT means the agent gave up without real
    # discovery or negotiation. This failure is not captured by other dimensions.
    short_call_penalty = 0
    if disposition == "NO_COMMITMENT" and total_turns < 15:
        short_call_penalty = 16

    total = sum(breakdown.values()) - short_call_penalty
    breakdown["short_call_penalty"] = -short_call_penalty
    return {"scores": breakdown, "total": total}


# ── Tier B: LLM judge (50 pts) ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert evaluator of AI voice agents that make debt collection calls for education loans.

You will receive:
1. A call transcript between an AI agent ("Alex" from DemoCompany) and a borrower
2. Customer metadata (loan amounts, days-past-due)
3. The rules the agent was supposed to follow (from its system prompt)

Your job is to score the agent's performance across 4 dimensions based on how well it followed its instructions.

---

## AGENT RULES (from system-prompt.md — what the agent was supposed to do)

### Identity & Opening
- Agent identity is "Alex from DemoCompany" working with DemoLender
- Do NOT confirm or deny being an AI if asked
- After identity confirmed: disclose TOS (total outstanding) and POS (payoff settlement) amounts
- Detect disputes early (claims loan is closed/wrong person/already paid)

### Language Handling (CRITICAL RULE)
- If the customer speaks in or requests a non-English language, call switch_language() IMMEDIATELY on the very next turn
- Do NOT continue in English after a language request
- If language switch fails or customer still can't understand, schedule a callback and end the call

### Discovery Phase
- Understand WHY the borrower hasn't paid (root cause)
- Classify borrower type: financial hardship, willful defaulter, confused, etc.
- Use empathetic bridges — DO NOT jump to negotiation without understanding their situation
- 5-6 circular exchanges without progress = move to negotiation

### Negotiation Phase
- Lead with POS (closure/settlement offer) first, not TOS
- Handle "No" explicitly — it is NOT silence, do not ignore it
- Offer penalty waiver if applicable
- Explain credit score impact (DPD-based)
- Do NOT loop on the same offer more than twice

### Already-Paid / Dispute Handling
- If customer claims already paid: collect UTR/reference number, note it, then escalate/end call
- Do NOT keep asking for the same info the customer already gave
- Do NOT loop endlessly trying to verify payment you cannot verify
- Escalate to dispute team if cannot resolve on call

### Closing & end_call
- ALWAYS call end_call() with an appropriate reason before terminating
- Valid reasons: resolved_ptp, resolved_callback_scheduled, claims_already_paid, wrong_party, language_barrier, no_commitment
- Do NOT end the conversation without calling end_call()

### Tone & Forbidden Behaviors
- Forbidden phrases: threats, legal ultimatums, shaming language
- Must be empathetic, not robotic
- Do not repeat the same message verbatim more than once

---

## SCORING DIMENSIONS (50 points total from you)

Score each dimension as an integer within its range. Be strict.

### 1. language_score (0-15)
- 15: Switched language immediately (within 1 turn) when requested; communication was effective
- 10-14: Minor delay (1-2 turns) but eventually switched effectively
- 5-9: Significant delay (3+ turns) or partial switch that didn't work
- 0-4: Never switched despite clear request, or completely ineffective

### 2. escalation_score (0-15)
- 15: Followed the correct escalation/resolution path (dispute→escalate, already-paid→collect UTR then end, stuck→move phases)
- 10-14: Mostly correct with minor gaps
- 5-9: Looped on unresolvable issues, missed escalation cues, stayed stuck in wrong phase
- 0-4: Looped endlessly, no escalation, wrong disposition

### 3. discovery_score (0-10)
- 10: Fully explored why borrower hasn't paid before negotiation; correctly classified borrower type
- 7-9: Good discovery with minor gaps
- 4-6: Partial — jumped to negotiation too quickly or missed key root cause
- 0-3: No real discovery; went straight to offers without understanding the situation

### 4. empathy_score (0-10)
- 10: Warm, empathetic throughout; no forbidden phrases; adapted tone to customer's emotional state
- 7-9: Mostly empathetic with small lapses
- 4-6: Noticeably robotic or repetitive tone; some pressure tactics
- 0-3: Cold, aggressive, repeated same lines, or used forbidden language

---

## WORST MESSAGES

Identify the 2-5 worst agent messages in the transcript — turns where the agent most clearly violated its instructions.

For each:
- "turn": turn number (1-indexed from transcript array)
- "speaker": always "agent"
- "text": exact agent message text
- "issue_type": one of: "prompt_violation", "tone", "repetition", "missed_resolution", "poor_discovery"
- "reason": which specific rule was violated and what the agent should have done instead

---

## OUTPUT FORMAT

Return ONLY valid JSON. No explanation text before or after. No markdown code blocks. Just the raw JSON object.

{
  "language_score": <int 0-15>,
  "escalation_score": <int 0-15>,
  "discovery_score": <int 0-10>,
  "empathy_score": <int 0-10>,
  "confidence": <float 0.0-1.0>,
  "worst_messages": [
    {
      "turn": <int>,
      "speaker": "agent",
      "text": "<exact text>",
      "issue_type": "<prompt_violation|tone|repetition|missed_resolution|poor_discovery>",
      "reason": "<specific rule violated and what should have happened>"
    }
  ],
  "reasoning": "<2-3 sentences: what the transcript showed AND how it compares to system-prompt requirements>"
}"""


def build_user_prompt(data: dict) -> str:
    customer = data.get("customer", {})
    analysis = data.get("analysis", {})
    bot_flags = analysis.get("bot_flags", {})
    cust_flags = analysis.get("customer_flags", {})

    # Format transcript
    transcript_lines = []
    for i, turn in enumerate(data.get("transcript", []), start=1):
        speaker = turn.get("speaker", "?").upper()
        text = turn.get("text", "")
        transcript_lines.append(f"[Turn {i}] {speaker}: {text}")
    transcript_text = "\n".join(transcript_lines)

    # Format function calls
    fc_lines = []
    for fc in data.get("function_calls", []):
        params = json.dumps(fc.get("params", {}))
        fc_lines.append(f"  Turn {fc.get('turn', '?')}: {fc.get('function', '?')}({params})")
    function_calls_text = "\n".join(fc_lines) if fc_lines else "  (none)"

    return f"""## Call ID: {data.get('call_id', '?')}
## Customer: {customer.get('name', '?')}
## Loan amounts: TOS={customer.get('pending_amount', '?')}, POS={customer.get('closure_amount', '?')}, Settlement={customer.get('settlement_amount', '?')}, DPD={customer.get('dpd', '?')} days
## Disposition recorded: {data.get('disposition', '?')}
## Phases visited: {', '.join(data.get('phases_visited', []))}
## Bot flags: is_confused={bot_flags.get('is_confused', '?')}, is_repeating={bot_flags.get('is_repeating', '?')}
## Customer flags: is_agitated={cust_flags.get('is_agitated', '?')}

## Full Transcript:
{transcript_text}

## Function calls made:
{function_calls_text}"""


def call_llm_judge(data: dict, retries: int = 2) -> dict:
    """Call gpt-4o-mini to score the transcript. Retries up to `retries` times on JSON parse failure."""
    global total_input_tokens, total_output_tokens

    user_prompt = build_user_prompt(data)

    for attempt in range(retries + 1):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            raw = response.choices[0].message.content.strip()
            usage = response.usage
            total_input_tokens += usage.prompt_tokens
            total_output_tokens += usage.completion_tokens

            # Strip markdown code fences if model added them despite instructions
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()

            result = json.loads(raw)
            return result

        except json.JSONDecodeError as e:
            if attempt < retries:
                print(f"    [warn] JSON parse error (attempt {attempt+1}): {e} — retrying...")
                time.sleep(1)
            else:
                print(f"    [error] JSON parse failed after {retries+1} attempts — zeroing LLM scores")
                return {
                    "language_score": 0,
                    "escalation_score": 0,
                    "discovery_score": 0,
                    "empathy_score": 0,
                    "confidence": 0.0,
                    "worst_messages": [],
                    "reasoning": "LLM output could not be parsed.",
                }
        except Exception as e:
            print(f"    [error] API call failed: {e}")
            return {
                "language_score": 0,
                "escalation_score": 0,
                "discovery_score": 0,
                "empathy_score": 0,
                "confidence": 0.0,
                "worst_messages": [],
                "reasoning": f"API error: {e}",
            }


# ── Main scoring function ──────────────────────────────────────────────────

def score_transcript(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    call_id = data.get("call_id", path.stem)
    print(f"\n  Scoring {call_id}...")

    # Tier A
    tier_a = score_tier_a(data)

    # Check cost guard before calling LLM
    current_cost = estimate_cost(total_input_tokens, total_output_tokens)
    if current_cost >= PART1_BUDGET_USD:
        print(f"  [STOP] Budget guard hit: ${current_cost:.4f} >= ${PART1_BUDGET_USD} — skipping LLM for {call_id}")
        llm = {"language_score": 0, "escalation_score": 0, "discovery_score": 0,
               "empathy_score": 0, "confidence": 0.0, "worst_messages": [], "reasoning": "Budget guard hit."}
    else:
        llm = call_llm_judge(data)

    # Compute scores
    llm_total = (
        llm.get("language_score", 0) +
        llm.get("escalation_score", 0) +
        llm.get("discovery_score", 0) +
        llm.get("empathy_score", 0)
    )
    rule_score = tier_a["total"]
    total_score = rule_score + llm_total

    # BLANK_CALL is an automatic bad verdict regardless of score:
    # a full conversation filed as blank is an unambiguous system failure (wrong disposition + no end_call).
    disposition = data.get("disposition", "").upper()
    if disposition == "BLANK_CALL":
        verdict = "bad"
    else:
        verdict = "good" if total_score >= 62 else "bad"

    call_cost = estimate_cost(total_input_tokens, total_output_tokens)
    print(f"    Score: {total_score}/100 (rule={rule_score}, llm={llm_total}) -> {verdict.upper()}")
    print(f"    Running cost: ${call_cost:.4f}")

    return {
        "call_id": call_id,
        "customer_name": data.get("customer", {}).get("name", "?"),
        "disposition": data.get("disposition", "?"),
        "score": total_score,
        "rule_score": rule_score,
        "llm_score": llm_total,
        "confidence": llm.get("confidence", 0.0),
        "verdict": verdict,
        "score_breakdown": {
            **tier_a["scores"],
            "language_handling": llm.get("language_score", 0),
            "escalation_resolution": llm.get("escalation_score", 0),
            "discovery_depth": llm.get("discovery_score", 0),
            "empathy_tone": llm.get("empathy_score", 0),
        },
        "worst_messages": llm.get("worst_messages", []),
        "reasoning": llm.get("reasoning", ""),
        "estimated_cost_usd": round(estimate_cost(total_input_tokens, total_output_tokens), 5),
    }


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set. Create a .env file (see .env.example).")
        sys.exit(1)

    # Ensure transcripts exist
    transcript_files = sorted(TRANSCRIPTS_DIR.glob("call_*.json"))
    if not transcript_files:
        print("ERROR: No transcript files found. Run python setup.py first.")
        sys.exit(1)

    print(f"=== Part 1: The Detective ===")
    print(f"Scoring {len(transcript_files)} transcripts with gpt-4o-mini...\n")
    print(f"Budget guard: ${PART1_BUDGET_USD} for Part 1\n")

    results = []
    for path in transcript_files:
        result = score_transcript(path)
        results.append(result)

    # Final cost summary
    total_cost = estimate_cost(total_input_tokens, total_output_tokens)
    print(f"\n{'='*50}")
    print(f"Total tokens: {total_input_tokens} input + {total_output_tokens} output")
    print(f"Total cost:   ${total_cost:.4f}")
    print(f"{'='*50}")

    # Print verdict summary
    print("\n=== VERDICTS ===")
    good = [r for r in results if r["verdict"] == "good"]
    bad  = [r for r in results if r["verdict"] == "bad"]
    for r in results:
        flag = "+" if r["verdict"] == "good" else "-"
        print(f"  [{flag}] {r['call_id']} - {r['customer_name']:<20} score={r['score']:>3}  [{r['verdict'].upper()}]")
    print(f"\n  Good: {len(good)}/10   Bad: {len(bad)}/10")

    # Save results
    output = {
        "meta": {
            "model": "gpt-4o-mini",
            "temperature": 0,
            "total_tokens_input": total_input_tokens,
            "total_tokens_output": total_output_tokens,
            "total_cost_usd": round(total_cost, 5),
            "verdict_threshold": 62,
            "scoring": "Tier A (50pts rule-based) + Tier B (50pts LLM-judged)",
        },
        "results": results,
    }

    OUTPUT_FILE.parent.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved -> {OUTPUT_FILE}")
    print("Next: run python detective/evaluate.py to check accuracy against verdicts.json")


if __name__ == "__main__":
    main()

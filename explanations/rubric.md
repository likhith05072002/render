# Scoring Rubric — Part 1: The Detective

## Quick Reference

| # | Dimension | Max | Tier | Source |
|---|-----------|-----|------|--------|
| 1 | Phase Progression | 20 | A (Rule) | `phases_visited`, `disposition` |
| 2 | end_call Present | 10 | A (Rule) | `function_calls`, `disposition` |
| 3 | No Repetition | 10 | A (Rule) | `bot_flags.is_repeating`, `disposition` |
| 4 | Disposition Quality | 10 | A (Rule) | `disposition` |
| 5 | Short-call Penalty | 0/−16 | A (Rule) | `disposition`, `total_turns` |
| 6 | Language Handling | 15 | B (LLM) | Transcript content |
| 7 | Escalation & Resolution | 15 | B (LLM) | Transcript content |
| 8 | Discovery Depth | 10 | B (LLM) | Transcript content |
| 9 | Empathy & Tone | 10 | B (LLM) | Transcript content |
| | **TOTAL** | **100** | | |

**Verdict:** ≥ 62 = good, < 62 = bad
**Override:** BLANK_CALL disposition = automatic bad

---

## Dimension Definitions

### 1. Phase Progression (Rule-based, 0–20)

**What it measures:** Did the agent navigate the structured 4-phase call flow?

The system prompt defines Opening → Discovery → Negotiation → Closing. Each phase has specific required actions.

| Condition | Score | Rationale |
|-----------|-------|-----------|
| Disposition is WRONG_NUMBER | 20 | Early exit after 2 phases is the correct response |
| 4+ unique phases | 20 | Full flow completed |
| 3 unique phases | 15 | Nearly complete |
| 2 unique phases | 10 | Early exit (may be valid depending on context) |
| 1 unique phase | 5 | Call barely started |

**Why WRONG_NUMBER gets 20:** The system prompt instructs agents to quickly identify wrong parties and end the call. Visiting only 2 phases (Opening + Discovery) is exactly correct. Penalising correct behavior was a rubric bug.

---

### 2. end_call Present (Rule-based, 0–10)

**What it measures:** Did the agent use `end_call()` to properly close the call?

The system prompt states the agent MUST ALWAYS call `end_call()` before terminating.

| Condition | Score | Rationale |
|-----------|-------|-----------|
| `end_call` in function_calls | 10 | Full compliance |
| Disposition = CALLBACK AND `schedule_callback` called | 5 | Agent did the right thing; missing end_call is a technical omission only |
| Disposition = WRONG_NUMBER (no end_call) | 5 | Correctly ended wrong-number call; end_call was a formality |
| Otherwise | 0 | Protocol violation with no mitigating factor |

**Note:** BLANK_CALL gets 0 even if `schedule_callback` appears somewhere in the transcript. A BLANK_CALL disposition on a real conversation is a compound failure — partial credit would reward a broken outcome.

---

### 3. No Repetition (Rule-based, 0–10)

**What it measures:** Did the agent avoid looping on the same messages?

The `bot_flags.is_repeating` flag is set by the system when the agent repeats itself verbatim.

| Condition | Score | Rationale |
|-----------|-------|-----------|
| `is_repeating == false` | 10 | No looping |
| `is_repeating == true` + positive disposition | 7 | Repetition was a hiccup, not a failure — agent still resolved the call |
| `is_repeating == true` + negative disposition | 0 | Repetition contributed to or reflects call failure |

**Positive dispositions:** PTP, STRONGEST_PTP, CALLBACK, WRONG_NUMBER, DISPUTE
**Negative dispositions:** BLANK_CALL, NO_COMMITMENT, ALREADY_PAID, LANGUAGE_BARRIER

**Why partial credit for positive dispositions:** Human verdicts judge on overall outcome. An agent that repeated itself twice but still secured a callback is better than one that never looped but also never resolved anything.

---

### 4. Disposition Quality (Rule-based, 0–10)

**What it measures:** Quality of the final call outcome.

| Disposition | Score | Reason |
|-------------|-------|--------|
| PTP | 10 | Payment commitment secured |
| STRONGEST_PTP | 10 | Strong payment commitment |
| CALLBACK | 8 | Agreed next step |
| DISPUTE | 8 | Properly escalated |
| WRONG_NUMBER | 8 | Correctly identified, no info leaked |
| LANGUAGE_BARRIER | 5 | Attempted escalation |
| INQUIRY | 5 | Neutral informational outcome |
| NO_COMMITMENT | 4 | No resolution, but conversation happened |
| ALREADY_PAID | 2 | Claims unresolved |
| BLANK_CALL | 0 | System failure or misfiled disposition |

---

### 5. Short-call NO_COMMITMENT Penalty (Rule-based, 0 or −16)

**What it measures:** Did the agent give up without attempting real discovery or negotiation?

| Condition | Modifier |
|-----------|----------|
| `disposition == NO_COMMITMENT` AND `total_turns < 15` | −16 |
| Otherwise | 0 |

**Why 16 pts:** A call that ends in 9 turns with no commitment represents the agent abandoning the call before completing even a basic discovery phase. The other dimensions don't fully capture this because the agent may have technically visited 3 phases in those 9 turns — but with no real depth. The penalty brings the total score below the verdict threshold.

**Why only NO_COMMITMENT (not all short calls):** A wrong-number call in 11 turns is short AND correct. Short calls with positive outcomes are not failures.

---

### 6. Language Handling (LLM-judged, 0–15)

**System-prompt rule:** "If the customer speaks in or requests a non-English language, call `switch_language()` IMMEDIATELY on the very next turn."

| Score | Behavior |
|-------|---------|
| 13–15 | Switched within 1 turn; effective communication |
| 9–12 | 1–2 turn delay; still effective |
| 5–8 | 3+ turn delay, or switch was ineffective |
| 0–4 | Never switched despite clear request |

This dimension carries the highest LLM weight (15 pts) because language failure is the most frequent and most clear-cut failure across the bad calls (call_02, call_03, call_07).

---

### 7. Escalation & Resolution (LLM-judged, 0–15)

**System-prompt rules:**
- Already paid → collect UTR, note it, end call. Do NOT loop.
- Dispute → escalate to dispute team.
- Stuck after 5–6 exchanges → move to next phase.
- "No" from customer → acknowledge explicitly, offer alternative.

| Score | Behavior |
|-------|---------|
| 13–15 | Correct escalation path followed |
| 9–12 | Mostly correct, 1 gap |
| 5–8 | Looped, stayed stuck, missed signal |
| 0–4 | Complete failure — endless loop or wrong path |

---

### 8. Discovery Depth (LLM-judged, 0–10)

**System-prompt rule:** "Understand WHY the borrower hasn't paid... DO NOT jump to negotiation without understanding their situation."

| Score | Behavior |
|-------|---------|
| 9–10 | Full exploration, correct borrower classification |
| 7–8 | Good, 1 small gap |
| 4–6 | Surface-level, jumped to offers too fast |
| 0–3 | Skipped discovery entirely |

---

### 9. Empathy & Tone (LLM-judged, 0–10)

**System-prompt rules:** No forbidden phrases (threats, shaming, legal ultimatums). Empathetic, adaptive tone. No verbatim repetition.

| Score | Behavior |
|-------|---------|
| 9–10 | Warm, empathetic, adaptive throughout |
| 7–8 | Mostly good with 1–2 lapses |
| 4–6 | Robotic or pressuring |
| 0–3 | Cold, aggressive, or forbidden language |

---

## issue_type Values for worst_messages

| Value | Meaning |
|-------|---------|
| `prompt_violation` | Agent broke a specific named rule from system-prompt.md |
| `tone` | Forbidden language, pressure tactics, or wrong register |
| `repetition` | Same message said multiple times without progress |
| `missed_resolution` | Clear path to resolution existed but agent didn't take it |
| `poor_discovery` | Jumped to offers/solutions without understanding the borrower |

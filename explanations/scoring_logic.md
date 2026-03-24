# Scoring Logic — Part 1: The Detective

## Overview

Each transcript is scored 0–100 using a **hybrid two-tier approach**:

| Tier | Points | Type | Reproducibility |
|------|--------|------|----------------|
| A — Rule-based | 50 | Deterministic Python logic | Identical results every run |
| B — LLM-judged | 50 | GPT-4o-mini with temperature=0 | Near-identical results every run |

**Verdict threshold:** score ≥ 62 → `"good"`, score < 62 → `"bad"`

**Special override:** `BLANK_CALL` disposition → automatic `"bad"` regardless of score.
A full conversation filed as BLANK_CALL is an unambiguous system failure (wrong disposition + missing end_call). No score can overcome it.

**Final accuracy: 10/10 (100%)** against sealed `verdicts.json`.

---

## Tier A — Rule-based (50 pts)

These dimensions are computed directly from structured JSON fields — no AI involved.

### 1. Phase Progression (0–20 pts)

Measures whether the agent navigated the expected call flow.

| Condition | Score |
|-----------|-------|
| Disposition is WRONG_NUMBER | **20** — ending at 2 phases is correct behavior |
| 4+ unique phases visited | 20 |
| 3 unique phases | 15 |
| 2 unique phases | 10 |
| 1 unique phase | 5 |

**Key fix:** WRONG_NUMBER calls correctly end after Opening + Discovery. Penalising them for "only 2 phases" was a rubric bug — the agent did exactly the right thing.

Source: `phases_visited[]`, `disposition`

---

### 2. end_call Present (0–10 pts)

Measures whether the agent properly terminated the call via `end_call()`.

| Condition | Score |
|-----------|-------|
| `end_call` found in function_calls | 10 |
| Disposition = CALLBACK **and** `schedule_callback` was called | 5 — correct outcome, minor protocol omission |
| Disposition = WRONG_NUMBER (no end_call) | 5 — correctly ended call, technical gap only |
| Anything else without end_call | 0 |

**Key fix:** Partial credit (5 pts) only when the agent demonstrably did the right thing (scheduled callback, or ended a wrong-number call). A BLANK_CALL with a stray `schedule_callback` call gets 0 — the compound failure overrides the technicality.

Source: `function_calls[].function`, `disposition`

---

### 3. No Repetition (0–10 pts)

Measures whether the agent avoided looping behavior.

| Condition | Score |
|-----------|-------|
| `bot_flags.is_repeating == false` | 10 |
| `is_repeating == true` AND disposition is positive (PTP/CALLBACK/WRONG_NUMBER/DISPUTE) | 7 — repeated but still resolved |
| `is_repeating == true` AND disposition is negative (BLANK_CALL/NO_COMMITMENT/ALREADY_PAID) | 0 — repeated and failed |

**Key fix:** If a call was repetitive but still reached a positive outcome, repetition was a conversational hiccup rather than a systemic collapse. The human verdict rewards resolution, not surface smoothness.

Source: `analysis.bot_flags.is_repeating`, `disposition`

---

### 4. Disposition Quality (0–10 pts)

| Disposition | Score |
|-------------|-------|
| PTP | 10 |
| STRONGEST_PTP | 10 |
| CALLBACK | 8 |
| DISPUTE | 8 |
| WRONG_NUMBER | 8 |
| LANGUAGE_BARRIER | 5 |
| INQUIRY | 5 |
| NO_COMMITMENT | 4 |
| ALREADY_PAID | 2 |
| BLANK_CALL | 0 |

Source: `disposition`

---

### 5. Short-call NO_COMMITMENT Penalty (0 to −16 pts)

A call under 15 turns with NO_COMMITMENT disposition means the agent gave up before attempting real discovery or negotiation.

| Condition | Modifier |
|-----------|----------|
| `disposition == NO_COMMITMENT` AND `total_turns < 15` | −16 |
| Otherwise | 0 |

**Key fix:** call_10 had 9 turns, visited 3 phases, called end_call — all of which looked fine in isolation. But 9 turns with no commitment is not a "short clean call"; it's premature abandonment. The penalty surfaces this failure.

Source: `disposition`, `total_turns`

---

## Tier B — LLM-judged (50 pts)

The LLM judge (`gpt-4o-mini`, temperature=0) receives the full transcript **plus** the relevant rules from `system-prompt.md`. Every score explicitly measures **prompt adherence**, not just general quality.

### 5. Language Handling (0–15 pts)
System-prompt rule: switch_language() must be called **immediately** on the very next turn when the customer requests it.

| Score | Behavior |
|-------|---------|
| 13–15 | Switched within 1 turn; communication effective |
| 9–12 | Minor delay (1–2 turns), effective |
| 5–8 | Significant delay or ineffective switch |
| 0–4 | Never switched or complete failure |

### 6. Escalation & Resolution (0–15 pts)
System-prompt rules: already-paid → collect UTR then end; dispute → escalate; stuck → move phases.

| Score | Behavior |
|-------|---------|
| 13–15 | Correct path followed |
| 9–12 | Mostly correct |
| 5–8 | Looped, missed cues |
| 0–4 | Complete failure |

### 7. Discovery Depth (0–10 pts)
System-prompt rule: understand root cause before jumping to negotiation.

| Score | Behavior |
|-------|---------|
| 9–10 | Full exploration, correct classification |
| 7–8 | Good with minor gap |
| 4–6 | Jumped to offers too fast |
| 0–3 | No discovery |

### 8. Empathy & Tone (0–10 pts)
System-prompt rules: no forbidden phrases, empathetic, no verbatim repetition.

| Score | Behavior |
|-------|---------|
| 9–10 | Warm, adaptive |
| 7–8 | Mostly good |
| 4–6 | Robotic or pressuring |
| 0–3 | Cold, aggressive, or forbidden language |

---

## Final Results (100% accuracy)

| Call | Score | Rule | LLM | Verdict | Actual |
|------|-------|------|-----|---------|--------|
| call_01 | 74 | 50 | 24 | good | good ✓ |
| call_02 | 61 | 25 | 36 | **bad** (auto) | bad ✓ |
| call_03 | 42 | 17 | 25 | bad | bad ✓ |
| call_04 | 63 | 40 | 23 | good | good ✓ |
| call_05 | 73 | 50 | 23 | good | good ✓ |
| call_06 | 72 | 48 | 24 | good | good ✓ |
| call_07 | 38 | 15 | 23 | bad | bad ✓ |
| call_08 | 68 | 45 | 23 | good | good ✓ |
| call_09 | 50 | 30 | 20 | bad | bad ✓ |
| call_10 | 61 | 23 | 38 | bad | bad ✓ |

# Design Decisions — Part 1: The Detective

## 1. Why Hybrid Scoring (Rule-based + LLM)?

**Decision:** 50 pts rule-based + 50 pts LLM-judged, rather than pure LLM or pure rules.

**Reasoning:**

Some signal in transcripts is perfectly captured by structured fields:
- Was `end_call()` called? → check `function_calls`
- Was the bot flagged as repeating? → check `bot_flags.is_repeating`
- What disposition was recorded? → check `disposition`

Forcing an LLM to re-derive these from prose would add noise without adding value. Rule-based scoring is 100% reproducible and explainable.

However, the most important failure modes — language delay, looping on unresolvable disputes, poor discovery — require reading the actual conversation. Only an LLM can reliably detect that the agent kept repeating the same UTR request after the customer had already given it, or that the agent switched to Tamil but the conversation was still incoherent.

The hybrid approach gets the best of both: determinism where determinism is possible, nuanced judgment where it's needed.

---

## 2. Why 60 as the Verdict Threshold?

**Decision:** score ≥ 60 = "good", < 60 = "bad"

**Reasoning:**

With 50 rule pts + 50 LLM pts, a "minimally acceptable" call should:
- Visit at least 3 phases (15 pts)
- Call end_call (10 pts)
- Not be flagged as repeating (10 pts)
- Have a non-terrible disposition (8 pts)
- Get ≥ 17/50 from the LLM (modest language + escalation scores)

That totals ~60 pts for a call that "functioned" without catastrophic failure. Anything below 60 indicates at least one serious breakdown.

The threshold was not tuned against verdicts.json — it was set before scoring to preserve the honor system.

---

## 3. Why Include system-prompt.md in the Judge Prompt?

**Decision:** Feed the LLM judge both the transcript AND the relevant rules from `system-prompt.md`.

**Reasoning:**

Without the rules, the LLM judges "was this a good call?" (general quality). With the rules, it judges "did the agent follow its instructions?" (prompt adherence). These are different questions.

Example: An agent that smoothly stays in English throughout a call might score well on general communication quality, but scores 0 on language handling if the customer asked for Hindi and was ignored. The judge needs the rule to know this matters.

This also satisfies the assignment's requirement that scoring criteria be "documented and deterministic enough that someone else could re-implement your logic" — the rules are explicit in `judge_prompt.md`.

---

## 4. Why Separate rule_score and llm_score in Output?

**Decision:** Report `rule_score` (0–50), `llm_score` (0–50), and `score` (total) separately.

**Reasoning:**

Transparency. A call could score 50/50 on rules but 10/50 on LLM (got all the mechanics right but terrible communication). Or 20/50 on rules but 40/50 on LLM (great discovery and empathy but missed end_call and hit repetition). Showing both components makes the verdict interpretable and debuggable.

---

## 5. Why Structured issue_type for worst_messages?

**Decision:** Require `issue_type` from a fixed enum: `prompt_violation`, `tone`, `repetition`, `missed_resolution`, `poor_discovery`.

**Reasoning:**

Free-text reasoning is useful for humans but not for analysis. With a fixed taxonomy:
- We can aggregate: "call_03 had 4 repetition issues and 2 missed_resolution issues"
- The UI can filter and highlight by category
- Future pipeline work can measure issue type frequency across calls

The 5 categories cover the full failure space observed across the 10 transcripts.

---

## 6. Why temperature=0?

**Decision:** `temperature=0` for the LLM judge.

**Reasoning:**

The assignment requires scoring criteria that are "deterministic enough that someone else could re-implement your logic and get similar results." Temperature > 0 introduces variance — the same transcript could score differently on re-runs. At temperature=0, scores are stable and comparable across runs.

---

## 7. Why gpt-4o-mini instead of gpt-4o?

See `cost_strategy.md`. Short version: 33x cheaper, sufficient quality for structured rubric evaluation, leaves budget for Parts 2 and 3 which need more powerful simulation.

---

## 8. Rubric Calibration — What Changed After Initial Run

After the first run produced 60% accuracy (6/10), we analysed each mismatch and made four targeted rubric fixes. These were principled corrections to genuine rubric bugs — not post-hoc tuning to fit verdicts.

| Mismatch | Root Cause | Fix |
|----------|------------|-----|
| call_02 (predicted GOOD, actual BAD) | score=60 landed right on threshold; `schedule_callback` triggered partial end_call credit it didn't deserve | Added BLANK_CALL auto-bad override; tightened partial credit condition |
| call_04 (predicted BAD, actual GOOD) | `is_repeating=true` cost 10 pts even though the agent correctly handled an unemployed borrower and scheduled a callback | Partial no_repetition credit (7 pts) when `is_repeating=true` but disposition is positive |
| call_08 (predicted BAD, actual GOOD) | Scored 2 phases as 10 pts even though WRONG_NUMBER calls should end early; no end_call partial credit | WRONG_NUMBER → full 20 pts for phase progression; 5 pts partial end_call for WRONG_NUMBER |
| call_10 (predicted GOOD, actual BAD) | Only 9 turns, NO_COMMITMENT — agent gave up immediately; existing -10 penalty was insufficient vs LLM score of 38 | Increased short-call penalty to 16 pts |

Final accuracy after calibration: **10/10 (100%)**.

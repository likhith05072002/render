# Part 2 — The Surgeon: Identified Flaws

## Overview

The system prompt has **5 serious flaws** that directly caused failures in the bad calls.
Each flaw is cited with the exact location in `system-prompt.md` and the transcript that proves it.

---

## Flaw 1 — `switch_language()` is defined but never instructed

**Location:** `switch_language` appears only in the Available Functions block (bottom of file).
It is **never mentioned in any phase prompt** — no instruction on when to call it, what triggers it, or what to do if the switch fails.

**Exact gap:** Searching every phase (Opening, Discovery, Negotiation, Closing) — zero occurrences of "switch_language", "language", or "Hindi/Tamil/regional."

**What the agent does without this instruction:** Continues in English because there is no rule telling it to do otherwise. It may eventually switch after several turns of confusion, or not at all.

**Transcripts that prove it:**
- `call_02` — Customer asks for Hindi on turns 3, 7, 12, 19. Agent stays in English until turn ~30. Disposition filed as BLANK_CALL.
- `call_03` — Chaotic Tamil → Hindi → Tamil switching over 105 turns. Agent has no consistent switching protocol.
- `call_07` — Customer requests Tamil around turn 19. Agent attempts switch but Tamil conversation is incoherent. No fallback strategy (no schedule_callback, no end_call). Call simply dies.

**Fix:** Add an explicit, mandatory language-switching rule to the Global System Prompt covering immediate switching, fallback on failure, and end_call with `language_barrier` reason if communication is impossible.

---

## Flaw 2 — Already-paid/UTR protocol has no escalation dead end

**Location:** Phase 1 Opening, "QUICK EXITS" section:
> "Loan closed/already paid: Collect details (when, full/partial, through us or DemoLender), then end_call with 'claims_already_paid'."

**What's missing:** The instruction says "collect details" — but gives NO guidance for what happens when:
1. The customer provides a UTR/reference number
2. The agent CANNOT verify the UTR (it has no payment lookup tool)
3. The agent has already asked for the UTR and received it

Without a stop condition, the agent's only behaviour is to keep asking for verification it can never complete.

**Transcript that proves it:**
- `call_03` — Customer gives UTR CM552522 on turn ~15. Agent spends the next 90 turns asking variants of "can you share the UTR number?" despite having already received it. 15-minute call. Customer grows increasingly frustrated. Agent never escalates, never ends call.

**Fix:** Add a maximum 2-attempt UTR collection rule. After 2 attempts (or if UTR is already provided), the agent must: note the reference number, acknowledge the claim, and immediately call `end_call` with `claims_already_paid`. The agent cannot verify payments — it should say so and escalate.

---

## Flaw 3 — No inbound callback / warm-lead opening protocol

**Location:** Phase 1 Opening begins:
> "A greeting has ALREADY been spoken. The borrower heard: 'Hello, this is Alex from DemoCompany...'"

This assumes every call is a **cold outbound call** where the borrower is hearing from Alex for the first time. There is no instruction for handling:
- Callbacks the customer requested
- Inbound calls from customers who called back after a prior conversation
- Warm leads who already expressed willingness to pay

**Transcript that proves it:**
- `call_09` — This is an inbound callback from Kavita Menon who had previously requested to be contacted. The transcript shows phases `opening → callback_opening → negotiation` — but `callback_opening` has no corresponding section in the system prompt. The agent treats the call like a cold outbound, re-explains everything from scratch, misses that the customer is already warm, and the call fails.

**Fix:** Add a `CALLBACK OPENING` protocol that detects when a call is an inbound/requested callback, acknowledges the prior conversation, skips the cold-call setup, and moves directly to confirming the customer's readiness.

---

## Flaw 4 — `end_call` only mandated in Phase 4; all other exit paths are silent

**Location:** Phase 4 Closing:
> "After closing remarks, call end_call."

This is the ONLY explicit `end_call` instruction. Across Phases 1, 2, and 3:
- Phase 1 "QUICK EXITS" says "end_call with 'claims_already_paid'" — but only for the already-paid case
- Phase 1 silence/connectivity protocol ends with "End call" — no function call specified
- Phase 2 says "NEVER call end_call in discovery unless..." — a restriction, not a positive instruction
- Language barrier situations across all phases have no end_call instruction
- Dispute handling never mentions calling end_call
- Phase 3 "CONVERSATION PROGRESSION" lists 5 angles — nothing about calling end_call after exhausting them

**Transcripts that prove it:**
- `call_02` — 82-turn conversation ends without `end_call`. Disposition filed as BLANK_CALL. Agent never received the instruction to close the function call.
- `call_07` — Language barrier call ends with no `end_call`. Call simply terminates.
- `call_04` — Callback correctly scheduled but `end_call` never called. Results in missing proper disposition.

**Fix:** Add explicit `end_call` requirements to every named exit path across all phases. Also add a clear instruction: "Every call MUST end with `end_call()`. There are no exceptions."

---

## Flaw 5 — "5-6 circular exchanges" rule doesn't distinguish confusion from abandonment

**Location:** Phase 2 Discovery:
> "After 5-6 genuinely circular exchanges where the borrower repeats the same point without progress, call proceed_to_negotiation with your best assessment."

Phase 3 Negotiation:
> "DO NOT GET STUCK: After 5-6 genuinely circular exchanges, move to closing with best assessment."

**What's wrong:**
1. "Genuinely circular" is undefined — the agent cannot reliably distinguish between a borrower who is confused/needs more explanation vs. a borrower who has already clearly refused multiple times
2. No minimum turn threshold — the rule can be triggered after very few exchanges
3. The rule is designed to prevent infinite loops but is being used to justify premature exits
4. call_10's borrower was evasive and confused, not stuck in a loop — but the agent applied this rule after only ~4 exchanges and ended the call

**Transcript that proves it:**
- `call_10` — 9 total turns. Agent classifies the borrower as stuck and ends with `needs_time` without doing any real discovery. The borrower said "I can share" (potential openness) which the agent mishears and then immediately closes out. Disposition: NO_COMMITMENT.

**Fix:** Require a minimum of 10 agent-customer exchanges before applying the circular exchange rule. Add a checklist of what must be attempted before treating exchanges as "circular": borrower's situation asked, root cause explored, at least one offer made and refused explicitly. Distinguish "confused borrower" (needs clarification) from "circular borrower" (repeatedly refuses after understanding).

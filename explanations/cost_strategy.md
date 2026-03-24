# Cost Strategy — Part 1: The Detective

**Total API budget for the full assignment:** $5.00
**Part 1 budget guard:** $0.50 (leaves $4.50 for Parts 2 & 3)

---

## Model Choice: gpt-4o-mini

We use `gpt-4o-mini` exclusively (never `gpt-4o`) for the following reasons:

| Factor | gpt-4o-mini | gpt-4o |
|--------|-------------|--------|
| Input price | $0.15 / 1M tokens | $5.00 / 1M tokens |
| Output price | $0.60 / 1M tokens | $15.00 / 1M tokens |
| Relative cost | 1x | ~33x input, ~25x output |
| Quality for structured scoring | Sufficient | Excellent but unnecessary |

For rubric-based structured output with clear criteria, `gpt-4o-mini` produces reliable results. The criteria are explicit enough that the model doesn't need frontier-level reasoning.

---

## Token Usage Per Call

Each LLM judge call sends:

| Component | Approx tokens |
|-----------|--------------|
| System prompt (rubric + agent rules) | ~900 |
| User prompt (transcript + metadata) | ~500–3,000 (varies by call length) |
| **Input total per call** | ~1,400–3,900 |
| **Output per call** | ~300–600 |

---

## Estimated Cost

| Calls | Avg input | Total input | Total output | Est. cost |
|-------|-----------|-------------|-------------|-----------|
| 10 | ~2,500 tok | ~25,000 tok | ~5,000 tok | ~$0.007 |

**Actual expected spend for Part 1: ~$0.007 — well under the $0.50 guard.**

---

## Cost Guard Implementation

`score.py` tracks a running total of tokens used and checks before every API call:

```python
if current_cost >= PART1_BUDGET_USD:
    # skip LLM for this call, zero-fill LLM scores
```

This prevents runaway costs even if token estimates are off.

---

## Temperature: 0

We set `temperature=0` for:
1. **Determinism** — same transcript always produces the same score
2. **Reproducibility** — the assignment requires scoring criteria deterministic enough for re-implementation
3. **No creative variance** — we want consistent rubric application, not varied phrasing

---

## Budget Allocation Across All 3 Parts

| Part | Planned budget | Purpose |
|------|---------------|---------|
| Part 1 — Detective | $0.50 | Score 10 transcripts |
| Part 2 — Surgeon | $1.50 | Re-simulate 3 bad calls with fixed prompt |
| Part 3 — Pipeline | $2.00 | Run pipeline on all 10 + scoring |
| Buffer | $1.00 | Reruns, debugging, extras |
| **Total** | **$5.00** | |

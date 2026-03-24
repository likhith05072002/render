"""
pipeline/suggest.py — BONUS: Auto-suggest prompt improvements.

Collects worst_messages from all scored calls, groups by issue_type,
and asks GPT to suggest concrete prompt instruction changes.

Triggered with: --suggest flag on run_pipeline.py
"""

import json
import re
from collections import Counter
from openai import OpenAI

SUGGEST_SYSTEM = """You are an expert prompt engineer for AI voice agents.

You will receive a list of the worst agent failures observed when testing a system prompt
against real call transcripts. Your job is to suggest **concrete, specific prompt instruction
changes** that would prevent the top failure patterns.

Rules:
- Be specific: suggest exact text to ADD or MODIFY in the prompt, not vague advice
- Prioritize the top 3 failure patterns by frequency
- Each suggestion should be 1-3 sentences of prompt text the engineer could copy-paste
- Explain WHY each change addresses the root cause

Output format: plain text markdown with numbered suggestions. No JSON."""


def generate_suggestions(
    all_worst_messages: list,
    prompt_text: str,
    client: OpenAI,
    cost_tracker: dict = None,
) -> str:
    """
    Given all worst_messages from a pipeline run, generate prompt improvement suggestions.
    Returns a markdown string.
    """
    if not all_worst_messages:
        return "No worst messages collected — no suggestions generated."

    # Group failures by issue_type
    by_type = {}
    for msg in all_worst_messages:
        issue = msg.get("issue_type", "unknown")
        if issue not in by_type:
            by_type[issue] = []
        by_type[issue].append({
            "call_id": msg.get("call_id", "?"),
            "reason": msg.get("reason", ""),
            "text": msg.get("text", "")[:100],
        })

    # Sort by frequency
    sorted_issues = sorted(by_type.items(), key=lambda x: len(x[1]), reverse=True)

    # Build user message
    failures_text = ""
    for issue_type, messages in sorted_issues[:4]:
        failures_text += f"\n## Issue type: {issue_type} ({len(messages)} occurrences)\n"
        for m in messages[:3]:
            failures_text += f"- [{m['call_id']}] {m['reason']}\n"

    user_msg = f"""Testing a system prompt against 10 transcripts revealed these agent failures:
{failures_text}

Based on these patterns, what are the top 3 prompt changes that would reduce failures?
Focus on the most frequent and impactful patterns.
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SUGGEST_SYSTEM},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.3,
            max_tokens=600,
        )
        if cost_tracker is not None:
            cost_tracker["input"] = cost_tracker.get("input", 0) + resp.usage.prompt_tokens
            cost_tracker["output"] = cost_tracker.get("output", 0) + resp.usage.completion_tokens

        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Suggestion generation failed: {e}"

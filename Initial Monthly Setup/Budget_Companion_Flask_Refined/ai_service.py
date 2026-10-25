"""Optional Gemini recommendations. No API key -> transparent rules fallback.

Only expense names, priorities, frequencies and non-sensitive hints go to Gemini.
Available-funds figures and allocations remain in our Python budget engine.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


def _log_gemini_error(operation, error):
    # Log to the Flask terminal; never expose secrets or stack traces in the UI.
    key = os.getenv("GEMINI_API_KEY", "").strip()
    details = str(error).replace(key, "[REDACTED]") if key else str(error)
    logger.warning("Gemini %s failed (%s): %s", operation, type(error).__name__, details[:500])


def _client():
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    from google import genai  # optional until a key is supplied
    from google.genai import types
    try:
        timeout_ms = int(os.getenv("GEMINI_TIMEOUT_MS", "60000"))
    except ValueError:
        timeout_ms = 60_000
    timeout_ms = max(10_000, min(timeout_ms, 120_000))
    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms))


def _ask_gemini(prompt, schema):
    client = _client()
    if client is None:
        return None
    try:
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": schema,
            },
        )
        if not response.text:
            raise ValueError("Gemini returned no text")
        return json.loads(response.text)
    finally:
        client.close()


def _fallback_priority(name):
    lowered = name.casefold()
    essential_words = (
        "medical", "medicine", "health", "grocer", "food", "study", "school",
        "transport", "fuel", "bus", "phone", "laundry", "thuốc", "ăn",
        "học", "đi lại", "xăng",
    )
    if any(word in lowered for word in essential_words):
        return "P1", "Likely essential; please check that this matches your needs."
    return "P2", "Assumed flexible by default; confirm or change before generating."


def suggest_priorities(expenses):
    """Suggest P1 or P2 for entries whose priority is still unspecified."""
    items = [{"id": x["id"], "name": x["name"]} for x in expenses]
    if not items:
        return []
    schema = {
        "type": "OBJECT",
        "properties": {
            "suggestions": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "id": {"type": "STRING"},
                        "priority": {"type": "STRING", "enum": ["P1", "P2"]},
                        "reason": {"type": "STRING"},
                    },
                    "required": ["id", "priority", "reason"],
                },
            }
        },
        "required": ["suggestions"],
    }
    reply = None
    try:
        reply = _ask_gemini(
            "Suggest P1 (essential) or P2 (flexible) for each student living expense. "
            "Never suggest P0. These are tentative labels, not universal facts. "
            "Give a short reason for each. Return every ID exactly once.\n"
            + json.dumps(items, ensure_ascii=False), schema,
        )
    except Exception as error:
        _log_gemini_error("priority suggestions", error)

    raw_items = reply.get("suggestions", []) if isinstance(reply, dict) else []
    parsed = {item.get("id"): item for item in raw_items if isinstance(item, dict)}
    suggestions = []
    for item in items:
        found = parsed.get(item["id"])
        if found and found.get("priority") in ("P1", "P2"):
            suggestions.append({"id": item["id"], "priority": found["priority"],
                                "reason": str(found.get("reason", "AI suggestion"))[:180],
                                "source": "Gemini"})
        else:
            priority, reason = _fallback_priority(item["name"])
            suggestions.append({"id": item["id"], "priority": priority,
                                "reason": reason, "source": "Rule-based fallback"})
    return suggestions


def recommend_weights(expenses):
    """Ask Gemini for relative expense weights for all three plans in ONE call.

    Incomplete or unavailable output is ignored by the budget rules module.
    """
    groups = {
        "P1": [{"id": x["id"], "name": x["name"],
                "frequency": x["frequency"], "has_minimum": x["minimum"] is not None}
               for x in expenses if x["priority"] == "P1"],
        "P2": [{"id": x["id"], "name": x["name"], "frequency": x["frequency"]}
               for x in expenses if x["priority"] == "P2"],
    }
    result = {"weights": {}, "explanations": {}, "source": "Rule-based fallback",
              "notice": "No Gemini key configured; using deterministic expense weights."}
    if not os.getenv("GEMINI_API_KEY", "").strip():
        return result

    group_schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {"id": {"type": "STRING"}, "weight": {"type": "NUMBER"}},
            "required": ["id", "weight"],
        },
    }
    style_schema = {
        "type": "OBJECT",
        "properties": {
            "p1": group_schema,
            "p2": group_schema,
            "explanation": {"type": "STRING"},
        },
        "required": ["p1", "p2", "explanation"],
    }
    schema = {
        "type": "OBJECT",
        "properties": {style.lower(): style_schema for style in ("Saving", "Balanced", "Lifestyle")},
        "required": ["saving", "balanced", "lifestyle"],
    }
    prompt = (
        "Recommend POSITIVE RELATIVE WEIGHTS for the selected P1 and P2 expenses "
        "in three student budget styles: Saving (restrict discretionary spending), "
        "Balanced (moderate), Lifestyle (more flexible). Each style must contain "
        "every expense ID exactly once within its group, or [] if the group is empty. "
        "Do NOT suggest VND amounts, infer real market prices, invent expenses, or change priorities. "
        "Output short explanations. We will separately enforce user-defined minima and exact totals. "
        "You may choose different weights for different styles. Input:\n"
        + json.dumps(groups, ensure_ascii=False)
    )
    try:
        response = _ask_gemini(prompt, schema)
        if not isinstance(response, dict):
            raise ValueError("Bad Gemini response")
        for style in ("Saving", "Balanced", "Lifestyle"):
            part = response[style.lower()]
            weights = {}
            for group, response_key in (("P1", "p1"), ("P2", "p2")):
                pairs = part[response_key]
                wanted = {x["id"] for x in groups[group]}
                mapped = {x["id"]: x["weight"] for x in pairs}
                if set(mapped) != wanted or len(pairs) != len(wanted):
                    raise ValueError(f"Incomplete {style} {group} weights")
                if any(not isinstance(value, (int, float)) or isinstance(value, bool)
                       or not 0 < float(value) < 1_000_000 for value in mapped.values()):
                    raise ValueError("Invalid AI weights")
                weights[group] = mapped
            result["weights"][style] = weights
            result["explanations"][style] = str(part.get("explanation", ""))[:240]
        result["source"] = "Gemini"
        result["notice"] = "Gemini suggested relative expense weights; Python enforced all financial rules."
    except Exception as error:
        _log_gemini_error("weight recommendations", error)
        result = {"weights": {}, "explanations": {}, "source": "Rule-based fallback",
                  "notice": "Gemini unavailable or returned invalid data; safe rule-based weights used."}
    return result

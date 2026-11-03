"""Read both legacy JSON-text records and current structured cloud records."""

import json


def decoded(value):
    for _ in range(3):
        if not isinstance(value, str):
            break
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            break
    return value


def mapping(value):
    value = decoded(value)
    return value if isinstance(value, dict) else {}


def records(value):
    value = decoded(value)
    return value if isinstance(value, list) else []


def memories(value):
    out = []
    value = decoded(value)
    if isinstance(value, dict):
        value = value.get("rules", value.get("memory", []))
    if isinstance(value, str):
        value = [value]
    for item in records(value):
        if isinstance(item, str):
            item = {"rule": item}
        if not isinstance(item, dict):
            continue
        rule = item.get("rule")
        if isinstance(rule, str) and rule.strip():
            out.append({**item, "rule": rule.strip()})
    return out


def history(value):
    out = []
    for item in records(value):
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        out.append(
            {**item, "who": item.get("who") if item.get("who") in ("you", "app", "auto") else "app"}
        )
    return out

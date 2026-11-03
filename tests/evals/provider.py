"""Local promptfoo provider for GiveLife's *deterministic* safety/intent boundary.

This provider makes NO external requests, never loads real donor data, and never
dispatches a WhatsApp action. It measures app policy, not DeepSeek's prose quality.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import assistant
import chat_policy
import conversation_insights
import dm_composer
import task_intent


def classify(prompt, state=None):
    state = state or {}
    review = conversation_insights.wants_review(prompt)
    intent = chat_policy.intent(prompt)
    offered = (
        []
        if review or chat_policy.smalltalk(prompt)
        else [
            t["function"]["name"]
            for t in assistant.CHAT_TOOLS
            if chat_policy.permitted(t["function"]["name"], prompt)
        ]
    )
    plan = task_intent.steps(chat_policy.owner_text(prompt))
    send = bool(intent["send"] and not review)
    left = state.get("left", None)
    can_post = bool(send and (left is None or left > 0) and not state.get("hold", False))
    return {
        "history_review": review,
        "send_authorized": send,
        "offered_tools": offered,
        "steps": [p["kind"] for p in plan],
        "distinct_sends": len(task_intent.send_clauses(chat_policy.owner_text(prompt))),
        "can_post": can_post,
        "unverified_medical": dm_composer.unverified_medical_claim(prompt),
    }


def call_api(prompt, options, context):
    variables = (context or {}).get("vars") or {}
    state = variables.get("state") or {}
    if isinstance(state, str):
        state = json.loads(state)
    data = classify(str(variables.get("input") or prompt), state)
    return {"output": json.dumps(data, ensure_ascii=False, separators=(",", ":"))}

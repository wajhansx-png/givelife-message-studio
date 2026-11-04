"""Live-model benchmark for the GiveLife chat. Fake tools only: nothing is ever sent.

Runs every benchmark case that reaches the model (tests/chat_bench.py) through the real chat
loop, once per model, and reports first-attempt accuracy, tool success, speed and model calls.

    DEEPSEEK_API_KEY=... python scripts/chat_benchmark.py --models deepseek-chat,deepseek-reasoner
"""

import argparse, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
import assistant
import chat_bench
import chat_policy
import manual_commands

STATE = {
    "left": 25000,
    "autopilot": True,
    "whatsapp": True,
    "case_name": "Yousaf janazah",
    "drafts": chat_bench.STATE["drafts"],
    "draft_task": chat_bench.STATE["draft_task"],
    "engine": {"group_intervals": {"main": 15, "fiverr": 30, "upwork": 30}},
    "schedules": [],
}


def fake_tools(calls):
    def tool(name):
        def run(**args):
            calls.append(name)
            if name == "get_message":
                return {"kind": args.get("kind", "group"), "text": STATE["drafts"].get(args.get("kind", "group"), "")}
            if name == "find_contact":
                return json.dumps([{"id": "923001234567@s.whatsapp.net", "name": "Ali Khan", "group": False}])
            if name in ("recent_activity", "list_rules", "app_status", "list_schedules", "search_memory"):
                return "Auto is on. No send in the last 10 minutes. No pending schedules."
            return "Simulated " + name + " succeeded. Nothing was really sent."

        return run

    return {t["function"]["name"]: tool(t["function"]["name"]) for t in assistant.CHAT_TOOLS}


def model_cases():
    """Cases the model must handle: not taken by a deterministic command."""
    out = []
    for case in chat_bench.CASES + chat_bench.HELD_OUT:
        fast = (manual_commands.parse(case["text"]) or {}).get("kind")
        if fast and chat_policy.fast_command_eligible(case["text"]):
            continue
        out.append(case)
    return out


def run_case(case):
    calls = []
    started = time.monotonic()
    error = ""
    try:
        result = assistant.chat(case["text"], case.get("history", []), STATE, [], fake_tools(calls)) or {}
    except Exception as e:
        result, error = {}, str(e)[:200]
    seconds = time.monotonic() - started
    need, forbid = case.get("tools", set()), case.get("forbid", set())
    used = set(calls)
    tool_ok = bool(need & used) if need else True
    safe = not (forbid & used)
    ok = bool(result.get("reply")) and tool_ok and safe and not error
    diag = result.get("diagnostics") or {}
    return {
        "id": case["id"],
        "ok": ok,
        "tool_ok": tool_ok,
        "safe": safe,
        "calls": calls,
        "model_calls": diag.get("iterations", 0),
        "seconds": round(seconds, 2),
        "error": error or "; ".join(diag.get("errors", [])[:2]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"))
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    if not assistant.client():
        sys.exit("Set DEEPSEEK_API_KEY to run the live benchmark. No model was called.")
    cases = model_cases()
    report = {}
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        os.environ["DEEPSEEK_REASONING_MODEL"] = model
        rows = [run_case(c) for c in cases]
        n = len(rows)
        report[model] = {
            "first_attempt_accuracy": round(sum(r["ok"] for r in rows) / n, 3),
            "tool_success": round(sum(r["tool_ok"] for r in rows) / n, 3),
            "unsafe_calls": sum(not r["safe"] for r in rows),
            "avg_seconds": round(sum(r["seconds"] for r in rows) / n, 2),
            "avg_model_calls": round(sum(r["model_calls"] for r in rows) / n, 2),
            "failures": [r for r in rows if not r["ok"]],
        }
        print(f"{model}: {report[model]['first_attempt_accuracy']:.0%} first-attempt, "
              f"{report[model]['tool_success']:.0%} tools, {report[model]['unsafe_calls']} unsafe, "
              f"{report[model]['avg_seconds']}s avg, {report[model]['avg_model_calls']} calls/turn")
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, default=list))


if __name__ == "__main__":
    main()

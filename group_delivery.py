"""Human-readable, receipt-grounded summaries for group sending.

A non-successful gateway response is never represented as a confirmed send.
No retries are initiated here: an uncertain send may have reached WhatsApp.
"""


def summarize(results, destinations):
    """Summarize actual per-group gateway receipts; never infer success."""
    destinations = list(destinations)
    total = len(destinations)
    outcomes = [r for r in (results or []) if isinstance(r, dict)]
    successes = sum(r.get("code") == "SUCCESS" for r in outcomes)
    if total and successes == total:
        return f"Confirmed sent to {successes}/{total} groups."

    if successes:
        line = f"Only {successes}/{total} group sends confirmed."
    else:
        line = f"Not confirmed: 0/{total} group sends. Nothing is marked as delivered."

    failures = []
    for r in outcomes:
        if r.get("code") == "SUCCESS":
            continue
        name = str(r.get("group") or "Group").strip()
        detail = str(r.get("message") or r.get("error") or r.get("code") or "No delivery receipt").strip()
        failures.append(f"{name}: {detail[:260]}")
    if not outcomes:
        failures.append("The send stopped before a gateway receipt was recorded.")
    if len(outcomes) < total:
        failures.append(f"{total - len(outcomes)} destination(s) had no send attempt or receipt.")

    return line + " " + " | ".join(failures) + " Do not resend without checking WhatsApp."

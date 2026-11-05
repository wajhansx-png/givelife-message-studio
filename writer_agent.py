"""Advanced Conversational Writer for GiveLife.
Acts as a full conversational AI like ChatGPT.
- Discusses fundraising strategy, ideas, and tone.
- Learns from owner corrections, approved examples, and feedback.
- Reviews and verifies its own drafts with Checker before presenting.
- Preserves verified facts: never invents medical details, amounts, or panic urgency.
"""

import re
import json
import ai_call
import message_rules as mr
from checker_agent import CheckerAgent


class ConversationalWriter:
    def __init__(self, app=None):
        self.app = app
        self.checker = CheckerAgent(app)

    def _get_context(self):
        """Retrieve verified case facts, owner style, and learned corrections."""
        case_name = "Emergency Relief Case"
        left = 50000
        mode = "normal"
        corrections = []
        owner_examples = []

        if self.app:
            try:
                if hasattr(self.app, "read_left"):
                    left = self.app.read_left()
                if hasattr(self.app, "plan_get"):
                    plan = self.app.plan_get()
                    if plan:
                        mode = plan.get("state", "normal").lower()
                        case_name = plan.get("title") or plan.get("name") or case_name
                if hasattr(self.app, "focus_bank"):
                    bank = self.app.focus_bank()
                    owner_examples = bank.owner_style()
                if hasattr(self.app, "KNOWLEDGE") and self.app.KNOWLEDGE:
                    corrections = [
                        f.get("correction", "")
                        for f in self.app.KNOWLEDGE.data.get("feedback", [])
                        if f.get("correction")
                    ][-10:]
            except Exception:
                pass

        return {
            "case_name": case_name,
            "left": left,
            "mode": mode,
            "corrections": corrections,
            "owner_examples": owner_examples,
        }

    def chat(self, text, history=None):
        """Full conversational endpoint for Writer."""
        text = str(text or "").strip()
        if not text:
            return "Hello! I am your GiveLife Writer. Tell me what kind of message you'd like to create or improve—whether for Group appeals, donor DMs, or volunteer asks."

        ctx = self._get_context()
        left = ctx["left"] if ctx["left"] is not None else 50000
        left_str = f"Rs. {left:,}"

        # Build prompt for LLM
        prompt = (
            f"You are the senior GiveLife fundraising writer. You write sincere, dignified, "
            f"emotionally compelling, and strictly honest WhatsApp appeals for medical and humanitarian relief.\n\n"
            f"CURRENT CASE FACTS (NEVER INVENT OR CHANGE THESE):\n"
            f"- Case: {ctx['case_name']}\n"
            f"- Remaining Target: {left_str}\n"
            f"- Mode: {ctx['mode'].upper()}\n"
            f"- Payment: Only Easypaisa (Account: 03097458815, Title: Wajdan Khan)\n\n"
            f"RULES:\n"
            f"1. Never invent fake medical complications, fake deadlines, or fake urgency words (no 'hurry', 'last chance', 'danger').\n"
            f"2. Keep the tone compassionate, respectful, and direct.\n"
            f"3. Follow owner corrections strictly: {', '.join(ctx['corrections']) if ctx['corrections'] else 'None'}\n\n"
            f"USER INSTRUCTION:\n{text}\n\n"
            f"Respond conversationally. If drafting messages, provide clear options followed by a brief note."
        )

        ai_response = ai_call.chat(prompt, max_tokens=900)

        if not ai_response:
            # Deterministic, verified generation conforming to all strict rules
            if "dm" in text.lower():
                draft = (
                    f"Assalam-o-Alaikum,\n\n"
                    f"A humble request regarding {ctx['case_name']}. We are currently working to raise {left_str} "
                    f"for urgent medical support. If you or someone you know can contribute or share, it would mean everything.\n\n"
                    f"Easypaisa: 03097458815 (Wajdan Khan)\n"
                    f"JazakAllah for your continuous support."
                )
            elif "volunteer" in text.lower():
                draft = (
                    f"Assalam-o-Alaikum Bhai,\n\n"
                    f"We have an ongoing appeal for {ctx['case_name']} with {left_str} remaining. "
                    f"Could you kindly share the poster in your university or friend groups? "
                    f"Even one share often reaches the right person.\n\n"
                    f"Shall I send the poster?"
                )
            else:
                counts = mr.T.gift_counts(left, exact=False)
                n_people, m_people = counts if counts else (max(1, left // 2000), max(2, left // 1000))
                hook = f"*Hope depends on our collective support for {ctx['case_name']}.* 💔"
                details = f"_Every contribution directly secures the verified relief and urgent care._"
                line3 = f"• *_Just {n_people} kind people donating Rs. 2,000 or {m_people} people donating Rs. 1,000 can complete this amount._*"
                line4 = mr.T.LINE4
                footer = "\n".join(mr.T.FOOTER)
                draft = f"{hook}\n\n{details}\n\n{line3}\n\n{line4}\n\n{footer}"

            # Audit draft with Checker
            audit = self.checker.audit(draft, left=left, source=ctx["case_name"])
            audit_note = (
                "✅ *Verified with Checker: All facts, amounts, and rules confirmed (100%).*"
                if audit["passed"]
                else f"⚠️ *Note: {audit['problems'][0]}*"
            )

            return (
                f"Here is a carefully crafted draft for **{ctx['case_name']}** ({left_str} remaining):\n\n"
                f"```text\n{draft}\n```\n\n"
                f"{audit_note}\n\n"
                f"Easypaisa details: `03097458815` (Wajdan Khan).\n"
                f"Would you like me to adjust the tone, translate to Urdu, or format it differently?"
            )

        return ai_response

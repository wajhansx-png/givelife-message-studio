# GiveLife V1: reliability tests, not mythical self-training

## What the evaluation does

GiveLife's real chat and WhatsApp data are **not included** in this repository.
The 20 checked-in cases at `tests/evals/goldens.json` are anonymized examples
reported by the owner in chat plus synthetic corner cases. They do **not** prove
that the full historical production chat was inspected.

The app stores (within current retention limits) owner turns, explicit
corrections, and tool error lessons. The read-only conversation review derives
theme summaries and tool-failure counts locally. Do not copy the raw history,
donor numbers, health records, secrets, or private WhatsApp conversations into
issues, public branches, CI artifacts, or third-party evaluation tools.

### Quick deterministic gate (no API usage)

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p test_policy_goldens.py -v
python -m unittest discover -s tests -v
```

### Open-source Promptfoo evaluation (optional)

[Promptfoo](https://github.com/promptfoo/promptfoo) evaluates and red-teams LLM
systems. Its `file://` Python provider is used here so the test runs locally
without a model API key or external WhatsApp service:

```sh
npx promptfoo@latest eval --config promptfooconfig.yaml --no-cache --no-share
```

It executes the **actual GiveLife policy and intent modules** with fake inputs,
not a fake copy of the rules. Results are checked against the same golden corpus.
The separate `promptfoo-guardrails.yml` workflow runs it in GitHub Actions.

**Scope limit:** This is a deterministic permission/intent gate, **not** a
live DeepSeek answer-quality, retrieval-quality, or end-to-end agent score.
Treating a green policy test as evidence that DeepSeek reliably reasons or
sends messages would be incorrect.

### Future live-model evaluation (controlled, consented, and costly)

After owner approval, add a separate evaluator that mocks **all outbound**
actions and tests the production DeepSeek model using a private, reviewed
evaluation dataset. Score: intent fidelity, multi-turn referent resolution,
retrieval faithfulness, tool selection/arguments, partial-completion reporting,
medical-fact restraint, and cost/latency. Run repeated samples and preserve
hold-out cases, rather than optimizing only on the test set.

[DeepEval](https://github.com/confident-ai/deepeval) is a suitable option
for answer relevance, tool-call correctness, task completion and multi-turn
faithfulness; these often use LLM judging and may incur API cost. Keep private
conversation data local or use an explicitly approved private evaluation model.

## Quality gates before deployment

1. All deterministic safety and policy goldens pass; **zero** known unsafe
   send authorization or falsified delivery confirmations.
2. Full Python and JavaScript unit suites pass and browsers cover common
   phone/desktop widths, keyboard focus, overflow and menus.
3. Test using a fake WhatsApp transport; never run automated tests against
   production donors, volunteers, groups or live cases.
4. Inspect CI failure logs and the current deployed SHA. A pushed commit is not
   proof of a successful Render deployment.
5. Log genuine failures without automatically retrying uncertain sends.
   Promote owner-confirmed, **anonymized** failures into new regression goldens.

## Root-cause checklist

- **Wrong intent:** status vs advice vs historical analysis vs write action.
- **Wrong context:** current case vs old case, owner correction vs older AI guess.
- **Wrong recipient:** exact phone/name mapping, unambiguous chat target.
- **Partial task:** tracked substeps, completion receipts and missing work.
- **Risky retry:** uncertain WhatsApp outcome, restart, idempotency.
- **Factual inaccuracy:** unsupported medical claims, wrong arithmetic or balance.
- **Poor answers:** repetitive case status instead of past-chat recommendations.
- **UI breakage:** narrow/cropped replies, keyboard focus loss, unreachable menus.
- **Cost/reliability:** context budget and hosting limits.

A repository or prompt cannot eliminate every future bug. We use regression
data, protected execution, observability and repeated validation to reduce them.

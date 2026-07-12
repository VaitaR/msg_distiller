"""Test prompt variants on problem cases and compare results.

Usage:
    python scripts/test_prompt_variants.py
"""

import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# Load .env if present
_env_file = ROOT / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

# ── Load base prompt ──────────────────────────────────────────────────────────
with open(ROOT / "config/prompts/slack.yaml") as f:
    base_config = yaml.safe_load(f)

BASELINE_SYSTEM = base_config["system"]

# ── Build 3 patched variants ──────────────────────────────────────────────────

# Variant A: Hypothesis gate — no exception for "date + team"
# --- Variant A patches ---
_HYPO_OLD = (
    '- Hypothesis, idea pitch, brainstorm, or proposal (signal words: "hypothesis",\n'
    '  "гипотеза", "concept", "idea", "what if", "концепция", "предложение к обсуждению",\n'
    '  "backlog", "brainstorm") — unless a concrete date + team is also stated'
)
_HYPO_NEW = (
    '- Hypothesis, idea pitch, brainstorm, or proposal (signal words: "hypothesis",\n'
    '  "гипотеза", "concept", "idea", "what if", "концепция", "предложение к обсуждению",\n'
    '  "backlog", "brainstorm") — ALWAYS a non-event. No exception: even if dates or\n'
    "  teams are mentioned, a message framed primarily as a hypothesis/backlog/idea is\n"
    "  never an event."
)
_SIGNAL_OLD = (
    'Signal phrases that strongly indicate non-event: "гипотеза", "hypothesis",\n'
    '"brainstorm", "полчаса", "join us", "last day", "увидимся", "мой последний день".'
)
_SIGNAL_NEW = (
    'Signal phrases that strongly indicate non-event: "гипотеза", "hypothesis",\n'
    '"brainstorm", "полчаса", "join us", "last day", "увидимся", "мой последний день",\n'
    '"предлагаю добавить", "backlog", "что если".'
)
_FUTURE_GATE_NEW = (
    "A forward-looking sentence qualifies for its own event ONLY when:\n"
    "- Condition (a) IS MANDATORY: explicit calendar date or deadline required.\n"
    "  PLUS at least ONE of:"
)
_FUTURE_GATE_OLD = (
    "A forward-looking sentence qualifies for its own event ONLY when it satisfies\n"
    "at least TWO of the following:"
)

VARIANT_A = BASELINE_SYSTEM.replace(_HYPO_OLD, _HYPO_NEW).replace(
    _SIGNAL_OLD, _SIGNAL_NEW
)
assert VARIANT_A != BASELINE_SYSTEM, "Variant A patch failed"

# Variant B: False-negative fix — positive trigger rules for terse release msgs
POSITIVE_TRIGGER_BLOCK = """
  POSITIVE TRIGGER RULES (override non-event detection):
  - Any message containing "released", "launched", "opened", "enabled", "rolled out",
    "shipped", "just deployed", "live", "вышло", "запустили", "выпустили", "добавили",
    "открыли" describing a company-internal action or product IS an event.
  - Internal tool improvements (compliance automation, support bot updates, KYT/AML
    flow changes, Retool module updates) ARE events if they reduce manual work or
    affect user-facing or compliance workflows.
  - A one-line message like "We added X to P2P" or "X is now live" is a valid event
    even without additional context. Do not reject purely for brevity.

"""

VARIANT_B = BASELINE_SYSTEM.replace(
    "Future-Mention Gate (CRITICAL):",
    POSITIVE_TRIGGER_BLOCK + "Future-Mention Gate (CRITICAL):",
)
assert VARIANT_B != BASELINE_SYSTEM, "Variant B patch failed"

# Variant C: A + B + tighter Future-Mention Gate (explicit date mandatory)
VARIANT_C = VARIANT_A.replace(
    "Future-Mention Gate (CRITICAL):",
    POSITIVE_TRIGGER_BLOCK + "Future-Mention Gate (CRITICAL):",
).replace(_FUTURE_GATE_OLD, _FUTURE_GATE_NEW)
assert VARIANT_C != VARIANT_A, "Variant C future-gate patch failed"

VARIANTS = {
    "Baseline": BASELINE_SYSTEM,
    "Variant A (hypothesis fix)": VARIANT_A,
    "Variant B (FN fix)": VARIANT_B,
    "Variant C (A+B+gate)": VARIANT_C,
}

# ── Test cases ─────────────────────────────────────────────────────────────────
# IMPORTANT: FP texts are taken directly from the llm_calls table (real production failures).
CASES = [
    # --- FALSE POSITIVES: confirmed from llm_calls — these DID extract events in prod ---
    {
        "label": "FP1: AI hypothesis (5 events in prod!)",
        "expected_is_event": False,
        "expected_events": 0,
        "text": (
            "<@U06M0G5T4DV>\n"
            "*Гипотеза: Wallet + AI Agents в Telegram* \n"
            "*после прочтения:*\n"
            "https://t.me/danokhlopkov/1639 (Lead analyst TON Foundation)\n"
            "https://identityhub.app/blog/telegram-default-ai-interface (полный обзор)\n\n"
            "Telegram становится дефолтным AI-интерфейсом. Нам надо думать как встроить "
            "Wallet в эту парадигму.\n\n"
            "5 идей:\n"
            "1. Wallet + AI agents в Telegram — backlog, гипотеза\n"
            "2. Wallet Pay for AI services — subscriptions, pay-per-use\n"
            "3. Transfers to agent addresses — sub-account in crypto wallet\n"
            "4. Agent-to-agent settlements inside messenger\n"
            "5. Make something simple but shareable for AI channels"
        ),
    },
    {
        "label": "FP2: Pipit tool recommendation (2 events in prod!)",
        "expected_is_event": False,
        "expected_events": 0,
        "text": (
            "http://pipitvoice.com\n"
            "> Pipit - это WhisprFlow локальный у вас на компьютере, бесплатно и очень "
            "хорошо превращает наговаривание в текст без ошибок (ну почти).\n"
            "> Первое что видишь в окошке Pipit - сколько ты уже успел сэкономить времени, "
            "не печатая, а говоря с компьютером\n"
            "По следам с семинара Клода, предлагаю добавить на семинарную страницу"
        ),
    },
    {
        "label": "FP3: Demo invite w/ teams (1 event in prod!)",
        "expected_is_event": False,
        "expected_events": 0,
        "text": (
            "Давно не было у нас продуктовых демо!\n\n"
            "Сегодня команды TON Wallet и P2P Market покажут интеграцию P2P в TON Wallet.\n\n"
            "Увидимся через полчаса!"
        ),
    },
    # --- FALSE NEGATIVES: messages where we WANT events extracted ---
    {
        "label": "FN1: Terse currency launch (XOF)",
        "expected_is_event": True,
        "expected_events": 1,
        "text": "We just opened XOF currency in P2P",
    },
    {
        "label": "FN2: Terse currency add (MUR+DZD)",
        "expected_is_event": True,
        "expected_events": 1,
        "text": "We added MUR and DZD currencies to P2P",
    },
    {
        "label": "FN3: Compliance rollout (LexisNexis KYC1)",
        "expected_is_event": True,
        "expected_events": 1,
        "text": (
            "Compliance Release: LexisNexis AML screening for KYC Level 1 (progressive rollout)\n\n"
            "Hi everyone, we started rolling out LexisNexis screening to KYC Level 1 users.\n\n"
            "Before this release, KYC1 relied only on LLM-based screening. "
            "Now LexisNexis is also applied for a growing subset of users."
        ),
    },
    {
        "label": "FN4: Support bot decision tree revamp",
        "expected_is_event": True,
        "expected_events": 1,
        "text": (
            "Support Bot update: Crypto Wallet & P2P Market branches refreshed\n\n"
            "Hi team! We've fully revamped the Support Bot decision trees for Crypto Wallet "
            "and P2P Market."
        ),
    },
    {
        "label": "FN5: Earn button (must be exactly 1 event, not 2)",
        "expected_is_event": True,
        "expected_events": 1,
        "text": (
            "<!here> Hi everyone!\n\n"
            "Another small but useful update from the TON Wallet team.\n\n"
            "We've added an Earn button to the incoming USDT transfer notification "
            "(only transactions above $1 are counted). Since the introduction of this button, "
            "around 7% of all staking actions now happen via this button.\n\n"
            "The team is also planning to extend the Earn button feature beyond USDT to "
            "other earn options."
        ),
    },
]


# ── API call ──────────────────────────────────────────────────────────────────
def call_llm(
    system: str, message: str, model: str = "gpt-4o-mini", temperature: float = 0.0
) -> dict:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content)


# ── Run experiments ───────────────────────────────────────────────────────────
# ── Run experiments ───────────────────────────────────────────────────────────
# Run with both: gpt-4o-mini@0 (cheap/fast) and gpt-5.4-mini@0.3 (production settings)
RUN_CONFIGS = [
    ("gpt-4o-mini", 0.0),
    ("gpt-5.4-mini", 0.3),
]

all_results: dict[str, dict[str, list[dict]]] = {}  # model_key → variant → results

for model, temp in RUN_CONFIGS:
    model_key = f"{model}@t{temp}"
    print(f"\n{'=' * 60}\nModel: {model_key}\n{'=' * 60}")
    results: dict[str, list[dict]] = {v: [] for v in VARIANTS}

    for case in CASES:
        for vname, vsystem in VARIANTS.items():
            try:
                out = call_llm(vsystem, case["text"], model=model, temperature=temp)
                is_event = out.get("is_event", False)
                events = out.get("events", [])
                n = len(events)
                correct = is_event == case["expected_is_event"]
                if case["expected_is_event"] and case["expected_events"] is not None:
                    correct = correct and (n == case["expected_events"])
                results[vname].append(
                    {
                        "label": case["label"],
                        "expected_is_event": case["expected_is_event"],
                        "expected_events": case["expected_events"],
                        "got_is_event": is_event,
                        "got_events": n,
                        "correct": correct,
                    }
                )
            except Exception as e:
                results[vname].append(
                    {
                        "label": case["label"],
                        "expected_is_event": case["expected_is_event"],
                        "expected_events": case["expected_events"],
                        "got_is_event": None,
                        "got_events": None,
                        "correct": False,
                        "error": str(e),
                    }
                )
                print(f"  [{vname[:10]}] {case['label'][:45]}: ERROR: {e}")
                continue
            print(
                f"  [{vname[:10]}] {case['label'][:45]}: "
                f"is_event={results[vname][-1]['got_is_event']} "
                f"n={results[vname][-1]['got_events']} "
                f"{'✅' if results[vname][-1]['correct'] else '❌'}"
            )
    all_results[model_key] = results

# ── Summary table ─────────────────────────────────────────────────────────────
overall_pass: dict[str, dict[str, float]] = {}  # model_key → variant → pass_rate

for model_key, results in all_results.items():
    print(f"\n\n{'=' * 80}")
    print(f"RESULTS TABLE — {model_key}")
    print("=" * 80)
    print(f"{'Case':<47} {'Base':^8} {'Var A':^8} {'Var B':^8} {'Var C':^8}")
    print("-" * 80)
    for i, case in enumerate(CASES):
        row = f"{case['label']:<47}"
        for vname in VARIANTS:
            r = results[vname][i]
            cell = "✅" if r["correct"] else f"❌{r['got_events']}"
            row += f" {cell:^8}"
        print(row)

    print("-" * 80)
    pass_rates: dict[str, float] = {}
    for vname in VARIANTS:
        correct = sum(r["correct"] for r in results[vname])
        total = len(results[vname])
        pass_rates[vname] = correct / total
        print(f"  {vname:<40}: {correct}/{total} = {correct / total * 100:.0f}%")
    overall_pass[model_key] = pass_rates

# ── Final recommendation ───────────────────────────────────────────────────────
print("\n\n" + "=" * 80)
print("FINAL RECOMMENDATION")
print("=" * 80)
# Use production model results (gpt-5.4-mini) for the recommendation
prod_key = next((k for k in overall_pass if "gpt-5.4" in k), list(overall_pass)[-1])
prod_rates = overall_pass[prod_key]
best = max(prod_rates, key=prod_rates.get)
print(f"Based on production model ({prod_key}):")
print(f"  BEST variant: {best} ({prod_rates[best] * 100:.0f}% pass rate)")
if prod_rates[best] > prod_rates.get("Baseline", 0):
    print("  → Apply this variant to config/prompts/slack.yaml")
else:
    print(
        "  → Baseline already handles all cases; apply Variant C as defensive hardening"
    )
print("=" * 80)

#!/usr/bin/env python3
"""Quick prompt quality test on 7 problematic cases from the quality report."""
import yaml, json, os, sys
from datetime import datetime, UTC
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('.env')

with open('config/prompts/slack.yaml') as f:
    prompt_cfg = yaml.safe_load(f)

from openai import OpenAI
client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

test_cases = [
    ('HYPOTHESIS (should be is_event=false)',
     'Гипотеза: Wallet + AI Agents в Telegram\nTL;DR: TG - топ интерфейс для AI продуктов. Нашел 183 AI-бота с 44.3M MAU.\nПредлагаю добавить в бэклог: Wallet Pay for AI services (subscriptions, pay-per-use), Internal transfers to agent addresses, Agent-to-agent settlements.'),

    ('MEETING INVITE (should be is_event=false)',
     'Давно не было у нас продуктовых демо!\nСегодня команды TON Wallet и P2P Market покажут интеграцию P2P в TON Wallet.\nУвидимся через полчаса!'),

    ('FAREWELL (should be is_event=false)',
     'FYI - с сегодняшнего дня по вопросам FAQ и новым задачам на статьи можно обращаться к @user\nСегодня мой последний день работы в Кошельке. Тамина будет координировать дальнейшую работу по направлению FAQ'),

    ('MULTI-FEATURE one message (should be 1-2 events, NOT 3+)',
     'Hey team! Today we introduce 5 new xStocks: COPPx(Copper), PALLx(Palladium), PPLTx(Platinum), SLVx(Silver), BTGOx(BitGo Holdings). We also added a new Metals section in Trade. And a new Trending tab (50% rollout).'),

    ('EXTERNAL redesign (company action as object)',
     'Telegram for Android got its biggest redesign ever — and Wallet kept up. Updated user interface, refreshed components, the new bottom bar. Kudos to the team!'),

    ('LABEL RENAME (should be Deploy, low importance)',
     'Hey team! In the context of preparing to launch the Loyalty program in Wallet, we renamed Earns in Russian from "Бонусы" to "Доход"'),

    ('USDC DEPOSITS with future mention (should NOT split withdrawal into separate event)',
     'We have just opened USDC deposits with auto-conversion to USDT for all employees internally. Tomorrow we are polishing details before rolling out to all users. Note: USDC withdrawals will be available in a subsequent release.'),
]

system_prompt = prompt_cfg['system']
ts = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC).isoformat()

results = []
for name, msg in test_cases:
    user_msg = f'Message timestamp: {ts}\nChannel: #releases\n\nMessage:\n{msg}'
    resp = client.chat.completions.create(
        model='gpt-4.1-mini',
        temperature=0.0,
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_msg},
        ],
        response_format={'type': 'json_object'},
        max_tokens=2000,
    )
    result = json.loads(resp.choices[0].message.content)
    is_event = result.get('is_event')
    events = result.get('events', [])
    results.append((name, is_event, events))
    print(f'\n=== {name} ===')
    print(f'is_event: {is_event}  events_count: {len(events)}')
    for e in events:
        print(f'  action={e.get("action")} object={e.get("object_name_raw")[:60]} status={e.get("status")}')
        if e.get('summary'):
            print(f'  summary: {e["summary"][:120]}')

print('\n\n=== PASS/FAIL SUMMARY ===')
expected = [False, False, False, 2, 1, 1, 1]  # max events expected
for (name, is_event, events), exp in zip(results, expected):
    if exp is False:
        ok = not is_event
    else:
        ok = is_event and len(events) <= exp
    status = 'PASS' if ok else 'FAIL'
    print(f'{status}: {name[:50]} => is_event={is_event}, count={len(events)}')

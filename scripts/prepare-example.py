import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, 'backend')
from xmahjong.config import Settings
from xmahjong.logs import parse_payload
from xmahjong.state import decisions
async def main():
    events, _ = await parse_payload(Path('tests/fixtures/tenhou-ranked.json').read_bytes(), Settings())
    Path('tests/fixtures/example.mjai.jsonl').write_text('\n'.join(json.dumps(e, ensure_ascii=False) for e in events), encoding='utf-8')
    print('events', len(events), 'decisions', [len(decisions(events,a)) for a in range(4)])
asyncio.run(main())

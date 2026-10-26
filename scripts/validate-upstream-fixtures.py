import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "backend")
from xmahjong.state import decisions, public_counts

fixtures = list(Path("vendor/convlog/tests/testdata").glob("*.json"))
total = 0
for f in fixtures:
    p = subprocess.run(
        ["docker", "run", "--rm", "-i", "xmahjong/convlog:local"],
        input=f.read_bytes(),
        capture_output=True,
        check=False,
        timeout=30,
    )
    if p.returncode:
        raise RuntimeError(f.name)
    events = [json.loads(x) for x in p.stdout.splitlines()]
    total += len(events)
    for a in range(4):
        for d in decisions(events, a):
            assert max(public_counts(d["state"])) <= 4, (f.name, a, d["id"])
print(
    "verified", len(fixtures), "upstream converter fixtures;", total, "events; all 4 seats public counts <= 4"
)

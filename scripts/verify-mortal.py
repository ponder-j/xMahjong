"""Live native-engine checks on real MJAI snapshots, including post-call discards."""

import asyncio
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from xmahjong.analysis import analyze
from xmahjong.config import load_settings
from xmahjong.state import decisions, legal_discards
from xmahjong.tiles import action_key


async def main():
    cfg = load_settings()
    events = [
        json.loads(line)
        for line in (ROOT / "tests/fixtures/example.mjai.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    snapshots = decisions(events, 0)
    selected = [
        next(d for d in snapshots if d["kind"] == "self"),
        next(d for d in snapshots if d["state"]["trigger"]["type"] == "pon"),
        next(d for d in snapshots if d["kind"] == "self" and d["state"]["turn"] >= 9),
        next(d for d in reversed(snapshots) if d["kind"] == "self"),
    ]
    scan = "--scan-disagreements" in sys.argv
    if scan:
        selected_ids = {d["id"] for d in selected}
        selected.extend(d for d in snapshots if d["kind"] == "self" and d["id"] not in selected_ids)
    output = []
    for decision in selected:
        report = await analyze(events, decision, cfg)
        engines = {e["name"]: e for e in report["engines"]}
        assert engines["mortal"]["status"] == "ok", engines["mortal"]["message"]
        post_call = decision["state"]["trigger"]["type"] in ("chi", "pon", "reach")
        assert engines["akochan"]["status"] == ("unsupported" if post_call else "ok"), engines["akochan"][
            "message"
        ]
        mortal = engines["mortal"]
        assert math.isclose(sum(c["probability"] for c in mortal["candidates"]), 1, abs_tol=1e-6)
        legal = {action_key(a) for a in legal_discards(decision["state"])}
        for c in mortal["candidates"]:
            assert math.isfinite(c["score"])
            if c["moves"][0]["type"] == "dahai":
                assert action_key(c["moves"][0]) in legal, c
        assert any(c["actual"] for c in report["candidates"])
        summary = {
            "decision_id": decision["id"],
            "trigger": decision["state"]["trigger"]["type"],
            "turn": decision["state"]["turn"],
            "disagreement": report["disagreement"]["level"],
            "mortal_candidates": len(mortal["candidates"]),
            "mortal_top": mortal["candidates"][0]["label"],
            "akochan_status": engines["akochan"]["status"],
            "akochan_top": engines["akochan"]["candidates"][0]["label"]
            if engines["akochan"]["candidates"]
            else None,
            "retained_candidates": len(report["candidates"]),
        }
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        output.append(summary)
        if scan and len(output) >= 4 and summary["disagreement"] in ("minor", "conflict"):
            break
    artifact = ROOT / "artifacts/mortal-verification.json"
    artifact.parent.mkdir(exist_ok=True)
    artifact.write_text(
        json.dumps(
            {"model": cfg.mortal.version, "weight_sha256": cfg.mortal.weight_sha256, "snapshots": output},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    asyncio.run(main())

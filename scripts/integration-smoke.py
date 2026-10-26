"""Exercise live API, actual Akochan and an OpenAI-compatible LLM; no engine doubles."""

import argparse
import json
import time
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--require-both", action="store_true")
    parser.add_argument("--decision-id", type=int, help="Validate a particular decision in the replay")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--replay-id", help="Validate an already imported real replay")
    source.add_argument("--majsoul-link", help="Download and validate an authorized Mahjong Soul replay")
    args = parser.parse_args()
    started = time.time()
    with httpx.Client(base_url=args.url, timeout=600) as client:

        def request(method, path, **kwargs):
            res = client.request(method, path, **kwargs)
            res.raise_for_status()
            return res.json()

        if args.replay_id:
            replay = args.replay_id
            fixture = "existing imported replay"
        elif args.majsoul_link:
            replay = request("POST", "/api/replays/link", json={"url": args.majsoul_link})["id"]
            fixture = "authorized Mahjong Soul replay downloaded through the live API"
        else:
            replay = request("POST", "/api/replays/example")["id"]
            fixture = "upstream real Tenhou fixture; not Mahjong Soul acceptance"
        listing = request("GET", f"/api/replays/{replay}/decisions")
        if args.replay_id and "paipu=" in listing.get("source", ""):
            fixture = "authorized Mahjong Soul replay previously downloaded through the live API"
        decision = next(
            d
            for d in listing["decisions"]
            if d["id"] == args.decision_id or args.decision_id is None and d["kind"] == "self"
        )
        prefix = f"/api/replays/{replay}/decisions/{decision['id']}"
        report = request("POST", prefix + "/analyze?refresh=true")
        engines = {e["name"]: e["status"] for e in report["engines"]}
        assert engines["akochan"] == "ok", engines
        assert report["candidates"]  # Some positions have only one retained/forced choice.
        explanation = request("POST", prefix + "/explain")
        assert explanation["source"] == "llm", explanation["notice"]
        assert {c["candidate_id"] for c in explanation["candidates"]} == {
            c["id"] for c in report["candidates"]
        }
        answer = request(
            "POST",
            prefix + "/chat",
            json={"question": "目前能够确认哪张弃牌对哪家是现物？证据不足请明确说明。"},
        )
        assert answer["source"] == "llm", answer
        candidate = next(c for c in report["candidates"] if c.get("evidence"))
        cf = request("POST", prefix + "/counterfactual", json={"tile": candidate["moves"][-1]["pai"]})
        assert cf["evidence"] == candidate["evidence"]
        result = {
            "result": "complete" if all(v == "ok" for v in engines.values()) else "partial",
            "fixture": fixture,
            "replay_id": replay,
            "decision_id": decision["id"],
            "engines": engines,
            "candidates": len(report["candidates"]),
            "llm_model": explanation["model"],
            "llm_explanation": "passed",
            "llm_chat": "passed",
            "counterfactual": "passed",
            "seconds": round(time.time() - started, 2),
        }
        directory = Path(__file__).resolve().parents[1] / "artifacts"
        directory.mkdir(exist_ok=True)
        filename = (
            "integration-real-replay.json"
            if args.replay_id or args.majsoul_link
            else "integration-result.json"
        )
        (directory / filename).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
        if args.require_both:
            assert result["result"] == "complete", "Mortal is not running with a real trained checkpoint"


if __name__ == "__main__":
    main()

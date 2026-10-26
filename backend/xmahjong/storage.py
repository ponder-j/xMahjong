import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class Storage:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "xmahjong.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS replays (id TEXT PRIMARY KEY, title TEXT, source TEXT,
                    created TEXT, events TEXT, original TEXT);
                CREATE TABLE IF NOT EXISTS analyses (cache_key TEXT PRIMARY KEY, report TEXT);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        return db

    def save(self, events: list, original: dict | None, source: str) -> str:
        encoded = json.dumps(events, ensure_ascii=False, sort_keys=True)
        replay_id = hashlib.sha256(encoded.encode()).hexdigest()[:24]
        names = events[0].get("names", ["未知玩家"])
        title = " / ".join(names)
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO replays VALUES (?, ?, ?, ?, ?, ?)",
                (
                    replay_id,
                    title,
                    source[:500],
                    datetime.now(UTC).isoformat(),
                    encoded,
                    json.dumps(original, ensure_ascii=False) if original else None,
                ),
            )
        return replay_id

    def list(self) -> list:
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id, title, source, created FROM replays ORDER BY created DESC LIMIT 100"
                )
            ]

    def get(self, replay_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM replays WHERE id = ?", (replay_id,)).fetchone()
        if row is None:
            raise KeyError(replay_id)
        data = dict(row)
        data["events"] = json.loads(data["events"])
        data["original"] = json.loads(data["original"]) if data["original"] else None
        return data

    def cached(self, key: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT report FROM analyses WHERE cache_key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache(self, key: str, report: dict):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO analyses VALUES (?, ?)", (key, json.dumps(report, ensure_ascii=False))
            )

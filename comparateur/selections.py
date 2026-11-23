"""Stockage local des sélections préparées par le coordinateur."""
from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

DATABASE = Path(__file__).resolve().parent.parent / "var" / "carnet.sqlite3"


def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS selections (
        id TEXT PRIMARY KEY, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        mode TEXT NOT NULL, model TEXT NOT NULL, criteria TEXT NOT NULL, listings TEXT NOT NULL)""")
    return db


def save(identifier, mode, query, ranked, path=DATABASE):
    listings = [dict(car=asdict(r["car"]), score=r["score"]) for r in ranked[:3]]
    with closing(connect(path)) as db, db:
        db.execute("INSERT INTO selections (id, mode, model, criteria, listings) VALUES (?, ?, ?, ?, ?) "
                   "ON CONFLICT(id) DO NOTHING",
                   (identifier, mode, query.vehicle, json.dumps(asdict(query)), json.dumps(listings)))
    return len(listings)


def recent(path=DATABASE):
    with closing(connect(path)) as db:
        rows = db.execute("SELECT * FROM selections ORDER BY created DESC, rowid DESC LIMIT 20")
        return [{**dict(r), "criteria":json.loads(r["criteria"]), "listings":json.loads(r["listings"])} for r in rows]

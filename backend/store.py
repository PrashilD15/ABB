import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        (root / 'documents').mkdir(exist_ok=True)
        self.db = root / 'lab.sqlite3'
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS objects (kind TEXT, id TEXT, body TEXT, PRIMARY KEY(kind,id))')
            db.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, timestamp TEXT, kind TEXT, body TEXT)')
        # A process restart never resumes a controller sequence.
        for run in self.list('run'):
            if run['status'] == 'RUNNING':
                run['status'] = 'INTERRUPTED'
                run['finished'] = now()
                run['reason'] = 'Application restarted; explicit reconnection required.'
                self.put('run', run['id'], run)

    def connection(self):
        return sqlite3.connect(self.db)

    def put(self, kind, id, body):
        with self.connection() as db:
            db.execute('INSERT OR REPLACE INTO objects VALUES (?,?,?)', (kind, id, json.dumps(body)))

    def get(self, kind, id):
        with self.connection() as db:
            row = db.execute('SELECT body FROM objects WHERE kind=? AND id=?', (kind, id)).fetchone()
        if not row:
            raise KeyError(id)
        return json.loads(row[0])

    def list(self, kind):
        with self.connection() as db:
            rows = db.execute('SELECT body FROM objects WHERE kind=? ORDER BY rowid DESC', (kind,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def event(self, kind, body):
        with self.connection() as db:
            db.execute('INSERT INTO events(timestamp,kind,body) VALUES (?,?,?)', (now(), kind, json.dumps(body)))

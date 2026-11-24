"""Persistência SQLite do histórico e configurações."""
import json
import sqlite3
import threading

class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, kind TEXT, payload TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, payload TEXT)')
        self.db.commit()

    def append(self, kind, data):
        with self.lock:
            self.db.execute('INSERT INTO records(kind,payload) VALUES (?,?)', (kind, json.dumps(data, ensure_ascii=False)))
            self.db.commit()

    def read(self, kind, limit=1000):
        with self.lock:
            return [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM records WHERE kind=? ORDER BY id DESC LIMIT ?', (kind, limit))]

    def save(self, key, data):
        with self.lock:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(data)))
            self.db.commit()

    def get(self, key, default):
        with self.lock:
            row = self.db.execute('SELECT payload FROM settings WHERE key=?', (key,)).fetchone()
            return json.loads(row[0]) if row else default

    def close(self):
        with self.lock:
            self.db.close()

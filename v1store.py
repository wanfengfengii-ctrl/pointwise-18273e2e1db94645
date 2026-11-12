"""Frozen deployed writer and old schema; also a compatibility fixture."""
import json
import sqlite3
from vendor.clock1 import local_ns

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 generation INTEGER NOT NULL);
INSERT OR IGNORE INTO meta VALUES(1,0);
CREATE TABLE IF NOT EXISTS eras(
 station TEXT NOT NULL, start_ns INTEGER NOT NULL,
 end_ns INTEGER NOT NULL, offset_ns INTEGER NOT NULL,
 PRIMARY KEY(station,start_ns));
CREATE TABLE IF NOT EXISTS samples(
 id TEXT PRIMARY KEY, rev INTEGER NOT NULL, station TEXT NOT NULL,
 local TEXT NOT NULL, amount INTEGER NOT NULL, deleted INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS links(
 id TEXT PRIMARY KEY, rev INTEGER NOT NULL, a TEXT NOT NULL, b TEXT NOT NULL,
 lo INTEGER NOT NULL, hi INTEGER NOT NULL, deleted INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS receipts(
 batch_id TEXT PRIMARY KEY, request TEXT NOT NULL, response TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS journal(
 seq INTEGER PRIMARY KEY AUTOINCREMENT, generation INTEGER NOT NULL,
 kind TEXT NOT NULL, item_id TEXT NOT NULL, body TEXT NOT NULL);
"""
SAMPLE_FIELDS = ("id", "rev", "station", "local", "amount", "deleted")
LINK_FIELDS = ("id", "rev", "a", "b", "lo", "hi", "deleted")

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)

def integer(value):
    return type(value) is int and -(1 << 63) <= value < (1 << 63)

def text(value):
    return isinstance(value, str) and bool(value)

def validate(rows, fields):
    if type(rows) is not list:
        raise ValueError("ROWS")
    seen = set()
    for row in rows:
        if type(row) is not dict or set(row) != set(fields):
            raise ValueError("FIELDS")
        if not text(row["id"]) or row["id"] in seen:
            raise ValueError("ID")
        seen.add(row["id"])
        if not integer(row["rev"]) or row["rev"] <= 0 or type(row["deleted"]) is not bool:
            raise ValueError("REVISION")
        if fields == SAMPLE_FIELDS:
            if not text(row["station"]) or not integer(row["amount"]):
                raise ValueError("SAMPLE")
            local_ns(row["local"])
        else:
            if not text(row["a"]) or not text(row["b"]):
                raise ValueError("LINK")
            if not integer(row["lo"]) or not integer(row["hi"]) or row["lo"] > row["hi"]:
                raise ValueError("LINK_RANGE")

class Store:
    def __init__(self, db=":memory:"):
        self.db = sqlite3.connect(db, isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    def generation(self):
        return self.db.execute("SELECT generation FROM meta WHERE singleton=1").fetchone()[0]

    def _rows(self, table, fields):
        result = []
        for raw in self.db.execute("SELECT * FROM " + table + " ORDER BY id"):
            row = {key: raw[key] for key in fields}
            row["deleted"] = bool(row["deleted"])
            result.append(row)
        return result

    def snapshot(self):
        self.db.execute("BEGIN")
        try:
            value = {"generation": self.generation(),
                     "samples": self._rows("samples", SAMPLE_FIELDS),
                     "links": self._rows("links", LINK_FIELDS),
                     "receipts": [dict(r) for r in self.db.execute(
                         "SELECT * FROM receipts ORDER BY batch_id")]}
            self.db.execute("COMMIT")
            return value
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def apply(self, batch_id, samples, links):
        if not text(batch_id):
            raise ValueError("BATCH_ID")
        request = canonical({"samples": samples, "links": links})
        self.db.execute("BEGIN IMMEDIATE")
        try:
            receipt = self.db.execute(
                "SELECT request,response FROM receipts WHERE batch_id=?", (batch_id,)).fetchone()
            if receipt is not None:
                if receipt["request"] != request:
                    raise ValueError("BATCH_CONFLICT")
                self.db.execute("COMMIT")
                return json.loads(receipt["response"])
            validate(samples, SAMPLE_FIELDS)
            validate(links, LINK_FIELDS)
            accepted = []
            for table, rows, fields in (("samples", samples, SAMPLE_FIELDS),
                                        ("links", links, LINK_FIELDS)):
                for row in rows:
                    raw = self.db.execute("SELECT * FROM " + table + " WHERE id=?",
                                          (row["id"],)).fetchone()
                    if raw is not None:
                        old = {key: raw[key] for key in fields}
                        old["deleted"] = bool(old["deleted"])
                        if old["rev"] > row["rev"]:
                            continue
                        if old["rev"] == row["rev"]:
                            if old != row:
                                raise ValueError("REVISION_CONFLICT")
                            continue
                    placeholders = ",".join("?" for _ in fields)
                    self.db.execute("INSERT OR REPLACE INTO " + table + " VALUES(" +
                                    placeholders + ")", tuple(row[key] for key in fields))
                    accepted.append((table, row["id"], canonical(row)))
            known = {r[0] for r in self.db.execute("SELECT DISTINCT station FROM eras")}
            for row in self.db.execute("SELECT station FROM samples"):
                if row[0] not in known:
                    raise ValueError("UNKNOWN_STATION")
            missing = self.db.execute("""
                SELECT links.id FROM links
                LEFT JOIN samples a ON links.a=a.id
                LEFT JOIN samples b ON links.b=b.id
                WHERE links.deleted=0 AND (a.id IS NULL OR b.id IS NULL)
                ORDER BY links.id LIMIT 1
            """).fetchone()
            if missing:
                raise ValueError("MISSING_ENDPOINT")
            generation = self.generation() + 1
            self.db.execute("UPDATE meta SET generation=? WHERE singleton=1", (generation,))
            response = {"batch_id": batch_id, "generation": generation, "accepted": len(accepted)}
            encoded = canonical(response)
            self.db.execute("INSERT INTO receipts VALUES(?,?,?)", (batch_id, request, encoded))
            for kind, item_id, body in accepted:
                self.db.execute("INSERT INTO journal(generation,kind,item_id,body) VALUES(?,?,?,?)",
                                (generation, kind, item_id, body))
            self.db.execute("INSERT INTO journal(generation,kind,item_id,body) VALUES(?,?,?,?)",
                            (generation, "receipt", batch_id,
                             canonical({"request": request, "response": encoded})))
            self.db.execute("COMMIT")
            return response
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def read(self, station, start_local, end_local):
        start, end = local_ns(start_local), local_ns(end_local)
        if start >= end:
            raise ValueError("RANGE")
        if not text(station):
            raise ValueError("STATION")
        # One SELECT fixes a committed SQLite snapshot; sum uses unbounded Python integers.
        rows = list(self.db.execute(
            "SELECT id,local,amount FROM samples WHERE station=? AND deleted=0 ORDER BY id",
            (station,)))
        chosen = [r for r in rows if start <= local_ns(r["local"]) < end]
        return {"count": len(chosen), "sum": sum(r["amount"] for r in chosen)}

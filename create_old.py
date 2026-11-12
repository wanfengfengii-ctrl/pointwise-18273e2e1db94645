"""Materialize the supplied deployed database fixture."""
import json
import sys
from v1store import Store
from samples import seed

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python3 create_old.py DATABASE")
    store = Store(sys.argv[1])
    try:
        if store.generation() != 0 or store.db.execute("SELECT COUNT(*) FROM eras").fetchone()[0]:
            raise SystemExit("fixture destination must be empty")
        receipt = seed(store)
        assert store.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        print(json.dumps({"receipt": receipt, "snapshot": store.snapshot()}, sort_keys=True))
    finally:
        store.close()

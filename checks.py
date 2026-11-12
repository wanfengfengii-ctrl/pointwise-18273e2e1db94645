import copy
import json
import sys
from legacy import Store
from samples import INITIAL, CORRECTION, ERAS, MINUTE, seed, t
from vendor.clock2 import Clock

def normal():
    store = Store()
    try:
        receipt = seed(store)
        assert receipt == {"batch_id": "recording-1", "generation": 1, "accepted": 7}
        assert store.read("river", "2024-11-03T01:00:00.000000000",
                          "2024-11-03T01:25:00.000000000") == {"count": 2, "sum": 3}
        before = store.snapshot()
        assert store.apply(**INITIAL) == receipt
        assert store.snapshot() == before
        bad = copy.deepcopy(INITIAL)
        bad["samples"][0]["amount"] = 99
        try:
            store.apply(**bad)
        except ValueError as error:
            assert str(error) == "BATCH_CONFLICT"
        else:
            raise AssertionError("missing request conflict")
        assert store.snapshot() == before
        conflict = {"batch_id": "conflict", "samples": [
            dict(INITIAL["samples"][0], rev=2, amount=100),
            dict(INITIAL["samples"][1], amount=123)], "links": []}
        try:
            store.apply(**conflict)
        except ValueError as error:
            assert str(error) == "REVISION_CONFLICT"
        else:
            raise AssertionError("missing revision conflict")
        assert store.snapshot() == before
        assert store.apply(**CORRECTION) == {
            "batch_id": "correction-2", "generation": 2, "accepted": 1}
        assert store.apply("old", [INITIAL["samples"][1]], []) == {
            "batch_id": "old", "generation": 3, "accepted": 0}
        assert store.read("river", "2024-11-03T01:00:00.000000000",
                          "2024-11-03T01:25:00.000000000") == {"count": 2, "sum": 1}
        assert store.snapshot()["samples"][1]["rev"] == 2
        assert len(store.snapshot()["receipts"]) == 3
        clock = Clock(ERAS)
        assert clock.candidates("river", INITIAL["samples"][0]["local"]) == [
            t("2024-11-03T05:10:00"), t("2024-11-03T06:10:00")]
        assert clock.candidates("river", "2024-03-10T02:30:00.000000000") == []
        assert clock.candidates("river", "2024-11-03T01:59:59.999999999") == [
            t("2024-11-03T05:59:59") + 999999999,
            t("2024-11-03T06:59:59") + 999999999]
        assert clock.candidates("river", "2024-11-03T02:00:00.000000000") == [
            t("2024-11-03T07:00:00")]
        assert not hasattr(__import__("vendor.clock2", fromlist=["local_ns"]), "local_ns")
        print("NORMAL_REGRESSION_OK")
    finally:
        store.close()

def demo():
    store = Store()
    try:
        print(json.dumps({"old_receipt": seed(store)}, sort_keys=True))
        print(json.dumps({"local_query": store.read(
            "river", "2024-11-03T01:00:00.000000000", "2024-11-03T01:25:00.000000000")},
            sort_keys=True))
        clock = Clock(ERAS)
        print(json.dumps({"a_utc_candidates_ns": clock.candidates(
            "river", INITIAL["samples"][0]["local"])}, sort_keys=True))
        print(json.dumps({"correction_receipt": store.apply(**CORRECTION)}, sort_keys=True))
        print(json.dumps({"corrected_local_query": store.read(
            "river", "2024-11-03T01:00:00.000000000", "2024-11-03T01:25:00.000000000")},
            sort_keys=True))
    finally:
        store.close()

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) == 2 else "verify"
    if mode in ("normal", "verify"):
        normal()
    elif mode == "demo":
        demo()
    else:
        raise SystemExit("expected normal, verify or demo")

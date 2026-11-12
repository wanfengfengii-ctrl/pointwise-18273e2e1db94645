"""Complete old-database construction and captured compatibility requests."""
from vendor.clock1 import local_ns

MINUTE = 60 * 1000000000
def t(text):
    return local_ns(text + ".000000000")

ERAS = [
    ("river", t("2024-01-01T00:00:00"), t("2024-03-10T07:00:00"), -300 * MINUTE),
    ("river", t("2024-03-10T07:00:00"), t("2024-11-03T06:00:00"), -240 * MINUTE),
    ("river", t("2024-11-03T06:00:00"), t("2025-01-01T00:00:00"), -300 * MINUTE),
    ("utc", t("2024-01-01T00:00:00"), t("2025-01-01T00:00:00"), 0),
]
INITIAL = {
    "batch_id": "recording-1",
    "samples": [
        {"id": "a", "rev": 1, "station": "river", "local": "2024-11-03T01:10:00.000000000", "amount": 7, "deleted": False},
        {"id": "b", "rev": 1, "station": "river", "local": "2024-11-03T01:20:00.000000000", "amount": -4, "deleted": False},
        {"id": "c", "rev": 1, "station": "river", "local": "2024-11-03T01:30:00.000000000", "amount": 11, "deleted": False},
        {"id": "z", "rev": 1, "station": "utc", "local": "2024-11-03T05:00:00.000000000", "amount": 0, "deleted": True},
    ],
    "links": [
        {"id": "ab", "rev": 1, "a": "a", "b": "b", "lo": 10 * MINUTE, "hi": 10 * MINUTE, "deleted": False},
        {"id": "bc", "rev": 1, "a": "b", "b": "c", "lo": 10 * MINUTE, "hi": 10 * MINUTE, "deleted": False},
        {"id": "za", "rev": 1, "a": "z", "b": "a", "lo": 10 * MINUTE, "hi": 70 * MINUTE, "deleted": False},
    ],
}
CORRECTION = {
    "batch_id": "correction-2",
    "samples": [dict(INITIAL["samples"][1], rev=2, amount=-6)],
    "links": [],
}
PIN = {
    "batch_id": "anchor-3", "samples": [],
    "links": [dict(INITIAL["links"][2], rev=2, hi=10 * MINUTE)],
}
UNPIN = {
    "batch_id": "anchor-4", "samples": [],
    "links": [dict(INITIAL["links"][2], rev=3, deleted=True)],
}
IMPOSSIBLE = {
    "batch_id": "bad-clock", "samples": [],
    "links": [dict(INITIAL["links"][0], rev=2, lo=11 * MINUTE, hi=11 * MINUTE)],
}

def seed(store):
    if store.generation() != 0:
        raise ValueError("SEED_NONEMPTY")
    store.db.executemany("INSERT INTO eras VALUES(?,?,?,?)", ERAS)
    return store.apply(**INITIAL)

"""Frozen v1 wall-clock API: a naive local coordinate, never a UTC instant."""
import datetime
import re

_NS = 1000000000
_EPOCH = datetime.datetime(1970, 1, 1)
_PATTERN = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})\.([0-9]{9})\Z")

def local_ns(text):
    if not isinstance(text, str):
        raise ValueError("LOCAL_FORMAT")
    match = _PATTERN.fullmatch(text)
    if match is None:
        raise ValueError("LOCAL_FORMAT")
    try:
        value = datetime.datetime.strptime(match[1], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        raise ValueError("LOCAL_FORMAT") from None
    delta = value - _EPOCH
    result = (delta.days * 86400 + delta.seconds) * _NS + int(match[2])
    if not -(1 << 63) <= result < (1 << 63):
        raise ValueError("TIME_RANGE")
    return result

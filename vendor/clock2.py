"""Complete offline v2 API. UTC eras replace the v1 scalar conversion."""
import datetime
import re

class Clock:
    def __init__(self, eras):
        self._eras = {}
        for station, start, end, offset in eras:
            if not isinstance(station, str) or not station:
                raise ValueError("ERA_STATION")
            if any(type(v) is not int for v in (start, end, offset)) or start >= end:
                raise ValueError("ERA_RANGE")
            self._eras.setdefault(station, []).append((start, end, offset))
        for rows in self._eras.values():
            rows.sort()
            if any(a[1] > b[0] for a, b in zip(rows, rows[1:])):
                raise ValueError("ERA_OVERLAP")

    def candidates(self, station, local):
        # v2 deliberately has no local_ns function and never chooses a fold.
        if not isinstance(local, str):
            raise ValueError("LOCAL_FORMAT")
        match = re.fullmatch(r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})\.([0-9]{9})", local)
        if match is None:
            raise ValueError("LOCAL_FORMAT")
        try:
            value = datetime.datetime.strptime(match[1], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            raise ValueError("LOCAL_FORMAT") from None
        delta = value - datetime.datetime(1970, 1, 1)
        wall = (delta.days * 86400 + delta.seconds) * 1000000000 + int(match[2])
        if not -(1 << 63) <= wall < (1 << 63):
            raise ValueError("TIME_RANGE")
        if station not in self._eras:
            raise ValueError("UNKNOWN_STATION")
        return sorted({wall - offset for start, end, offset in self._eras[station]
                       if start <= wall - offset < end})

"""Entry/exit position state machine (SIG-002, technical architecture 7).

Enter when |z| >= entry_z; exit when |z| <= exit_z.
No position opened on a day data is missing.
Parameters: entry_z, exit_z from config.signal.
"""


def state_machine(z_series: list[float | None],
                  entry_z: float,
                  exit_z: float) -> list[int]:
    """Return position array: +1 long spread, -1 short spread, 0 flat.

    A position can flip direction only via flat (exit first).
    """
    pos = 0
    out = []
    for z in z_series:
        if z is None:
            out.append(pos)
            continue
        if pos == 0 and abs(z) >= entry_z:
            pos = 1 if z < 0 else -1
        elif pos != 0 and abs(z) <= exit_z:
            pos = 0
        out.append(pos)
    return out


def identify_trades(dates: list, positions: list[int]) -> list[dict]:
    """Group consecutive same-sign positions into trades. Returns trade dicts."""
    trades = []
    start = None
    sign = 0
    for i, p in enumerate(positions):
        if p != 0 and start is None:
            start = i
            sign = p
        elif p == 0 and start is not None:
            trades.append({"entry_i": start, "exit_i": i, "direction": sign})
            start = None
            sign = 0
        elif start is not None and p != sign:
            trades.append({"entry_i": start, "exit_i": i, "direction": sign})
            start = i if p != 0 else None
            sign = p
    if start is not None:
        trades.append({"entry_i": start, "exit_i": len(positions) - 1, "direction": sign,
                       "open": True})
    del dates
    return trades

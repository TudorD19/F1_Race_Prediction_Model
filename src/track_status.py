"""Find laps disturbed by flags, Safety Car or deleted lap times, using OpenF1 race_control.
 
Two public functions:
    neutralised_periods(race_control)      -> table of [start, end) time windows
    add_track_status_flags(laps, race_control) -> laps with two new boolean columns
"""
 
import re
 
import pandas as pd
 
 
def _track_reset(row):
    """True for a message that clears the whole track (back to racing)."""
    return row["category"] == "Flag" and row["scope"] == "Track" and row["flag"] in ("GREEN", "CLEAR", "CHEQUERED")
 
 
def neutralised_periods(race_control):
    """Return a DataFrame with one row per period where the track was not fully green.
 
    Columns: kind (YELLOW, RED, SC, VSC), start, end.
    Rules:
      - YELLOW / DOUBLE YELLOW in a (mini) sector lasts until CLEAR in that sector
        or until the whole track is cleared.
      - RED lasts until the track goes GREEN again.
      - SAFETY CAR DEPLOYED lasts until the track is cleared.
      - VSC DEPLOYED lasts until VSC ENDING.
      A period that never closes lasts until the last message of the session.
    """
    if len(race_control) == 0:
        return pd.DataFrame(columns=["kind", "start", "end"])
 
    rc = race_control.copy()
    rc["date"] = pd.to_datetime(rc["date"], format="ISO8601", utc=True)
    rc = rc.sort_values("date", kind="stable")  # keep API order for equal timestamps
    session_end = rc["date"].max()
 
    periods = []
    open_yellow = {}  # sector -> start time
    open_track = {}   # "RED" / "SC" / "VSC" -> start time
 
    def close(kind, start, end):
        periods.append({"kind": kind, "start": start, "end": end})
 
    for _, row in rc.iterrows():
        t, flag, msg = row["date"], row["flag"], str(row["message"])
 
        # 1) sector yellows
        if row["category"] == "Flag" and flag in ("YELLOW", "DOUBLE YELLOW"):
            open_yellow.setdefault(row["sector"], t)
        elif row["category"] == "Flag" and flag == "CLEAR" and row["scope"] == "Sector":
            if row["sector"] in open_yellow:
                close("YELLOW", open_yellow.pop(row["sector"]), t)
 
        # 2) red flag
        if row["category"] == "Flag" and flag == "RED":
            open_track.setdefault("RED", t)
 
        # 3) safety car and virtual safety car
        if row["category"] == "SafetyCar":
            if msg.startswith("VSC DEPLOYED"):
                open_track.setdefault("VSC", t)
            elif msg.startswith("VSC ENDING") and "VSC" in open_track:
                close("VSC", open_track.pop("VSC"), t)
            elif msg.startswith("SAFETY CAR DEPLOYED"):
                if "VSC" in open_track:  # a VSC can turn into a full Safety Car
                    close("VSC", open_track.pop("VSC"), t)
                open_track.setdefault("SC", t)
 
        # 4) whole track cleared: closes everything that is still open
        if _track_reset(row):
            for sector, start in open_yellow.items():
                close("YELLOW", start, t)
            open_yellow.clear()
            for kind in ("RED", "SC", "VSC"):
                if kind in open_track:
                    close(kind, open_track.pop(kind), t)
 
    # anything still open lasts until the end of the session
    for start in open_yellow.values():
        close("YELLOW", start, session_end)
    for kind, start in open_track.items():
        close(kind, start, session_end)
 
    return pd.DataFrame(periods)
 
 
_DELETED = re.compile(r"CAR (\d+) .*DELETED.*LAP (\d+)")
_REINSTATED = re.compile(r"CAR (\d+) .*LAP (\d+).*REINSTATED")
 
 
def deleted_laps(race_control):
    """Return a set of (driver_number, lap_number) whose time was deleted (e.g. track limits).
 
    Example message: "CAR 30 (LAW) TIME 1:34.481 DELETED - TRACK LIMITS AT TURN 1 LAP 6 16:07:36"
    Laps later reinstated by the stewards are removed from the set.
    """
    deleted, reinstated = set(), set()
    for msg in race_control.get("message", pd.Series(dtype=str)).astype(str):
        m = _DELETED.search(msg)
        if m:
            deleted.add((int(m.group(1)), int(m.group(2))))
        m = _REINSTATED.search(msg)
        if m:
            reinstated.add((int(m.group(1)), int(m.group(2))))
    return deleted - reinstated
 
 
def add_track_status_flags(laps, race_control):
    """Add two boolean columns to a lap table:
 
    - is_neutralised: the lap overlaps a yellow, red, SC or VSC period
    - is_deleted:     the lap time was deleted by race control
    """
    out = laps.copy()
    start = pd.to_datetime(out["date_start"], format="ISO8601", utc=True)
    end = start + pd.to_timedelta(out["lap_duration"].fillna(0), unit="s")
 
    out["is_neutralised"] = False
    for _, p in neutralised_periods(race_control).iterrows():
        overlaps = (start < p["end"]) & (end > p["start"])
        out["is_neutralised"] |= overlaps
 
    gone = deleted_laps(race_control)
    out["is_deleted"] = [
        (d, l) in gone for d, l in zip(out["driver_number"], out["lap_number"])
    ]
    return out
 
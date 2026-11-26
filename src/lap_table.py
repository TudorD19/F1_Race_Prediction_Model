from openf1_client import get
from track_status import add_track_status_flags

STINT_COLUMNS = ["driver_number", "stint_number", "lap_start", "lap_end","compound", "tyre_age_at_start"]

#Return the clean laps of one session, with compound and tyre age
def build_lap_table(session_key, max_ratio = 1.07):
    laps = get("laps", session_key = session_key)
    stints = get("stints", session_key = session_key)
    rc = get("race_control", session_key=session_key)

    if len(laps) == 0 or len(stints) == 0:
        return None

    merged = laps.merge(stints[STINT_COLUMNS], on="driver_number")
    laps_st = merged[(merged["lap_number"] >= merged["lap_start"]) & (merged["lap_number"] <= merged["lap_end"])].copy()

    laps_st["tyre_age"] = laps_st["tyre_age_at_start"] + (laps_st["lap_number"] - laps_st["lap_start"])
    laps_st["is_pit_in_lap"] = laps_st["lap_number"] == laps_st["lap_end"]

    laps_st = add_track_status_flags(laps_st,rc)

    not_out  = ~laps_st["is_pit_out_lap"]
    not_in   = ~laps_st["is_pit_in_lap"]
    has_time = laps_st["lap_duration"].notna()
    not_neutralised = ~laps_st["is_neutralised"]
    not_deleted = ~laps_st["is_deleted"]
    is_dry = laps_st["compound"].isin(["SOFT", "MEDIUM", "HARD"])

    keep = not_out & not_in & has_time &not_neutralised & not_deleted & is_dry
    clean = laps_st[keep].copy()

    clean["stint_best"] = clean.groupby(["driver_number", "stint_number"])["lap_duration"].transform("min")
    within107 = clean["lap_duration"] < (max_ratio * clean["stint_best"])
    clean = clean[within107].copy()

    clean["session_key"] = session_key
    return clean
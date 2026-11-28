import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression

from openf1_client import get
from lap_table import build_lap_table

MIN_LONG_RUN_LAPS = 5
MIN_DRIVERS_PER_SESSION = 8
MIN_RACE_LAPS = 10

#clean laps of every FP2 and race of the season in that year (notebook 04)
def load_laps(year):
    tables = []
    for session_name in ["Practice 2", "Race"]:
        sessions = get("sessions", year = year, session_name = session_name)
        for _, s in sessions.iterrows():
            t = build_lap_table(s["session_key"])
            if t is not None and len(t) > 0:
                t["session_name"] = session_name
                t["location"] = s["location"]
                t["date_start"] = s["date_start"]
                tables.append(t)
    return pd.concat(tables, ignore_index=True)


#how much does fuel and tyre age count 
def fit_race_correction(g):
    X = pd.get_dummies(g["driver_number"], prefix="driver", dtype=float)
    X["lap_number"] = g["lap_number"]
    X["tyre_age"] = g["tyre_age"]
    y = g["lap_duration"]

    model = LinearRegression().fit(X, y)
    coefs = dict(zip(X.columns, model.coef_))
    return {"fuel": coefs["lap_number"], "deg": coefs["tyre_age"]}


#calls function fit_race_correction for every race and returns the median values for the season
def season_correction(race_laps):
    results = pd.DataFrame([fit_race_correction(g) for _, g in race_laps.groupby("session_key")])
    return results["fuel"].median(), results["deg"].median()


#calculates the real fp2 pace for every driver
def fp2_pace(fp2_laps, fuel, deg):
    
    #One row per driver per weekend with the corrected FP2 long-run pace (notebooks 05 + 06)
    lr = fp2_laps.copy()
    stint = ["session_key", "driver_number", "stint_number"]

    # long runs: enough clean laps in the stint, enough drivers in the session
    lr["laps_in_stint"] = lr.groupby(stint)["lap_number"].transform("size")
    lr = lr[lr["laps_in_stint"] >= MIN_LONG_RUN_LAPS].copy()
    drivers = lr.groupby("session_key")["driver_number"].transform("nunique")
    lr = lr[drivers >= MIN_DRIVERS_PER_SESSION].copy()

    # fuel and tyre correction
    lr["laps_into_stint"] = lr["lap_number"] - lr.groupby(stint)["lap_number"].transform("min") #laps in the stint will start from 1
    lr["corrected"] = lr["lap_duration"] - fuel * lr["laps_into_stint"] - deg * lr["tyre_age"] #corrected lap time 

    pace = lr.groupby(["location", "driver_number"]).agg(
        fp2_pace=("corrected", "median"),
        n_laps=("corrected", "size"),
    ).reset_index()

    pace["location_best"] = pace.groupby("location")["fp2_pace"].transform("min")
    pace["fp2_gap_pct"] = (pace["fp2_pace"] / pace["location_best"] - 1) * 100  
    
    return pace


#what we want to predict - the target - the real race pace
def race_target(race_laps, fuel, deg):
    
    #One row per driver per race with the corrected race pace (notebook 07).
    race = race_laps.copy()
    race["corrected"] = race["lap_duration"] - fuel * race["lap_number"] - deg * race["tyre_age"] #fuel is measured from the start of the race

    target = race.groupby(["location", "driver_number"]).agg(
        race_pace=("corrected", "median"),
        race_laps=("corrected", "size"),
        date_start=("date_start", "first"),
    ).reset_index()

    target = target[target["race_laps"] >= MIN_RACE_LAPS].copy() 
    target["location_best"] = target.groupby("location")["race_pace"].transform("min")
    target["race_gap_pct"] = (target["race_pace"] / target["location_best"] - 1) * 100

    return target


#Qualifying position of every driver at every weekend
def quali_positions(year):

    rows = []
    for _, s in get("sessions", year=year, session_name="Qualifying").iterrows():
        res = get("session_result", session_key=s["session_key"])
        if len(res) > 0:
            res = res[["driver_number", "position"]].copy()
            res["location"] = s["location"]
            rows.append(res)
    return pd.concat(rows).rename(columns={"position": "quali_pos"})


#Building the dataset for one season - combining all the functions
def build_dataset(year):
    laps = load_laps(year)
    fp2_laps = laps[laps["session_name"] == "Practice 2"]
    race_laps = laps[laps["session_name"] == "Race"]

    fuel, deg = season_correction(laps)

    data = fp2_pace(fp2_laps, fuel, deg).merge(race_target(race_laps, fuel, deg), on = ["location", "driver_number"])
    data = data.merge(quali_positions(year), on = ["location", "driver_number"], how = "left") #how = "left" in order to prevent losing drivers who don't have a pace in quali

    data["quali_pos"] = pd.to_numeric(data["quali_pos"], errors = "coerce").fillna(20)#converts every value to a number and NaN where is None, then puts 20 (back of the grid)
    data["year"] = year
    data["fuel_effect"] = fuel
    data["deg_effect"] = deg

    return data

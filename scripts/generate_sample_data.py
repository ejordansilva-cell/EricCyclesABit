"""Generate synthetic Strava + TrainerRoad sample exports for local testing/demo."""
import random
from datetime import date, timedelta

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

START = date(2024, 1, 1)
END = date(2026, 7, 6)

ROUTE_NAMES = [
    "Morning Loop", "River Trail Ride", "Hill Repeats", "Coffee Shop Ride",
    "Gravel Grind", "Zwift Watopia", "Long Sunday Ride", "Commute", "Recovery Spin",
]


def _daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def gen_strava(path: str) -> None:
    rows = []
    activity_id = 1_000_000
    ftp_base = 210
    for d in _daterange(START, END):
        days_in = (d - START).days
        ftp_now = ftp_base + days_in * 0.03 + 15 * np.sin(days_in / 180)
        ride_prob = 0.5 + 0.2 * np.sin(days_in / 30)
        if random.random() > max(ride_prob, 0.15):
            continue

        is_long = random.random() < 0.15
        distance_mi = np.random.gamma(4, 6) if not is_long else np.random.uniform(60, 105)
        distance_m = distance_mi * 1609.344
        moving_time_s = distance_mi / random.uniform(13, 18) * 3600
        elev_ft = distance_mi * random.uniform(20, 90)
        avg_watts = max(90, np.random.normal(ftp_now * 0.68, 20))

        rows.append({
            "Activity ID": activity_id,
            "Activity Date": d.strftime("%b %d, %Y, %I:%M:%S %p"),
            "Activity Name": random.choice(ROUTE_NAMES),
            "Activity Type": "Virtual Ride" if random.random() < 0.2 else "Ride",
            "Elapsed Time": int(moving_time_s * 1.05),
            "Distance": round(distance_m, 1),
            "Elapsed Time.1": int(moving_time_s * 1.05),
            "Moving Time": int(moving_time_s),
            "Distance.1": round(distance_m, 1),
            "Elevation Gain": round(elev_ft * 0.3048, 1),
            "Average Watts": round(avg_watts, 1),
            "Max Watts": round(avg_watts * random.uniform(2.5, 4), 1),
            "Weighted Average Power": round(avg_watts * 1.08, 1),
            "Average Heart Rate": round(np.random.normal(140, 12), 1),
            "Max Heart Rate": round(np.random.normal(172, 8), 1),
            "Average Cadence": round(np.random.normal(85, 6), 1),
            "Calories": round(distance_mi * 35, 1),
            "Relative Effort": round(np.random.uniform(20, 180), 1),
        })
        activity_id += 1

    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"Wrote {len(rows)} Strava rides to {path}")


def gen_trainerroad(path: str) -> None:
    rows = []
    ftp_base = 210
    workout_names = ["Baxter", "Petit", "Mary Austin", "Warlow", "Carter", "Antelope"]
    for d in _daterange(START, END):
        if random.random() > 0.3:
            continue
        days_in = (d - START).days
        ftp_now = round(ftp_base + days_in * 0.03 + 15 * np.sin(days_in / 180))
        duration_min = np.random.uniform(30, 90)
        intensity_factor = np.random.uniform(0.65, 0.95)
        avg_power = ftp_now * intensity_factor
        tss = (duration_min / 60) * (intensity_factor ** 2) * 100

        rows.append({
            "Date": d.strftime("%Y-%m-%d"),
            "WorkoutName": random.choice(workout_names),
            "WorkoutType": random.choice(["Sweet Spot", "Threshold", "VO2", "Endurance"]),
            "DurationMinutes": round(duration_min, 1),
            "TSS": round(tss, 1),
            "IF": round(intensity_factor, 2),
            "AveragePower": round(avg_power, 1),
            "NormalizedPower": round(avg_power * 1.05, 1),
            "AverageHeartRate": round(np.random.normal(145, 10), 1),
            "AverageCadence": round(np.random.normal(88, 5), 1),
            "FTP": ftp_now,
        })

    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"Wrote {len(rows)} TrainerRoad workouts to {path}")


if __name__ == "__main__":
    gen_strava("sample_data/strava_activities_sample.csv")
    gen_trainerroad("sample_data/trainerroad_sample.csv")

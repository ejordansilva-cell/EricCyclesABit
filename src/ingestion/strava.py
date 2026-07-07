"""Parse a Strava bulk-export activities.csv into a normalized rides DataFrame."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

METERS_PER_MILE = 1609.344
METERS_PER_FOOT = 0.3048

CYCLING_TYPES = {
    "Ride",
    "Virtual Ride",
    "E-Bike Ride",
    "Gravel Ride",
    "Mountain Bike Ride",
    "Handcycle",
    "Velomobile",
}

# Strava's export column names have shifted over the years and include
# duplicate-suffixed columns (e.g. "Distance.1"). Map several known aliases
# to our normalized schema, in priority order.
COLUMN_ALIASES = {
    "activity_id": ["Activity ID"],
    "date": ["Activity Date"],
    "name": ["Activity Name"],
    "sport_type": ["Activity Type"],
    "filename": ["Filename"],
    "elapsed_time_s": ["Elapsed Time.1", "Elapsed Time"],
    "moving_time_s": ["Moving Time"],
    "distance_m": ["Distance.1", "Distance"],
    "elevation_gain_m": ["Elevation Gain"],
    "avg_watts": ["Average Watts"],
    "max_watts": ["Max Watts"],
    "weighted_avg_watts": ["Weighted Average Power"],
    "avg_hr": ["Average Heart Rate"],
    "max_hr": ["Max Heart Rate"],
    "avg_cadence": ["Average Cadence"],
    "calories": ["Calories"],
    "relative_effort": ["Relative Effort.1", "Relative Effort"],
}


def _pick_column(df: pd.DataFrame, aliases: list[str]) -> pd.Series | None:
    for alias in aliases:
        if alias in df.columns:
            return df[alias]
    return None


def _read_activities_csv_from_zip(zf: zipfile.ZipFile) -> pd.DataFrame:
    csv_name = next((n for n in zf.namelist() if n.lower().endswith("activities.csv")), None)
    if csv_name is None:
        raise ValueError("Couldn't find activities.csv inside that zip.")
    with zf.open(csv_name) as f:
        return pd.read_csv(f, low_memory=False)


def load_strava_export(uploaded_file) -> pd.DataFrame:
    """Accepts a Strava bulk-export .zip or a bare activities.csv file-like object.

    Reads only the activities.csv member out of the zip (never buffers the
    whole archive in memory), so this is safe to use even on multi-GB exports.
    """
    name = getattr(uploaded_file, "name", "") or ""
    if name.lower().endswith(".zip"):
        with zipfile.ZipFile(uploaded_file) as zf:
            df = _read_activities_csv_from_zip(zf)
    else:
        df = pd.read_csv(uploaded_file, low_memory=False)

    return _normalize(df)


def load_strava_export_from_path(path: str | Path) -> pd.DataFrame:
    """Like load_strava_export, but reads straight from a local zip/csv path on
    disk instead of an in-memory upload — use this for large exports so the
    file never has to pass through the browser upload widget."""
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"No such file: {path}")

    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            df = _read_activities_csv_from_zip(zf)
    else:
        df = pd.read_csv(path, low_memory=False)

    return _normalize(df)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    normalized = pd.DataFrame()
    for field, aliases in COLUMN_ALIASES.items():
        col = _pick_column(df, aliases)
        normalized[field] = col if col is not None else pd.NA

    normalized["date"] = pd.to_datetime(normalized["date"], format="mixed", errors="coerce")
    normalized = normalized.dropna(subset=["date"])

    normalized["sport_type"] = normalized["sport_type"].fillna("")
    normalized = normalized[normalized["sport_type"].isin(CYCLING_TYPES)].copy()

    numeric_fields = [
        "elapsed_time_s", "moving_time_s", "distance_m", "elevation_gain_m",
        "avg_watts", "max_watts", "weighted_avg_watts", "avg_hr", "max_hr",
        "avg_cadence", "calories", "relative_effort",
    ]
    for field in numeric_fields:
        normalized[field] = pd.to_numeric(normalized[field], errors="coerce")

    normalized["distance_mi"] = normalized["distance_m"] / METERS_PER_MILE
    normalized["elevation_gain_ft"] = normalized["elevation_gain_m"] / METERS_PER_FOOT
    normalized["moving_time_min"] = normalized["moving_time_s"] / 60
    normalized["elapsed_time_min"] = normalized["elapsed_time_s"] / 60
    normalized["source"] = "strava"

    return normalized.sort_values("date").reset_index(drop=True)

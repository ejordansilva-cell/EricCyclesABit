"""Parse a TrainerRoad workout-history CSV export into a normalized DataFrame.

TrainerRoad's export columns have varied across their site's history, so
instead of hard-coding exact names we fuzzy-match on keywords.
"""
from __future__ import annotations

import io

import pandas as pd

# field -> keywords to look for in a lowercased, underscore-stripped column name.
# Order matters: first keyword set that matches wins.
FIELD_KEYWORDS = {
    "date": ["date"],
    "workout_name": ["workoutname", "workout", "name"],
    "workout_type": ["workouttype", "type"],
    "duration_min": ["durationminutes", "duration", "minutes", "time"],
    "tss": ["tss"],
    "intensity_factor": ["intensityfactor", "if"],
    "avg_power": ["averagepower", "avgpower", "avg_watts"],
    "normalized_power": ["normalizedpower", "np"],
    "avg_hr": ["averageheartrate", "avghr", "heartrate"],
    "avg_cadence": ["averagecadence", "cadence"],
    "ftp": ["ftp"],
}


def _slug(col: str) -> str:
    return "".join(ch for ch in col.lower() if ch.isalnum())


def _match_column(columns: list[str], keywords: list[str]) -> str | None:
    slugs = {col: _slug(col) for col in columns}
    for keyword in keywords:
        for col, slug in slugs.items():
            if keyword in slug:
                return col
    return None


def load_trainerroad_export(uploaded_file) -> pd.DataFrame:
    raw = uploaded_file.read()
    df = pd.read_csv(io.BytesIO(raw), low_memory=False)
    columns = list(df.columns)

    normalized = pd.DataFrame()
    for field, keywords in FIELD_KEYWORDS.items():
        col = _match_column(columns, keywords)
        normalized[field] = df[col] if col is not None else pd.NA

    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    normalized = normalized.dropna(subset=["date"])

    numeric_fields = [
        "duration_min", "tss", "intensity_factor", "avg_power",
        "normalized_power", "avg_hr", "avg_cadence", "ftp",
    ]
    for field in numeric_fields:
        normalized[field] = pd.to_numeric(normalized[field], errors="coerce")

    normalized["source"] = "trainerroad"
    return normalized.sort_values("date").reset_index(drop=True)


def ftp_history(tr_rides: pd.DataFrame) -> pd.DataFrame:
    """Return distinct (date, ftp) points where FTP is recorded, forward-deduped."""
    if tr_rides.empty or "ftp" not in tr_rides.columns:
        return pd.DataFrame(columns=["date", "ftp"])

    known = tr_rides.dropna(subset=["ftp"])[["date", "ftp"]].sort_values("date")
    if known.empty:
        return known

    changes = known[known["ftp"] != known["ftp"].shift(1)]
    return changes.reset_index(drop=True)

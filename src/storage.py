"""Local persistence for parsed ride data and goal settings."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STRAVA_PATH = DATA_DIR / "strava_rides.parquet"
TRAINERROAD_PATH = DATA_DIR / "trainerroad_rides.parquet"
GOALS_PATH = DATA_DIR / "goals.json"


def save_rides(df: pd.DataFrame, path: Path) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def load_rides(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_parquet(path)


def save_goals(goals: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GOALS_PATH.write_text(json.dumps(goals, indent=2))


def load_goals() -> dict | None:
    if not GOALS_PATH.exists():
        return None
    return json.loads(GOALS_PATH.read_text())

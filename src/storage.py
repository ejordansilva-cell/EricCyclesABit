"""Local persistence for parsed ride data and goal settings."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STRAVA_PATH = DATA_DIR / "strava_rides.pkl"
TRAINERROAD_PATH = DATA_DIR / "trainerroad_rides.pkl"
GOALS_PATH = DATA_DIR / "goals.json"
STRAVA_ZIP_PATH_FILE = DATA_DIR / "strava_zip_path.txt"
WORKOUT_CACHE_PATH = DATA_DIR / "workout_cache.json"


def save_rides(df: pd.DataFrame, path: Path) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_pickle(path)


def load_rides(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_pickle(path)


def save_goals(goals: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GOALS_PATH.write_text(json.dumps(goals, indent=2))


def load_goals() -> dict | None:
    if not GOALS_PATH.exists():
        return None
    return json.loads(GOALS_PATH.read_text())


def save_strava_zip_path(path: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STRAVA_ZIP_PATH_FILE.write_text(path)


def load_strava_zip_path() -> str | None:
    if not STRAVA_ZIP_PATH_FILE.exists():
        return None
    path = STRAVA_ZIP_PATH_FILE.read_text().strip()
    return path or None


def save_workout_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WORKOUT_CACHE_PATH.write_text(json.dumps(cache, indent=2))


def load_workout_cache() -> dict:
    if not WORKOUT_CACHE_PATH.exists():
        return {}
    return json.loads(WORKOUT_CACHE_PATH.read_text())

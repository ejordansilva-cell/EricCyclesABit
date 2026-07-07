"""Goal definitions and progress calculations for the four tracked goal types."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from src import metrics
from src.ingestion import trainerroad as tr_ingest


def default_goals() -> dict:
    year = dt.date.today().year
    return {
        "ftp": {
            "enabled": True,
            "target_watts": 250,
            "target_date": f"{year}-12-31",
            "current_watts": None,
        },
        "distance": {
            "enabled": True,
            "target_miles": 3000,
            "year": year,
        },
        "elevation": {
            "enabled": True,
            "target_ft": 150000,
            "year": year,
        },
        "consistency": {
            "enabled": True,
            "target_rides_per_week": 4,
        },
    }


def ftp_progress(tr_rides: pd.DataFrame, goal: dict) -> dict:
    history = tr_ingest.ftp_history(tr_rides) if tr_rides is not None and not tr_rides.empty else pd.DataFrame()
    current = goal.get("current_watts")
    if current is None and not history.empty:
        current = float(history["ftp"].iloc[-1])
    target = goal.get("target_watts")
    pct = min(current / target, 1.0) if current and target else None
    return {
        "current": current,
        "target": target,
        "target_date": goal.get("target_date"),
        "pct": pct,
        "history": history,
    }


def distance_progress(strava_rides: pd.DataFrame, goal: dict) -> dict:
    year = goal.get("year", dt.date.today().year)
    target = goal.get("target_miles")
    cumulative = metrics.cumulative_by_year(strava_rides, "distance_mi", year)
    current = float(cumulative["cumulative"].iloc[-1]) if not cumulative.empty else 0.0
    projected = metrics.project_annual_total(cumulative, year) if not cumulative.empty else 0.0
    pct = min(current / target, 1.0) if target else None
    return {
        "current": current,
        "target": target,
        "projected": projected,
        "pct": pct,
        "cumulative": cumulative,
        "year": year,
    }


def elevation_progress(strava_rides: pd.DataFrame, goal: dict) -> dict:
    year = goal.get("year", dt.date.today().year)
    target = goal.get("target_ft")
    cumulative = metrics.cumulative_by_year(strava_rides, "elevation_gain_ft", year)
    current = float(cumulative["cumulative"].iloc[-1]) if not cumulative.empty else 0.0
    projected = metrics.project_annual_total(cumulative, year) if not cumulative.empty else 0.0
    pct = min(current / target, 1.0) if target else None
    return {
        "current": current,
        "target": target,
        "projected": projected,
        "pct": pct,
        "cumulative": cumulative,
        "year": year,
    }


def consistency_progress(strava_rides: pd.DataFrame, goal: dict) -> dict:
    weekly = metrics.weekly_summary(strava_rides)
    target = goal.get("target_rides_per_week")
    recent = metrics.recent_weekly_average(weekly, num_weeks=4)
    pct = min(recent["rides"] / target, 1.0) if target else None
    return {
        "current_avg_rides_per_week": recent["rides"],
        "current_avg_hours_per_week": recent["hours"],
        "target": target,
        "pct": pct,
        "weekly": weekly,
    }

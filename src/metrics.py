"""Aggregations over normalized ride data: weekly/monthly rollups, streaks, cumulative totals."""
from __future__ import annotations

import datetime as dt

import pandas as pd


def weekly_summary(rides: pd.DataFrame) -> pd.DataFrame:
    if rides.empty:
        return pd.DataFrame(columns=["week_start", "rides", "distance_mi", "elevation_gain_ft", "hours"])

    df = rides.copy()
    df["week_start"] = df["date"].dt.to_period("W-MON").apply(lambda p: p.start_time)
    grouped = df.groupby("week_start").agg(
        rides=("date", "count"),
        distance_mi=("distance_mi", "sum"),
        elevation_gain_ft=("elevation_gain_ft", "sum"),
        hours=("moving_time_min", lambda s: s.sum() / 60),
    ).reset_index()
    return grouped.sort_values("week_start")


def monthly_summary(rides: pd.DataFrame) -> pd.DataFrame:
    if rides.empty:
        return pd.DataFrame(columns=["month", "rides", "distance_mi", "elevation_gain_ft", "hours"])

    df = rides.copy()
    df["month"] = df["date"].dt.to_period("M").apply(lambda p: p.start_time)
    grouped = df.groupby("month").agg(
        rides=("date", "count"),
        distance_mi=("distance_mi", "sum"),
        elevation_gain_ft=("elevation_gain_ft", "sum"),
        hours=("moving_time_min", lambda s: s.sum() / 60),
    ).reset_index()
    return grouped.sort_values("month")


def cumulative_by_year(rides: pd.DataFrame, value_col: str, year: int) -> pd.DataFrame:
    if rides.empty:
        return pd.DataFrame(columns=["date", "cumulative"])

    df = rides[rides["date"].dt.year == year].sort_values("date").copy()
    if df.empty:
        return pd.DataFrame(columns=["date", "cumulative"])

    df["cumulative"] = df[value_col].fillna(0).cumsum()
    return df[["date", "cumulative"]]


def ytd_totals(rides: pd.DataFrame, year: int) -> dict:
    df = rides[rides["date"].dt.year == year]
    return {
        "rides": int(len(df)),
        "distance_mi": float(df["distance_mi"].sum()) if not df.empty else 0.0,
        "elevation_gain_ft": float(df["elevation_gain_ft"].sum()) if not df.empty else 0.0,
        "hours": float(df["moving_time_min"].sum() / 60) if not df.empty else 0.0,
    }


def longest_ride(rides: pd.DataFrame) -> pd.Series | None:
    if rides.empty or rides["distance_mi"].isna().all():
        return None
    return rides.loc[rides["distance_mi"].idxmax()]


def project_annual_total(cumulative_df: pd.DataFrame, year: int, today: dt.date | None = None) -> float:
    """Straight-line projection of a year-end total from year-to-date pace."""
    if cumulative_df.empty:
        return 0.0

    today = today or dt.date.today()
    year_start = dt.date(year, 1, 1)
    days_elapsed = max((today - year_start).days + 1, 1)
    days_in_year = 366 if _is_leap(year) else 365
    current_total = cumulative_df["cumulative"].iloc[-1]
    return current_total / days_elapsed * days_in_year


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


DEFAULT_IF_NO_POWER = 0.65  # assumed intensity factor for rides with no power data


def estimate_tss(rides: pd.DataFrame, ftp: float | None) -> pd.DataFrame:
    """Adds a 'tss' column estimated from power data (or a flat assumed
    intensity for rides with no power meter). Requires a current FTP —
    returns all-NaN 'tss' if none is set."""
    df = rides.copy()
    if not ftp:
        df["tss"] = pd.NA
        return df

    hours = df["moving_time_min"] / 60
    intensity_power = df["weighted_avg_watts"].fillna(df["avg_watts"])
    intensity_factor = intensity_power / ftp

    df["tss"] = hours * intensity_factor ** 2 * 100
    missing_power = intensity_power.isna()
    df.loc[missing_power, "tss"] = hours[missing_power] * (DEFAULT_IF_NO_POWER ** 2) * 100
    return df


def weekly_tss(rides_with_tss: pd.DataFrame) -> pd.DataFrame:
    if rides_with_tss.empty or "tss" not in rides_with_tss.columns:
        return pd.DataFrame(columns=["week_start", "tss"])

    df = rides_with_tss.copy()
    df["week_start"] = df["date"].dt.to_period("W-MON").apply(lambda p: p.start_time)
    grouped = df.groupby("week_start")["tss"].sum().reset_index()
    return grouped.sort_values("week_start").reset_index(drop=True)


def recent_weekly_average(weekly: pd.DataFrame, num_weeks: int = 4) -> dict:
    if weekly.empty:
        return {"rides": 0.0, "hours": 0.0}
    recent = weekly.tail(num_weeks)
    return {
        "rides": float(recent["rides"].mean()),
        "hours": float(recent["hours"].mean()),
    }

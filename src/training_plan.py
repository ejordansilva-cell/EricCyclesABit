"""Heuristic 2-week training recommendation: rolling training-load trend,
a burnout-avoidance check against past load spikes, and a day-by-day
schedule aimed at your FTP goal's pace.

This is not a physiological model — TSS is estimated from ride-summary
power (no proper power-duration curve), and "on pace for your goal" is a
qualitative read of your recent load trend, not a guarantee. Treat the
output as a reasonable starting point to adjust, not a prescription.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

ROLLING_WEEKS = 6
DEFAULT_RAMP_RATE = 1.08
CAUTIOUS_RAMP_RATE = 1.05
DELOAD_FACTOR = 0.7
WARMUP_COOLDOWN_MIN = 15
MIN_REPS = 3
MIN_DURATION_MIN = 20

# Interval sessions: work/rest per rep, an assumed base rep count (used only
# as a starting point before scaling to the day's TSS budget), and a blended
# whole-session intensity factor.
INTERVAL_LIBRARY = [
    {"kind": "VO2/anaerobic", "work_s": 30, "rest_s": 30, "if": 0.80, "max_reps": 20},
    {"kind": "VO2", "work_s": 300, "rest_s": 180, "if": 0.82, "max_reps": 8},
    {"kind": "Threshold", "work_s": 480, "rest_s": 240, "if": 0.85, "max_reps": 6},
    {"kind": "Sweet Spot", "work_s": 900, "rest_s": 300, "if": 0.83, "max_reps": 4},
]
EASY_IF = 0.65
LONG_IF = 0.65

# Fraction of the week's target TSS assigned to each role, keyed by
# (has_long_day, n_hard_days, has_easy_day) -> (long, hard_each, easy)
ROLE_FRACTIONS = {
    (True, 2, True): (0.35, 0.25, 0.15),
    (True, 1, True): (0.40, 0.35, 0.25),
    (True, 1, False): (0.55, 0.45, 0.0),
    (True, 0, False): (1.0, 0.0, 0.0),
}


def _format_work_duration(work_s: int) -> str:
    if work_s < 60:
        return f"0:{work_s:02d}"
    minutes, seconds = divmod(work_s, 60)
    return f"{minutes}:{seconds:02d}"


def _scale_interval(entry: dict, target_tss: float) -> dict:
    duration_hours = target_tss / (entry["if"] ** 2 * 100) if target_tss > 0 else 0
    duration_s = duration_hours * 3600
    cycle_s = entry["work_s"] + entry["rest_s"]
    reps = max(MIN_REPS, round((duration_s - WARMUP_COOLDOWN_MIN * 60) / cycle_s)) if cycle_s else MIN_REPS
    reps = min(reps, entry.get("max_reps", reps))
    actual_duration_min = round((WARMUP_COOLDOWN_MIN * 60 + reps * cycle_s) / 60)
    actual_tss = round((actual_duration_min / 60) * entry["if"] ** 2 * 100)
    label = f"{reps} x {_format_work_duration(entry['work_s'])}"
    return {"label": label, "kind": entry["kind"], "duration_min": actual_duration_min, "est_tss": actual_tss}


def _scale_steady(label: str, kind: str, if_: float, target_tss: float) -> dict:
    duration_hours = target_tss / (if_ ** 2 * 100) if target_tss > 0 else 0
    duration_min = max(MIN_DURATION_MIN, round(duration_hours * 60))
    est_tss = round((duration_min / 60) * if_ ** 2 * 100)
    return {"label": label, "kind": kind, "duration_min": duration_min, "est_tss": est_tss}


def detect_overreach_events(weekly_tss: pd.DataFrame, spike_ratio: float = 1.3, crash_ratio: float = 0.6) -> list[dict]:
    """Flags weeks that ramped up hard and were immediately followed by a big
    drop-off — a rough proxy for a burnout/fatigue crash, not a diagnosis."""
    events = []
    tss = weekly_tss["tss"].to_numpy()
    weeks = weekly_tss["week_start"].to_numpy()
    for i in range(1, len(tss) - 1):
        if tss[i - 1] <= 0:
            continue
        ramped = tss[i] / tss[i - 1] >= spike_ratio
        crashed = tss[i] > 0 and tss[i + 1] / tss[i] <= crash_ratio
        if ramped and crashed:
            events.append({"week_start": weeks[i], "tss": float(tss[i]), "next_week_tss": float(tss[i + 1])})
    return events


def recommend_ramp_rate(overreach_events: list[dict]) -> float:
    return CAUTIOUS_RAMP_RATE if overreach_events else DEFAULT_RAMP_RATE


def assess_ftp_pace(weekly_tss: pd.DataFrame, ftp_goal: dict, today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    current = ftp_goal.get("current_watts")
    target = ftp_goal.get("target_watts")
    target_date = dt.date.fromisoformat(ftp_goal["target_date"]) if ftp_goal.get("target_date") else None

    weeks_remaining = max((target_date - today).days / 7, 0) if target_date else None
    gap_watts = (target - current) if (current and target) else None

    recent = weekly_tss.tail(ROLLING_WEEKS)
    slope = None
    if len(recent) >= 3:
        x = np.arange(len(recent))
        slope = float(np.polyfit(x, recent["tss"].to_numpy(), 1)[0])

    if gap_watts is not None and gap_watts <= 0:
        message = f"You're already at or above your {target:.0f}W target."
    elif weeks_remaining == 0:
        message = "Your FTP target date has arrived — this plan reflects maintaining current load."
    elif slope is None:
        message = "Not enough ride history yet to judge your training trend."
    elif slope > 5:
        message = (
            f"Training load has been trending up over the last {len(recent)} weeks — "
            f"consistent with working toward your {target:.0f}W target in ~{weeks_remaining:.0f} weeks."
        )
    elif slope < -5:
        message = (
            f"Training load has been declining over the last {len(recent)} weeks, which will make it "
            f"harder to hit {target:.0f}W by your target date without rebuilding volume."
        )
    else:
        message = (
            f"Training load has been roughly flat — fine for maintaining fitness, but reaching "
            f"{target:.0f}W in ~{weeks_remaining:.0f} weeks likely needs a gradual increase."
        )

    return {
        "current_watts": current,
        "target_watts": target,
        "gap_watts": gap_watts,
        "weeks_remaining": weeks_remaining,
        "slope_tss_per_week": slope,
        "message": message,
    }


def _pick_ride_days(rides: pd.DataFrame, n_days: int) -> list[str]:
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    if rides.empty:
        default = ["Tuesday", "Thursday", "Saturday", "Sunday", "Wednesday", "Monday", "Friday"]
        return default[:n_days]

    counts = rides["date"].dt.day_name().value_counts()
    counts = counts.reindex(order, fill_value=0)
    top_days = counts.sort_values(ascending=False).index.tolist()
    return top_days[:n_days]


def _pick_long_day(rides: pd.DataFrame, ride_days: list[str]) -> str:
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    if not rides.empty:
        avg_distance = rides.groupby(rides["date"].dt.day_name())["distance_mi"].mean()
        candidates = avg_distance.reindex(ride_days).dropna()
        if not candidates.empty:
            return candidates.idxmax()
    for preferred in ["Saturday", "Sunday"]:
        if preferred in ride_days:
            return preferred
    return sorted(ride_days, key=order.index)[-1]


def _build_week(ride_days: list[str], long_day: str, week_index: int, target_tss: float, today: dt.date, day_offset_start: int) -> dict:
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    hard_days = sorted([d for d in ride_days if d != long_day], key=order.index)
    n_hard = 2 if len(ride_days) >= 4 else 1 if len(ride_days) >= 2 else 0
    hard_days = hard_days[:n_hard]
    easy_days = [d for d in ride_days if d != long_day and d not in hard_days]

    fraction_key = (True, n_hard, bool(easy_days))
    long_frac, hard_frac, easy_frac = ROLE_FRACTIONS.get(fraction_key, (0.5, 0.25, 0.25))

    assignments: dict[str, dict] = {
        long_day: _scale_steady("Long endurance ride", "Endurance", LONG_IF, target_tss * long_frac),
    }
    for i, day in enumerate(hard_days):
        lib_entry = INTERVAL_LIBRARY[(week_index + i) % len(INTERVAL_LIBRARY)]
        assignments[day] = _scale_interval(lib_entry, target_tss * hard_frac)
    for day in easy_days:
        share = easy_frac / len(easy_days) if easy_days else 0
        assignments[day] = _scale_steady("Endurance spin", "Endurance", EASY_IF, target_tss * share)

    days = []
    for day_offset in range(7):
        date = today + dt.timedelta(days=day_offset_start + day_offset)
        weekday = date.strftime("%A")
        entry = assignments.get(weekday)
        if entry is None:
            days.append({"date": date, "weekday": weekday, "label": "Rest", "duration_min": 0, "est_tss": 0})
        else:
            days.append({"date": date, "weekday": weekday, **entry})
    return {"days": days, "planned_total_tss": round(sum(d["est_tss"] for d in days))}


def build_two_week_plan(
    rides: pd.DataFrame,
    ftp_goal: dict,
    ride_days_per_week: int,
    weekly_tss: pd.DataFrame,
    today: dt.date | None = None,
) -> dict:
    today = today or dt.date.today()
    ride_days_per_week = max(2, min(7, round(ride_days_per_week)))

    recent = weekly_tss.tail(ROLLING_WEEKS)
    baseline = float(recent["tss"].mean()) if not recent.empty else 200.0

    overreach_events = detect_overreach_events(weekly_tss)
    ramp_rate = recommend_ramp_rate(overreach_events)

    last_three = weekly_tss.tail(3)["tss"].to_numpy()
    building_streak = len(last_three) == 3 and bool(np.all(np.diff(last_three) > 0))

    if building_streak:
        week1_target = baseline * DELOAD_FACTOR
        week2_target = week1_target * ramp_rate
        week1_kind, week2_kind = "deload", "build"
    else:
        week1_target = baseline * ramp_rate
        if week1_target > baseline * 1.15:
            week2_target = week1_target * DELOAD_FACTOR
            week2_kind = "deload"
        else:
            week2_target = week1_target * ramp_rate
            week2_kind = "build"
        week1_kind = "build"

    ride_days = _pick_ride_days(rides, ride_days_per_week)
    long_day = _pick_long_day(rides, ride_days)

    weeks = []
    for week_num, target_tss in enumerate([week1_target, week2_target]):
        week = _build_week(ride_days, long_day, week_num, target_tss, today, week_num * 7)
        weeks.append({
            "week_num": week_num + 1,
            "target_tss": round(target_tss),
            "kind": week1_kind if week_num == 0 else week2_kind,
            **week,
        })

    return {
        "baseline_tss": round(baseline),
        "ramp_rate": ramp_rate,
        "overreach_events": overreach_events,
        "weeks": weeks,
    }

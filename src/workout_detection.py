"""Best-effort detection of interval structure (e.g. "6 x 3:00 @ 245W") from a
raw power-vs-time stream. This is a heuristic, not an exact reconstruction of
whatever workout was actually prescribed — treat labels as approximate.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_SEGMENT_S = 6
_NICE_DURATIONS_S = [10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 300, 360, 480, 600, 720, 900, 1200]


def _nice_duration_label(seconds: float) -> str:
    nearest = min(_NICE_DURATIONS_S, key=lambda d: abs(d - seconds))
    if nearest < 60:
        return f"0:{nearest:02d}"
    minutes, secs = divmod(nearest, 60)
    return f"{minutes}:{secs:02d}"


def _resample_to_seconds(power_df: pd.DataFrame) -> pd.Series:
    df = power_df.copy()
    df["elapsed_s"] = df["elapsed_s"].round().astype(int)
    df = df.groupby("elapsed_s")["watts"].mean()
    full_index = np.arange(0, int(df.index.max()) + 1)
    return df.reindex(full_index).interpolate(limit=15).ffill().bfill()


def _segments_from_classification(watts: pd.Series, is_work: pd.Series) -> list[dict]:
    segments = []
    start = 0
    current = is_work.iloc[0]
    for i in range(1, len(is_work) + 1):
        if i == len(is_work) or is_work.iloc[i] != current:
            end = i
            duration = end - start
            if duration >= MIN_SEGMENT_S or not segments:
                segments.append({
                    "start_s": start,
                    "end_s": end,
                    "duration_s": duration,
                    "avg_watts": float(watts.iloc[start:end].mean()),
                    "kind": "work" if current else "rest",
                })
            elif segments:
                # merge tiny blip into previous segment
                prev = segments[-1]
                prev["end_s"] = end
                prev["duration_s"] = end - prev["start_s"]
                prev["avg_watts"] = float(watts.iloc[prev["start_s"]:end].mean())
            if i < len(is_work):
                start = i
                current = is_work.iloc[i]
    return segments


def _find_repeats(segments: list[dict], duration_tol: float = 0.25, power_tol: float = 0.15) -> dict | None:
    work_positions = [idx for idx, s in enumerate(segments) if s["kind"] == "work"]
    if len(work_positions) < 3:
        return None

    best = None
    i = 0
    while i < len(work_positions):
        j = i + 1
        ref = segments[work_positions[i]]
        while (
            j < len(work_positions)
            and abs(segments[work_positions[j]]["duration_s"] - ref["duration_s"]) <= duration_tol * ref["duration_s"]
            and abs(segments[work_positions[j]]["avg_watts"] - ref["avg_watts"]) <= power_tol * ref["avg_watts"]
        ):
            j += 1
        count = j - i
        if count >= 3 and (best is None or count > best["count"]):
            group_positions = work_positions[i:j]
            group = [segments[p] for p in group_positions]

            recovery_durations = []
            for a, b in zip(group_positions, group_positions[1:]):
                between = segments[a + 1:b]
                if len(between) == 1 and between[0]["kind"] == "rest":
                    recovery_durations.append(between[0]["duration_s"])

            best = {
                "count": count,
                "avg_duration_s": float(np.mean([g["duration_s"] for g in group])),
                "avg_watts": float(np.mean([g["avg_watts"] for g in group])),
                "avg_recovery_s": float(np.mean(recovery_durations)) if recovery_durations else None,
            }
        i = j
    return best


def detect_intervals(power_df: pd.DataFrame, ftp: float | None = None) -> dict:
    if power_df is None or power_df.empty:
        return {"label": "No power data", "segments": [], "repeats": None}

    watts = _resample_to_seconds(power_df)
    smoothed = watts.rolling(5, center=True, min_periods=1).median()

    low, high, median = smoothed.quantile([0.25, 0.75, 0.5])
    spread_ratio = (high - low) / median if median else 0

    if spread_ratio < 0.20:
        # Not enough separation between "hard" and "easy" seconds to call
        # this an interval workout — it's just one steady effort.
        avg = float(smoothed.mean())
        watt_label = f"{avg:.0f}W" + (f" ({avg / ftp * 100:.0f}% FTP)" if ftp else "")
        return {"label": f"Steady effort @ {watt_label}", "segments": [], "repeats": None}

    threshold = (low + high) / 2
    is_work = smoothed > threshold
    segments = _segments_from_classification(smoothed, is_work)
    work_segments = [s for s in segments if s["kind"] == "work"]

    repeat = _find_repeats(segments)

    if repeat:
        watt_label = f"{repeat['avg_watts']:.0f}W"
        if ftp:
            watt_label += f" ({repeat['avg_watts'] / ftp * 100:.0f}% FTP)"
        label = f"{repeat['count']} x {_nice_duration_label(repeat['avg_duration_s'])} @ {watt_label}"
        if repeat["avg_recovery_s"]:
            label += f", {_nice_duration_label(repeat['avg_recovery_s'])} recovery"
    elif len(work_segments) == 1 and work_segments[0]["duration_s"] > len(smoothed) * 0.6:
        avg = work_segments[0]["avg_watts"]
        watt_label = f"{avg:.0f}W" + (f" ({avg / ftp * 100:.0f}% FTP)" if ftp else "")
        label = f"Steady effort @ {watt_label}"
    else:
        label = "Mixed / unstructured ride"

    return {"label": label, "segments": segments, "repeats": repeat}

"""One-off script: build a synthetic Strava-export-shaped zip (activities.csv +
gzipped FIT files with power data) to test the power-stream/interval-detection
pipeline end to end. Not part of the app itself."""
import datetime
import gzip
import zipfile

import numpy as np
from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.profile_type import FileType


def build_fit_bytes(start: datetime.datetime, power_series) -> bytes:
    builder = FitFileBuilder()
    file_id = FileIdMessage()
    file_id.type = FileType.ACTIVITY
    builder.add(file_id)
    for i, watts in enumerate(power_series):
        rm = RecordMessage()
        rm.timestamp = int((start + datetime.timedelta(seconds=i)).timestamp() * 1000)
        rm.power = int(watts)
        builder.add(rm)
    fit_file = builder.build()
    return bytes(fit_file.to_bytes())


def make_interval_power(n_reps, work_s, work_w, rest_s, rest_w, warmup_s=300, cooldown_s=300):
    rng = np.random.default_rng(0)
    series = list(150 + rng.normal(0, 8, warmup_s))
    for _ in range(n_reps):
        series += list(work_w + rng.normal(0, 10, work_s))
        series += list(rest_w + rng.normal(0, 8, rest_s))
    series += list(100 + rng.normal(0, 8, cooldown_s))
    return series


def main():
    activities_csv = (
        "Activity ID,Activity Date,Activity Name,Activity Type,Filename,"
        "Elapsed Time,Distance,Elapsed Time.1,Moving Time,Distance.1,"
        "Elevation Gain,Average Watts,Max Watts,Weighted Average Power,"
        "Average Heart Rate,Max Heart Rate,Average Cadence,Calories,Relative Effort\n"
    )

    rows = []
    fit_members = {}

    rides = [
        ("9001", "2026-06-01 08:00:00", "5x5 VO2", make_interval_power(5, 300, 280, 180, 120)),
        ("9002", "2026-06-03 08:00:00", "30/30s", make_interval_power(12, 30, 340, 30, 100)),
        ("9003", "2026-06-05 08:00:00", "Endurance Spin", list(150 + np.random.default_rng(1).normal(0, 10, 3600))),
    ]

    for activity_id, date_str, name, power_series in rides:
        start = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        fit_bytes = build_fit_bytes(start, power_series)
        member_name = f"activities/{activity_id}.fit.gz"
        fit_members[member_name] = gzip.compress(fit_bytes)

        rows.append(
            f"{activity_id},\"{start.strftime('%b %-d, %Y, %-I:%M:%S %p')}\",{name},Virtual Ride,"
            f"{member_name},3600,50000,3600,3600,50000,500,"
            f"{np.mean(power_series):.1f},{np.max(power_series):.1f},{np.mean(power_series) * 1.05:.1f},"
            f"140,170,85,1200,120\n"
        )

    with zipfile.ZipFile("/tmp/test_export.zip", "w") as zf:
        zf.writestr("activities.csv", activities_csv + "".join(rows))
        for member_name, data in fit_members.items():
            zf.writestr(member_name, data)

    print("wrote /tmp/test_export.zip")


if __name__ == "__main__":
    main()

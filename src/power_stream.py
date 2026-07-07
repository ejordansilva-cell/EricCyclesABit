"""Extract per-second power data from FIT files bundled in a Strava bulk-export zip.

Only reads the single requested member out of the zip, so this is fine to
use even against multi-gigabyte exports without ever loading the whole
archive into memory.
"""
from __future__ import annotations

import gzip
import io
import zipfile
from pathlib import Path

import pandas as pd

try:
    import fitparse
except ImportError:  # pragma: no cover
    fitparse = None


def _read_member_bytes(zip_path: Path, member_path: str) -> bytes | None:
    with zipfile.ZipFile(zip_path) as zf:
        candidates = [member_path, member_path.lstrip("/")]
        name = next((n for n in zf.namelist() if n in candidates), None)
        if name is None:
            # Strava sometimes stores a slightly different relative path than
            # what's recorded in activities.csv; fall back to a basename match.
            base = Path(member_path).name
            name = next((n for n in zf.namelist() if Path(n).name == base), None)
        if name is None:
            return None
        return zf.read(name)


def _parse_fit_power(raw: bytes) -> pd.DataFrame | None:
    if fitparse is None:
        raise RuntimeError("fitparse is not installed — add it to requirements.txt")

    fit = fitparse.FitFile(io.BytesIO(raw))
    rows = []
    for record in fit.get_messages("record"):
        values = {d.name: d.value for d in record}
        if "power" in values and "timestamp" in values and values["power"] is not None:
            rows.append((values["timestamp"], values["power"]))

    if not rows:
        return None

    df = pd.DataFrame(rows, columns=["timestamp", "watts"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    df["elapsed_s"] = (df["timestamp"] - df["timestamp"].iloc[0]).dt.total_seconds()
    return df[["elapsed_s", "watts"]]


def get_power_stream(zip_path: Path, member_path: str) -> pd.DataFrame | None:
    """Returns a DataFrame with columns [elapsed_s, watts], or None if the
    activity file can't be found or has no power data (e.g. GPX rides without
    a power meter)."""
    if not member_path or pd.isna(member_path):
        return None

    raw = _read_member_bytes(Path(zip_path), str(member_path))
    if raw is None:
        return None

    suffix = Path(str(member_path)).suffix.lower()
    if suffix == ".gz":
        raw = gzip.decompress(raw)
        suffix = Path(str(member_path)[: -len(".gz")]).suffix.lower()

    if suffix == ".fit":
        return _parse_fit_power(raw)

    # GPX/TCX rarely carry reliable power extensions in bulk exports — skip.
    return None

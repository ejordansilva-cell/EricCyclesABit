"""EricCyclesABit — a personal dashboard for tracking cycling goals from
Strava and TrainerRoad exports."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import goals as goals_mod
from src import metrics
from src import power_stream
from src import storage
from src import training_plan
from src import workout_detection
from src.ingestion import strava as strava_ingest
from src.ingestion import trainerroad as trainerroad_ingest

st.set_page_config(page_title="EricCyclesABit", page_icon="🚴", layout="wide")


def _init_state() -> None:
    if "strava_rides" not in st.session_state:
        st.session_state.strava_rides = storage.load_rides(storage.STRAVA_PATH)
    if "trainerroad_rides" not in st.session_state:
        st.session_state.trainerroad_rides = storage.load_rides(storage.TRAINERROAD_PATH)
    if "goals" not in st.session_state:
        st.session_state.goals = storage.load_goals() or goals_mod.default_goals()
    if "strava_zip_path" not in st.session_state:
        st.session_state.strava_zip_path = storage.load_strava_zip_path()
    if "workout_cache" not in st.session_state:
        st.session_state.workout_cache = storage.load_workout_cache()


_init_state()


def page_upload() -> None:
    st.header("Upload your ride data")

    st.subheader("Strava export")
    st.caption(
        "Settings → My Account → Download or Delete Your Account → Bulk Export "
        "(Strava emails you a zip). If it's large (the zip with individual activity "
        "files can easily be 1GB+), don't upload it through the browser — point the "
        "app at the file on disk instead."
    )

    zip_path_input = st.text_input(
        "Local path to your Strava export zip (or activities.csv)",
        value=st.session_state.strava_zip_path or "",
        placeholder="/Users/you/Downloads/export_12345.zip",
    )
    if st.button("Load from path"):
        try:
            df = strava_ingest.load_strava_export_from_path(zip_path_input)
        except Exception as exc:
            st.error(f"Couldn't load that file: {exc}")
        else:
            st.session_state.strava_rides = df
            storage.save_rides(df, storage.STRAVA_PATH)
            if zip_path_input.lower().endswith(".zip"):
                st.session_state.strava_zip_path = zip_path_input
                storage.save_strava_zip_path(zip_path_input)
            st.success(f"Loaded {len(df)} rides from Strava.")

    with st.expander("Or upload directly (fine for files under a couple hundred MB)"):
        strava_file = st.file_uploader("activities.csv or export.zip", type=["csv", "zip"], key="strava_upl")
        if strava_file is not None:
            try:
                df = strava_ingest.load_strava_export(strava_file)
            except Exception as exc:
                st.error(f"Couldn't parse that file: {exc}")
            else:
                st.session_state.strava_rides = df
                storage.save_rides(df, storage.STRAVA_PATH)
                st.success(f"Loaded {len(df)} rides from Strava.")

        if st.button("Load sample Strava data"):
            with open("sample_data/strava_activities_sample.csv", "rb") as f:
                df = strava_ingest.load_strava_export(f)
            st.session_state.strava_rides = df
            storage.save_rides(df, storage.STRAVA_PATH)
            st.success(f"Loaded {len(df)} sample rides.")

    rides = st.session_state.strava_rides
    if rides is not None and not rides.empty:
        st.metric("Rides loaded", len(rides))
        st.caption(f"{rides['date'].min().date()} — {rides['date'].max().date()}")
        if st.session_state.strava_zip_path:
            st.caption(
                f"Using `{st.session_state.strava_zip_path}` for per-ride power data "
                "(workout structure detection) on the Rides Explorer page."
            )

    st.divider()

    st.subheader("TrainerRoad export (optional)")
    st.caption(
        "If your TrainerRoad plan lets you export workout history / career CSV, you "
        "can add it here for FTP history. If not — no problem, set your current FTP "
        "manually on the Goals page instead."
    )
    tr_file = st.file_uploader("workout history CSV", type=["csv"], key="tr_upl")
    if tr_file is not None:
        try:
            df = trainerroad_ingest.load_trainerroad_export(tr_file)
        except Exception as exc:
            st.error(f"Couldn't parse that file: {exc}")
        else:
            st.session_state.trainerroad_rides = df
            storage.save_rides(df, storage.TRAINERROAD_PATH)
            st.success(f"Loaded {len(df)} workouts from TrainerRoad.")

    tr_rides = st.session_state.trainerroad_rides
    if tr_rides is not None and not tr_rides.empty:
        st.metric("Workouts loaded", len(tr_rides))
        st.caption(f"{tr_rides['date'].min().date()} — {tr_rides['date'].max().date()}")


def page_goals() -> None:
    st.header("Your goals")
    goals = st.session_state.goals

    with st.form("goals_form"):
        st.subheader("FTP / power")
        ftp_enabled = st.checkbox("Track FTP goal", value=goals["ftp"]["enabled"])
        current_ftp_value = goals["ftp"].get("current_watts")
        ftp_current = st.number_input(
            "Current FTP (watts) — enter your latest known value",
            min_value=0, value=int(current_ftp_value) if current_ftp_value else 0,
        )
        ftp_target = st.number_input("Target FTP (watts)", min_value=0, value=int(goals["ftp"]["target_watts"]))
        ftp_date = st.date_input(
            "Target date",
            value=dt.date.fromisoformat(goals["ftp"]["target_date"]),
        )

        st.subheader("Distance")
        dist_enabled = st.checkbox("Track distance goal", value=goals["distance"]["enabled"])
        dist_target = st.number_input(
            "Target miles this year", min_value=0, value=int(goals["distance"]["target_miles"])
        )

        st.subheader("Elevation / climbing")
        elev_enabled = st.checkbox("Track elevation goal", value=goals["elevation"]["enabled"])
        elev_target = st.number_input(
            "Target elevation gain this year (ft)", min_value=0, value=int(goals["elevation"]["target_ft"])
        )

        st.subheader("Consistency")
        cons_enabled = st.checkbox("Track consistency goal", value=goals["consistency"]["enabled"])
        cons_target = st.number_input(
            "Target rides per week", min_value=0.0, step=0.5,
            value=float(goals["consistency"]["target_rides_per_week"]),
        )

        if st.form_submit_button("Save goals"):
            year = dt.date.today().year
            new_goals = {
                "ftp": {
                    "enabled": ftp_enabled,
                    "target_watts": ftp_target,
                    "target_date": ftp_date.isoformat(),
                    "current_watts": ftp_current or None,
                },
                "distance": {"enabled": dist_enabled, "target_miles": dist_target, "year": year},
                "elevation": {"enabled": elev_enabled, "target_ft": elev_target, "year": year},
                "consistency": {"enabled": cons_enabled, "target_rides_per_week": cons_target},
            }
            st.session_state.goals = new_goals
            storage.save_goals(new_goals)
            st.success("Goals saved.")


def _empty_df() -> pd.DataFrame:
    return pd.DataFrame()


def page_dashboard() -> None:
    st.header("Dashboard")
    strava_rides = st.session_state.strava_rides
    tr_rides = st.session_state.trainerroad_rides
    goals = st.session_state.goals

    if (strava_rides is None or strava_rides.empty) and (tr_rides is None or tr_rides.empty):
        st.info("No data loaded yet — head to **Upload Data** to get started.")
        return

    strava_rides = strava_rides if strava_rides is not None else _empty_df()
    tr_rides = tr_rides if tr_rides is not None else _empty_df()

    cols = st.columns(4)

    if goals["ftp"]["enabled"]:
        result = goals_mod.ftp_progress(tr_rides, goals["ftp"])
        with cols[0]:
            st.metric(
                "FTP",
                f"{result['current']:.0f} W" if result["current"] else "—",
                delta=f"target {result['target']:.0f} W" if result["target"] else None,
            )
            if result["pct"] is not None:
                st.progress(result["pct"])

    if goals["distance"]["enabled"]:
        result = goals_mod.distance_progress(strava_rides, goals["distance"])
        with cols[1]:
            st.metric(f"Distance ({result['year']})", f"{result['current']:.0f} mi")
            st.caption(f"target {result['target']:.0f} mi · pace {result['projected']:.0f} mi")
            if result["pct"] is not None:
                st.progress(result["pct"])

    if goals["elevation"]["enabled"]:
        result = goals_mod.elevation_progress(strava_rides, goals["elevation"])
        with cols[2]:
            st.metric(f"Elevation ({result['year']})", f"{result['current']:.0f} ft")
            st.caption(f"target {result['target']:.0f} ft · pace {result['projected']:.0f} ft")
            if result["pct"] is not None:
                st.progress(result["pct"])

    if goals["consistency"]["enabled"]:
        result = goals_mod.consistency_progress(strava_rides, goals["consistency"])
        with cols[3]:
            st.metric("Rides/week (4wk avg)", f"{result['current_avg_rides_per_week']:.1f}")
            st.caption(f"target {result['target']:.1f}/week")
            if result["pct"] is not None:
                st.progress(result["pct"])

    st.divider()

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("FTP progression")
        if goals["ftp"]["enabled"] and not tr_rides.empty:
            history = trainerroad_ingest.ftp_history(tr_rides)
            if not history.empty:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=history["date"], y=history["ftp"], mode="lines+markers", name="FTP"))
                fig.add_hline(
                    y=goals["ftp"]["target_watts"], line_dash="dash",
                    annotation_text="target", line_color="gray",
                )
                fig.update_layout(yaxis_title="watts", margin=dict(t=10))
                st.plotly_chart(fig, width='stretch')
            else:
                st.caption("No FTP values found in your TrainerRoad export.")
        else:
            st.caption(
                "No FTP history to chart — set your current FTP manually on the "
                "Goals page, or upload a TrainerRoad export for a history line."
            )

    with chart_col2:
        st.subheader("Weekly volume")
        if not strava_rides.empty:
            weekly = metrics.weekly_summary(strava_rides)
            fig = px.bar(weekly, x="week_start", y="hours", labels={"week_start": "week", "hours": "hours"})
            st.plotly_chart(fig, width='stretch')
            fig2 = px.bar(weekly, x="week_start", y="rides", labels={"week_start": "week", "rides": "rides"})
            if goals["consistency"]["enabled"]:
                fig2.add_hline(
                    y=goals["consistency"]["target_rides_per_week"], line_dash="dash",
                    annotation_text="target", line_color="gray",
                )
            st.plotly_chart(fig2, width='stretch')
        else:
            st.caption("Upload Strava data to see weekly volume.")

    chart_col3, chart_col4 = st.columns(2)

    with chart_col3:
        st.subheader("Cumulative distance")
        if goals["distance"]["enabled"] and not strava_rides.empty:
            result = goals_mod.distance_progress(strava_rides, goals["distance"])
            cum = result["cumulative"]
            if not cum.empty:
                fig = px.area(cum, x="date", y="cumulative", labels={"cumulative": "miles"})
                fig.add_hline(y=result["target"], line_dash="dash", annotation_text="target", line_color="gray")
                st.plotly_chart(fig, width='stretch')
        else:
            st.caption("Upload Strava data to see distance progress.")

    with chart_col4:
        st.subheader("Cumulative elevation")
        if goals["elevation"]["enabled"] and not strava_rides.empty:
            result = goals_mod.elevation_progress(strava_rides, goals["elevation"])
            cum = result["cumulative"]
            if not cum.empty:
                fig = px.area(cum, x="date", y="cumulative", labels={"cumulative": "feet"})
                fig.add_hline(y=result["target"], line_dash="dash", annotation_text="target", line_color="gray")
                st.plotly_chart(fig, width='stretch')
        else:
            st.caption("Upload Strava data to see elevation progress.")


def page_rides() -> None:
    st.header("Rides explorer")
    strava_rides = st.session_state.strava_rides

    if strava_rides is None or strava_rides.empty:
        st.info("No Strava data loaded yet.")
        return

    min_date, max_date = strava_rides["date"].min().date(), strava_rides["date"].max().date()
    date_range = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)

    sport_types = sorted(strava_rides["sport_type"].dropna().unique())
    selected_types = st.multiselect("Ride type", sport_types, default=sport_types)

    filtered = strava_rides[
        (strava_rides["date"].dt.date >= date_range[0])
        & (strava_rides["date"].dt.date <= date_range[-1])
        & (strava_rides["sport_type"].isin(selected_types))
    ]

    longest = metrics.longest_ride(filtered)
    if longest is not None:
        st.caption(
            f"Longest ride in range: {longest['name']} — {longest['distance_mi']:.1f} mi "
            f"on {longest['date'].date()}"
        )

    display_cols = [
        "date", "name", "sport_type", "distance_mi", "moving_time_min",
        "elevation_gain_ft", "avg_watts", "avg_hr",
    ]
    table = filtered.sort_values("date", ascending=False).reset_index(drop=True)

    selection = st.dataframe(
        table[display_cols],
        width='stretch',
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="rides_table",
    )

    st.divider()
    st.subheader("Workout structure")

    zip_path = st.session_state.strava_zip_path
    if not zip_path:
        st.caption(
            "Point the Upload Data page at your local Strava export **zip** (not just "
            "activities.csv) to detect interval structure from power data."
        )
        return

    rows = selection.get("selection", {}).get("rows", []) if selection else []
    if not rows:
        st.caption("Select a ride above to see its detected interval structure.")
        return

    ride = table.iloc[rows[0]]
    activity_id = str(ride["activity_id"])
    st.write(f"**{ride['name']}** — {ride['date'].date()}")

    with st.spinner("Extracting power data..."):
        stream = power_stream.get_power_stream(zip_path, ride.get("filename"))

    cache = st.session_state.workout_cache
    if activity_id in cache:
        result = cache[activity_id]
    elif stream is not None:
        current_ftp = st.session_state.goals["ftp"].get("current_watts")
        result = workout_detection.detect_intervals(stream, ftp=current_ftp)
        cache[activity_id] = {"label": result["label"], "repeats": result["repeats"]}
        storage.save_workout_cache(cache)
    else:
        result = {"label": "No power data found for this ride."}

    st.info(result["label"])

    if stream is not None and not stream.empty:
        fig = px.line(stream, x="elapsed_s", y="watts", labels={"elapsed_s": "seconds", "watts": "watts"})
        st.plotly_chart(fig, width='stretch')


def page_training_plan() -> None:
    st.header("Training Plan")
    st.caption(
        "Heuristic, not a physiological model: TSS is estimated from ride-summary power "
        "(not a full power-duration curve), and the pace assessment is a read of your "
        "recent load trend, not a guarantee. Use this as a starting point to adjust."
    )

    strava_rides = st.session_state.strava_rides
    goals = st.session_state.goals

    if strava_rides is None or strava_rides.empty:
        st.info("No Strava data loaded yet — head to **Upload Data** to get started.")
        return

    current_ftp = goals["ftp"].get("current_watts")
    if not current_ftp:
        st.warning("Set your current FTP on the **Goals** page first — training load estimates need it.")
        return

    rides_tss = metrics.estimate_tss(strava_rides, current_ftp)
    weekly = metrics.weekly_tss(rides_tss)

    if len(weekly) < 3:
        st.info("Not enough ride history yet to establish a training-load trend.")
        return

    st.subheader("Training load")
    recent_avg = weekly.tail(training_plan.ROLLING_WEEKS)["tss"].mean()
    st.metric("Rolling 6-week avg TSS/week", f"{recent_avg:.0f}")

    fig = px.bar(weekly, x="week_start", y="tss", labels={"week_start": "week", "tss": "TSS"})
    fig.add_scatter(
        x=weekly["week_start"], y=weekly["tss"].rolling(training_plan.ROLLING_WEEKS).mean(),
        mode="lines", name="6-wk rolling avg",
    )
    st.plotly_chart(fig, width='stretch')

    pace = training_plan.assess_ftp_pace(weekly, goals["ftp"])
    st.info(pace["message"])

    overreach_events = training_plan.detect_overreach_events(weekly)
    if overreach_events:
        dates = ", ".join(pd.Timestamp(e["week_start"]).strftime("%b %-d") for e in overreach_events[-5:])
        st.caption(
            f"Detected past week(s) where load spiked then dropped sharply (a rough burnout proxy): "
            f"{dates}. Future ramps are kept more conservative as a result."
        )

    st.divider()
    st.subheader("Next 2 weeks")

    ride_days_per_week = goals["consistency"].get("target_rides_per_week", 4)
    plan = training_plan.build_two_week_plan(
        strava_rides, goals["ftp"], ride_days_per_week, weekly, today=dt.date.today(),
    )

    for week in plan["weeks"]:
        st.write(
            f"**Week {week['week_num']} — {week['kind'].title()}** "
            f"(target ~{week['target_tss']:.0f} TSS, planned ~{week['planned_total_tss']:.0f} TSS)"
        )
        table = pd.DataFrame(week["days"])
        table["date"] = table["date"].apply(lambda d: d.strftime("%a %b %-d"))
        table = table.rename(columns={
            "date": "Date", "label": "Workout", "duration_min": "Duration (min)", "est_tss": "Est. TSS",
        })[["Date", "Workout", "Duration (min)", "Est. TSS"]]
        st.dataframe(table, width='stretch', hide_index=True)


PAGES = {
    "Dashboard": page_dashboard,
    "Goals": page_goals,
    "Training Plan": page_training_plan,
    "Upload Data": page_upload,
    "Rides Explorer": page_rides,
}


def main() -> None:
    st.sidebar.title("🚴 EricCyclesABit")
    choice = st.sidebar.radio("Navigate", list(PAGES.keys()))
    PAGES[choice]()


if __name__ == "__main__":
    main()

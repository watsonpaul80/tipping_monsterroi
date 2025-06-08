#!/usr/bin/env python3
import json
import os
from datetime import timedelta

import boto3
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

load_dotenv()


def get_confidence_band(conf: float) -> str | None:
    """Return the confidence band label for `conf`."""
    bins = [
        (0.50, 0.60),
        (0.60, 0.70),
        (0.70, 0.80),
        (0.80, 0.90),
        (0.90, 1.00),
        (0.99, 1.01),
    ]
    for low, high in bins:
        if low <= conf < high:
            return f"{low:.2f}\u2013{high:.2f}"
    return None


def load_recent_roi_stats(path: str, ref_date: str, window: int = 30) -> dict:
    """Return ROI per confidence bin for `window` days up to `ref_date`."""
    if not os.path.exists(path):
        return {}

    df_roi = pd.read_csv(path)
    if df_roi.empty:
        return {}

    df_roi["Date"] = pd.to_datetime(df_roi["Date"], errors="coerce")
    df_roi["Win PnL"] = pd.to_numeric(df_roi["Win PnL"], errors="coerce").fillna(0)
    df_roi["Tips"] = pd.to_numeric(df_roi["Tips"], errors="coerce").fillna(0)

    ref = pd.to_datetime(ref_date)
    start = ref - timedelta(days=window)
    df_roi = df_roi[(df_roi["Date"] >= start) & (df_roi["Date"] <= ref)]

    roi = {}
    for band, grp in df_roi.groupby("Confidence Bin"):
        tips = grp["Tips"].sum()
        pnl = grp["Win PnL"].sum()
        roi[band] = pnl / tips if tips else 0.0
    return roi


def load_sent_confidence(date_str: str) -> dict:
    """Return mapping of (course, time, horse) to confidence for a date."""
    path = f"logs/sent_tips_{date_str}.jsonl"
    conf_map = {}
    if not os.path.exists(path):
        return conf_map
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                tip = json.loads(line)
                race = tip.get("race", "")
                if " " not in race:
                    continue
                time_str, course = race.split(" ", 1)
                horse = str(tip.get("name", "")).strip().lower()
                key = (course.strip().lower(), time_str.lstrip("0"), horse)
                conf_map[key] = float(tip.get("confidence", 0.0))
            except Exception:
                continue
    return conf_map


st.set_page_config(page_title="Tipping Monster P&L", layout="wide")


def calc_win_profit(row: pd.Series) -> float:
    """Return profit for a win-only bet based on SP."""
    if str(row.get("Result")) == "NR":
        return 0.0
    stake = row.get("Stake", 1.0)
    sp = float(row.get("SP", 0.0))
    return round((sp - 1) * stake if str(row.get("Result")) == "1" else -stake, 2)


def calc_ew_profit(row: pd.Series) -> float:
    """Return profit for an each-way bet assuming 1/5 odds, 3 places."""
    if str(row.get("Result")) == "NR":
        return 0.0
    sp = float(row.get("SP", 0.0))
    result = str(row.get("Result"))
    win_part = (sp - 1) * 0.5 if result == "1" else 0.0
    place_part = (
        ((sp * 0.2) - 1) * 0.5 if result.isdigit() and int(result) <= 3 else -0.5
    )
    return round(win_part + place_part, 2)


# === AWS S3 SETTINGS ===
# It's good practice to get these from Streamlit secrets or environment variables directly in Streamlit Cloud
# For local development, .env is fine.
bucket = os.getenv("S3_BUCKET")
key = os.getenv("S3_OBJECT")

# Download from S3 into local file
s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_DEFAULT_REGION"),
)

try:
    s3.download_file(bucket, key, "master_subscriber_log.csv")
    df = pd.read_csv("master_subscriber_log.csv")
except NoCredentialsError:
    st.error("❌ AWS credentials missing or invalid.")
    st.stop()
except ClientError as e:
    st.error(f"❌ Could not download file from S3: {e}")
    st.stop()

df["Profit Win"] = df.apply(calc_win_profit, axis=1)
df["Profit EW"] = df.apply(calc_ew_profit, axis=1)
df["Running Profit Win"] = df["Profit Win"].cumsum()
df["Running Profit EW"] = df["Profit EW"].cumsum()

# === CLEAN + FILTER ===
df["Date"] = pd.to_datetime(df["Date"])
df = df.sort_values("Date")

roi_map = load_recent_roi_stats(
    "monster_confidence_per_day_with_roi.csv",
    df["Date"].max().strftime("%Y-%m-%d"),
    30,
)
positive_bins = {band for band, val in roi_map.items() if val > 0}


def attach_confidence(row):
    date_str = row["Date"].date().isoformat()
    if date_str not in st.session_state.confidence_cache:
        st.session_state.confidence_cache[date_str] = load_sent_confidence(date_str)
    key = (
        str(row["Meeting"]).strip().lower(),
        str(row["Time"]).lstrip("0"),
        str(row["Horse"]).strip().lower(),
    )
    return st.session_state.confidence_cache[date_str].get(key)


# Initialize confidence_cache in Streamlit's session state
if "confidence_cache" not in st.session_state:
    st.session_state.confidence_cache = {}

# Sidebar filters
st.sidebar.header("🔎 Filters")
all_dates = sorted(df["Date"].dt.date.unique())
selected_dates = st.sidebar.multiselect("Date Range", all_dates, default=all_dates[-7:])
filtered = df[df["Date"].dt.date.isin(selected_dates)]

# Add ROI View radio toggle
roi_view = st.sidebar.radio("ROI View", ("Win Only", "Each-Way"))

# Apply "Positive ROI Bands Only" filter if checked
if st.sidebar.checkbox("Positive ROI Bands Only"):
    # Ensure confidence is attached only if this filter is active
    filtered = filtered.copy()  # Operate on a copy to avoid SettingWithCopyWarning
    filtered["Confidence"] = filtered.apply(attach_confidence, axis=1)
    filtered["Band"] = filtered["Confidence"].apply(get_confidence_band)
    filtered = filtered[filtered["Band"].isin(positive_bins)]

# Optional sidebar filters for the table view
show_winners_only = st.sidebar.checkbox("Show Winners Only")
show_placed_only = st.sidebar.checkbox("Show Placed Only")

# Summary Metrics
st.subheader("📦 Summary Stats")
total_tips = len(filtered)
winners = (filtered["Result"] == "1").sum()

# Dynamically select profit column based on ROI view
profit_col = "Profit Win" if roi_view == "Win Only" else "Profit EW"
run_col = "Running Profit Win" if roi_view == "Win Only" else "Running Profit EW"

profit = round(filtered[profit_col].sum(), 2)
best_profit = round(filtered[run_col].iloc[-1], 2) if not filtered.empty else 0
stake_total = filtered["Stake"].sum()
roi = (profit / stake_total * 100) if stake_total else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Tips", total_tips)
col2.metric("Winners", winners)
col3.metric("Profit (pts)", profit)
col4.metric("ROI %", f"{roi:.2f}%")

# Line Chart – Running Profit
# Ensure the `run_col` is present before grouping
df_plot = filtered.groupby("Date")[run_col].max().reset_index()
df_plot["Date"] = pd.to_datetime(df_plot["Date"])

st.subheader("📈 Cumulative Profit Over Time")
fig, ax = plt.subplots()
ax.plot(df_plot["Date"], df_plot[run_col], marker="o", label=roi_view)
ax.set_xlabel("Date")
ax.set_ylabel("Profit (pts)")
ax.grid(True)
ax.legend()
st.pyplot(fig)

# Table View
st.subheader("📋 Tips Breakdown")

# Apply optional filters for winners or placed horses for the table display
table_df = filtered.copy()
if show_winners_only:
    table_df = table_df[table_df["Result"] == "1"]
elif show_placed_only:
    # Assuming "Placed" means 1st, 2nd, or 3rd. Adjust if "Placed" has a specific result code.
    table_df = table_df[table_df["Result"].isin(["1", "2", "3"])]

# Display selected columns including the chosen profit column
show_cols = [
    "Date",
    "Time",
    "Horse",
    "EW/Win",
    profit_col,  # Use the dynamically selected profit column
    "Result",
    "SP",  # Added SP for context in the table
    "Meeting",  # Added Meeting for context in the table
]

# Ensure only existing columns are selected to avoid KeyError
show_cols_existing = [col for col in show_cols if col in table_df.columns]

st.dataframe(
    table_df.sort_values(by=["Date", "Time"], ascending=[False, True])[
        show_cols_existing
    ]
)

# Danger Fav section
st.subheader("⚠️ Danger Favs")
danger_date = st.sidebar.selectbox(
    "Danger Fav Date", all_dates, index=len(all_dates) - 1
)


def load_danger_favs(date_str: str) -> pd.DataFrame | None:
    path = f"predictions/{date_str}/danger_favs.jsonl"
    if not os.path.exists(path):
        return None
    return pd.read_json(path, lines=True)


danger_df = load_danger_favs(
    danger_date.isoformat() if hasattr(danger_date, "isoformat") else str(danger_date)
)
if danger_df is not None and not danger_df.empty:
    sort_field = st.selectbox(
        "Sort Danger Favs By", ["confidence", "bf_sp"], key="df_sort"
    )
    danger_df = danger_df.sort_values(by=sort_field, ascending=False)
    st.dataframe(danger_df)
else:
    st.write("No Danger Favs found for selected date.")

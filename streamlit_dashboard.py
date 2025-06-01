import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import boto3
from botocore.exceptions import NoCredentialsError, ClientError

st.set_page_config(page_title="Tipping Monster P&L", layout="wide")

# === AWS S3 SETTINGS FROM STREAMLIT SECRETS ===
secrets = st.secrets["aws"]
bucket = secrets["bucket"]
key = secrets["object"]

# Download from S3 into local file
s3 = boto3.client(
    "s3",
    aws_access_key_id=secrets["aws_access_key_id"],
    aws_secret_access_key=secrets["aws_secret_access_key"],
    region_name=secrets["region"]
)

try:
    s3.download_file(bucket, key, "master_subscriber_log.csv")
    df = pd.read_csv("master_subscriber_log.csv")
except NoCredentialsError:
    st.error("\u274c AWS credentials missing or invalid.")
    st.stop()
except ClientError as e:
    st.error(f"\u274c Could not download file from S3: {e}")
    st.stop()

# === CLEAN + FILTER ===
df['Date'] = pd.to_datetime(df['Date'])
df = df.sort_values("Date")

# Sidebar filters
st.sidebar.header("\ud83d\udd0d Filters")
all_dates = sorted(df['Date'].dt.date.unique())
selected_dates = st.sidebar.multiselect("Date Range", all_dates, default=all_dates[-7:])
filtered = df[df['Date'].dt.date.isin(selected_dates)]

# Summary Metrics
st.subheader("\ud83d\udcbe Summary Stats")
total_tips = len(filtered)
winners = (filtered['Result'] == '1').sum()
profit = round(filtered['Profit'].sum(), 2)
best_profit = round(filtered['Running Profit Best Odds'].iloc[-1], 2) if not filtered.empty else 0
stake_total = filtered['Stake'].sum()
roi = (profit / stake_total * 100) if stake_total else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Tips", total_tips)
col2.metric("Winners", winners)
col3.metric("Profit (pts)", profit)
col4.metric("ROI %", f"{roi:.2f}%")

# Line Chart – Running Profit
df_plot = filtered.groupby("Date")["Running Profit"].max().reset_index()
df_plot["Date"] = pd.to_datetime(df_plot["Date"])

st.subheader("\ud83d\udcca Cumulative Profit Over Time")
fig, ax = plt.subplots()
ax.plot(df_plot["Date"], df_plot["Running Profit"], marker="o", label="Standard Odds")
ax.set_xlabel("Date")
ax.set_ylabel("Profit (pts)")
ax.grid(True)
ax.legend()
st.pyplot(fig)

# Table View
st.subheader("\ud83d\udcc4 Tips Breakdown")
st.dataframe(filtered.sort_values(by=["Date", "Time"], ascending=[False, True]))

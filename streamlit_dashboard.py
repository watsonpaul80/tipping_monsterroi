import streamlit as st
import pandas as pd

st.set_page_config(page_title="Tipping Monster ROI", layout="wide")

@st.cache_data
def load_data():
    url = "https://tipping-monster-data.s3.eu-west-2.amazonaws.com/master_subscriber_log.csv"
    df = pd.read_csv(url)
    df = df[df['Date'].str.len() == 10]  # avoid malformed dates
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])
    return df

df = load_data()

st.title("📊 Tipping Monster Dashboard")
st.markdown("### Filter and Explore ROI Performance")

# Sidebar Filters
with st.sidebar:
    trainer_filter = st.multiselect("Trainer", sorted(df['Trainer'].dropna().unique()))
    jockey_filter = st.multiselect("Jockey", sorted(df['Jockey'].dropna().unique()))
    meeting_filter = st.multiselect("Meeting", sorted(df['Meeting'].dropna().unique()))
    ew_filter = st.radio("Bet Type", ["All", "Win", "EW"], index=0)
    date_range = st.date_input("Date Range", [df['Date'].min(), df['Date'].max()])

filtered = df.copy()

if trainer_filter:
    filtered = filtered[filtered['Trainer'].isin(trainer_filter)]
if jockey_filter:
    filtered = filtered[filtered['Jockey'].isin(jockey_filter)]
if meeting_filter:
    filtered = filtered[filtered['Meeting'].isin(meeting_filter)]
if ew_filter != "All":
    filtered = filtered[filtered['EW/Win'] == ew_filter]
if len(date_range) == 2:
    start_date, end_date = date_range
    filtered = filtered[(filtered['Date'] >= pd.to_datetime(start_date)) & (filtered['Date'] <= pd.to_datetime(end_date))]

# Main Table
st.dataframe(filtered.sort_values("Date", ascending=False), use_container_width=True)

# ROI Summary
total_stake = filtered['Stake'].sum()
roi = (filtered['Profit'].sum() / total_stake * 100) if total_stake > 0 else 0
roi_best = (filtered['Running Profit Best Odds'].iloc[-1] / total_stake * 100) if total_stake > 0 else 0

st.markdown("---")
st.subheader("💰 ROI Summary")
st.metric("💰 Level Stake ROI", f"{roi:.2f}%")
st.metric("🏆 Best Odds ROI", f"{roi_best:.2f}%")

# Footer
st.markdown("---")
st.caption("Tipping Monster 🧐 built for dominance. Updated live from S3 logs.")

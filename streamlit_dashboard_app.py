import pandas as pd
import streamlit as st
import boto3
from io import StringIO

# === CONFIG ===
BUCKET = "tipping-monster-data"
KEY = "master_subscriber_log.csv"

# === Load Data from S3 ===
@st.cache_data
def load_data():
    access_key = st.secrets["aws_access_key_id"]
    secret_key = st.secrets["aws_secret_access_key"]

    s3 = boto3.client("s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key
    )
    response = s3.get_object(Bucket=BUCKET, Key=KEY)
    csv_string = response["Body"].read().decode("utf-8")
    df = pd.read_csv(StringIO(csv_string))

    # Strip suffixes like "_realistic" from Date and ensure proper format
    df["Date"] = df["Date"].astype(str).str.extract(r"(\d{4}-\d{2}-\d{2})")[0]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])

    return df

# === Load & Prep Data ===
df = load_data()
df['Profit'] = df['Profit'].astype(float)
df['Best Odds'] = df['Best Odds'].astype(float)
df['Running Profit'] = df['Running Profit'].astype(float)
df['Running Profit Best Odds'] = df['Running Profit Best Odds'].astype(float)
df['Tags'] = df['Tags'] if 'Tags' in df.columns else ''
df['Trainer'] = df['Trainer'].astype(str) if 'Trainer' in df.columns else 'Unknown'

# === Streamlit UI ===
st.set_page_config(page_title="Tipping Monster Dashboard", layout="wide")
st.title("🧐 Tipping Monster – ROI Dashboard")
st.markdown("Visualise performance from past monster tips. Filter, export, analyse.")

# === Sidebar Filters ===
st.sidebar.header("🔍 Filters")
min_date = df["Date"].min()
max_date = df["Date"].max()

date_range = st.sidebar.date_input("Select Date Range", [min_date, max_date], min_value=min_date, max_value=max_date)
selected_type = st.sidebar.multiselect("Bet Type", options=df["EW/Win"].unique(), default=list(df["EW/Win"].unique()))
selected_jockeys = st.sidebar.multiselect("Jockey", options=sorted(df["Jockey"].unique()), default=list(df["Jockey"].unique()))
selected_trainers = st.sidebar.multiselect("Trainer", options=sorted(df["Trainer"].unique()), default=list(df["Trainer"].unique()))

# === Tag Filtering ===
tag_options = ["NAP", "Steam", "In Form", "Light Weight"]
selected_tags = st.sidebar.multiselect("Tip Tags", tag_options, default=tag_options)

def has_selected_tags(tags, selected):
    return any(tag.lower() in str(tags).lower() for tag in selected)

# === Filter Data ===
filtered = df[
    (df["Date"] >= pd.to_datetime(date_range[0])) &
    (df["Date"] <= pd.to_datetime(date_range[1])) &
    (df["EW/Win"].isin(selected_type)) &
    (df["Jockey"].isin(selected_jockeys)) &
    (df["Trainer"].isin(selected_trainers)) &
    (df["Tags"].apply(lambda x: has_selected_tags(x, selected_tags)))
]

# === Summary Stats ===
total_tips = len(filtered)
total_profit = round(filtered["Profit"].sum(), 2)
total_best_profit = round(filtered["Running Profit Best Odds"].iloc[-1], 2) if not filtered.empty else 0
roi = round((total_profit / total_tips) * 100, 2) if total_tips > 0 else 0
roi_best = round((total_best_profit / total_tips) * 100, 2) if total_tips > 0 else 0

st.markdown(f"""
### 📊 Summary  
- **Tips:** {total_tips}  
- **Profit (SP):** `{total_profit}` pts  
- **Profit (Best Odds):** `{total_best_profit}` pts  
- **ROI (SP):** `{roi}%`  
- **ROI (Best Odds):** `{roi_best}%`
""")

# === Charts ===
st.markdown("### 📈 Profit Over Time")
chart_df = filtered.groupby("Date").agg({"Profit": "sum", "Running Profit": "last", "Running Profit Best Odds": "last"}).reset_index()
st.line_chart(chart_df.set_index("Date")[["Running Profit", "Running Profit Best Odds"]])

# === Per-Day Summary ===
st.markdown("### 📅 Per-Day Summary")
daily_summary = filtered.groupby("Date").agg({
    "Horse": "count",
    "Profit": "sum",
    "Best Odds": "mean",
    "Running Profit": "last",
    "Running Profit Best Odds": "last"
}).rename(columns={"Horse": "Tips"}).reset_index()
st.dataframe(daily_summary, use_container_width=True)

# === Telegram-Style Summary ===
st.markdown("### 📬 Telegram-Style Summary")
for _, row in daily_summary.iterrows():
    st.markdown(f"""
    🗓️ **{row['Date'].date()}**  
    🏇 Tips: {row['Tips']} | 💰 Profit: `{round(row['Profit'], 2)}` pts | 📈 RP: `{round(row['Running Profit'], 2)}` | 💎 BODDS RP: `{round(row['Running Profit Best Odds'], 2)}`
    """)

# === Table ===
st.markdown("### 🧾 Tips Table")
st.dataframe(filtered.sort_values("Date", ascending=False), use_container_width=True)

# === Download ===
csv_download = filtered.to_csv(index=False).encode("utf-8")
st.download_button("📅 Download CSV", csv_download, "tipping_monster_filtered.csv", "text/csv")

import argparse
import json
import os
import pandas as pd
from pathlib import Path
from datetime import datetime
import boto3
from io import StringIO
import streamlit as st

# === CONFIG ===
PRED_DIR = Path("logs")
RESULTS_DIR = Path("rpscrape/data/dates/all")
OUTPUT_DIR = Path("logs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MASTER_LOG = OUTPUT_DIR / "master_subscriber_log.csv"

@st.cache_data
def load_data():
    # Pull secrets from Streamlit's config
    access_key = st.secrets["aws_access_key_id"]
    secret_key = st.secrets["aws_secret_access_key"]

    # Create S3 client
    s3 = boto3.client("s3",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key
    )

    # Read file from S3
    response = s3.get_object(Bucket="tipping-monster-data", Key="master_subscriber_log.csv")
    csv_string = response["Body"].read().decode("utf-8")
    df = pd.read_csv(StringIO(csv_string))

    # Usual cleanup
    df = df[df['Date'].str.len() == 10]
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])

    return df

df = load_data()

st.title("📊 Tipping Monster Dashboard")
st.markdown("### Filter and Explore ROI Performance")

st.dataframe(df)

# You can add more Streamlit components below, e.g., charts, filters, etc.

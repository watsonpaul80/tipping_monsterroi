import argparse
import json
import os
import pandas as pd
from pathlib import Path
from datetime import datetime

# === CONFIG ===
PRED_DIR = Path("logs")
RESULTS_DIR = Path("rpscrape/data/dates/all")
OUTPUT_DIR = Path("logs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MASTER_LOG = OUTPUT_DIR / "master_subscriber_log.csv"

def load_tips(date_str):
    tips_path = PRED_DIR / f"sent_tips_{date_str}.jsonl"
    if not tips_path.exists():
        print(f"❌ Missing tips file: {tips_path}")
        return []
    with open(tips_path, "r") as f:
        return [json.loads(line) for line in f]

def load_results(date_str):
    path = RESULTS_DIR / f"{date_str.replace('-', '_')}.csv"
    if not path.exists():
        print(f"❌ Missing results file: {path}")
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["course"] = df["course"].astype(str).str.strip().str.lower()
    df["horse"] = df["horse"].astype(str).str.lower().str.replace(r" \(.*\)", "", regex=True).str.strip()
    df["off"] = df["off"].astype(str).str.strip()
    return df

def normalize(text):
    return str(text).lower().strip().replace(" (ire)", "").replace(" (gb)", "")

def main(date_str):
    tips = load_tips(date_str)
    results_df = load_results(date_str)
    out_rows = []
    running_profit = 0.0
    running_best_profit = 0.0

    for tip in tips:
        race = tip.get("race", "??:?? Unknown")
        try:
            time_str, meeting = race.split(" ", 1)
        except:
            time_str, meeting = "??:??", "Unknown"

        horse = tip.get("name", "Unknown")
        trainer = tip.get("trainer", "Unknown")
        sp = float(tip.get("bf_sp") or 0)
        odds = float(tip.get("odds") or tip.get("bf_sp") or 0)
        best_odds = float(tip.get("realistic_odds") or odds)
        conf = tip.get("confidence", 0.0)
        ew = odds >= 5.0 or tip.get("each_way", False)
        ew_flag = "EW" if ew else "Win"
        stake = 1.0
        result = "NR"
        pos = None

        value_pct = round((odds / sp) * 100, 2) if sp else "-"
        profit = 0.0
        profit_best = 0.0

        # Match result
        if not results_df.empty:
            match = results_df[
                (results_df["course"] == normalize(meeting)) &
                (results_df["off"] == time_str) &
                (results_df["horse"] == normalize(horse))
            ]
            if not match.empty:
                pos_raw = match.iloc[0]["pos"]
                try:
                    pos = int(pos_raw)
                    result = str(pos)
                except:
                    result = str(pos_raw).strip().upper()

        # Profit logic
        if result != "NR":
            if ew:
                win = (sp - 1) * 0.5 if result == "1" else 0
                place = ((sp * 0.2) - 1) * 0.5 if result.isdigit() and int(result) <= 3 else -0.5
                profit = round(win + place, 2)
                win_b = (best_odds - 1) * 0.5 if result == "1" else 0
                place_b = ((best_odds * 0.2) - 1) * 0.5 if result.isdigit() and int(result) <= 3 else -0.5
                profit_best = round(win_b + place_b, 2)
            else:
                profit = round((sp - 1) * stake if result == "1" else -stake, 2)
                profit_best = round((best_odds - 1) * stake if result == "1" else -stake, 2)

        running_profit += profit
        running_best_profit += profit_best

        out_rows.append({
            "Date": date_str,
            "Meeting": meeting,
            "Time": time_str,
            "EW/Win": ew_flag,
            "Trainer": trainer,
            "Jockey": tip.get("jockey", "Unknown"),
            "Horse": horse,
            "Odds": odds,
            "SP": sp,
            "Value": value_pct,
            "Result": result,
            "Stake": stake,
            "Profit": profit,
            "Running Profit": round(running_profit, 2),
            "Best Odds": best_odds,
            "Running Profit Best Odds": round(running_best_profit, 2)
        })

    df_new = pd.DataFrame(out_rows)

    if MASTER_LOG.exists():
        df_master = pd.read_csv(MASTER_LOG)
        df_master = df_master[~df_master['Date'].str.contains("_realistic")]
        df_master = df_master[~((df_master['Date'] == date_str) & (df_master['Horse'].isin(df_new['Horse'])))]
        df_master = pd.concat([df_master, df_new], ignore_index=True)
    else:
        df_master = df_new

    df_master.to_csv(MASTER_LOG, index=False)
    print(f"✅ Updated master log: {MASTER_LOG}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()
    main(args.date)

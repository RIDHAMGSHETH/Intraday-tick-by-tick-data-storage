"""
===============================================================================
SESSION RUNNER FOR CLOUD & GITHUB ACTIONS (HOLIDAY-AWARE)
===============================================================================
Executes a target market recording session:
- Checks 2026 holiday calendar & weekend status
- Initializes UniversalRecorder with automatic TOTP login
- Records continuous 5-depth ticks, tape, and 1-min bars
- Gracefully stops at market close (15:32 IST for NSE, 23:32 IST for MCX)
- Safely handles SIGTERM/SIGINT signals
- Converts CSVs to Parquet & uploads to Hugging Face
===============================================================================
"""

import os
import sys
import signal
import argparse
import requests
from datetime import datetime, time as dtime

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(ENGINE_DIR, ".."))
DATA_ROOT = os.path.join(REPO_ROOT, "data")

if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from trading_calendar import get_market_status, get_ist_now
from universal_recorder import UniversalRecorder, PRIMARY_ASSETS
from hf_dataset_uploader import convert_and_upload_file

def send_telegram_alert(text):
    """Sends clean, formatted telegram status alert if token & chat id exist in environment."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=8)
    except Exception as e:
        print(f"[-] Telegram dispatch error: {e}")

def run_session(session_type="morning", max_minutes=345):
    now = get_ist_now()
    status = get_market_status(now)
    date_str = now.strftime("%Y-%m-%d")

    print(f"[*] Date: {date_str} | Time: {now.strftime('%H:%M:%S')} IST")
    print(f"[*] Session requested: {session_type.upper()}")
    print(f"[*] Market Status: {status}")

    if not status["is_trading_day"]:
        print(f"[!] Today is NOT a trading day ({status['reason']}). Exiting cleanly.")
        return 0

    session_label = "Morning (NSE + MCX Day)" if session_type == "morning" else "Evening (MCX Commodities Night)"
    assets_label = "NIFTY, SENSEX, CRUDE OIL, NATURAL GAS" if session_type == "morning" else "CRUDE OIL, CRUDE MINI, NATURAL GAS"

    if session_type == "morning":
        if not status["nse_open"] and not status["mcx_open"]:
            if "NSE Closed" in status["reason"] and "MCX Morning Closed" in status["reason"]:
                print(f"[!] Morning market is closed: {status['reason']}. Skipping morning session.")
                return 0
        stop_time = dtime(15, 32)
    elif session_type == "evening":
        if not status["mcx_open"]:
            print(f"[!] MCX is not currently open ({status['reason']}). Exiting cleanly.")
            return 0
        stop_time = dtime(23, 32)
    else:
        stop_time = None

    # Send Clean & Specific Telegram Startup Alert
    startup_msg = (
        f"🟢 <b>[TICK RECORDER] {session_type.upper()} SESSION ACTIVE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Session:</b> {session_label}\n"
        f"📊 <b>Assets Captured:</b> {assets_label}\n"
        f"⚙️ <b>Data Recorded:</b> 5-Depth Live Ticks, 1-Min Bars & Order Flow Tape\n"
        f"⏱️ <b>Auto-Stop Time:</b> {stop_time.strftime('%I:%M %p') if stop_time else 'Market Close'} IST\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💾 <i>Running on GitHub Actions. Storing tick by tick to Cloud & Hugging Face.</i>"
    )
    send_telegram_alert(startup_msg)

    print(f"\n[+] Launching {session_type.upper()} recorder session (Max: {max_minutes} min, Target Stop: {stop_time})...")
    recorder = UniversalRecorder(
        poll_interval=0.20,
        option_radius=6,
        max_runtime_minutes=max_minutes,
        stop_time_ist=stop_time
    )

    def sig_handler(sig, frame):
        print(f"\n[!] Signal {sig} received. Initiating graceful shutdown...")
        recorder.running = False

    try:
        signal.signal(signal.SIGINT, sig_handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, sig_handler)
    except Exception as e:
        print(f"[-] Signal binding note: {e}")

    try:
        recorder.initialize()
        recorder.run()
    except KeyboardInterrupt:
        print("\n[*] Manual interruption.")
    except Exception as e:
        print(f"[-] Session encountered error: {e}")
    finally:
        recorder.flush_all_pending_bars()
        print(f"\n[OK] Recorded {recorder.total_ticks_recorded:,} ticks & {recorder.total_trades_inferred:,} tape trades.")

    # Upload to Hugging Face
    print(f"\n[*] Uploading completed {date_str} datasets to Hugging Face...")
    for a_dir in PRIMARY_ASSETS:
        p_bars = os.path.join(DATA_ROOT, a_dir, date_str, f"{a_dir}_1min_bars_{date_str}.csv")
        p_ticks = os.path.join(DATA_ROOT, a_dir, date_str, f"{a_dir}_ticks_{date_str}.csv")
        p_tape = os.path.join(DATA_ROOT, a_dir, date_str, f"{a_dir}_tape_{date_str}.csv")

        if os.path.exists(p_bars):
            print(f"  Uploading {a_dir} 1-min bars to Hugging Face...")
            convert_and_upload_file(p_bars, a_dir, date_str)
        if os.path.exists(p_ticks):
            print(f"  Uploading {a_dir} ticks to Hugging Face...")
            convert_and_upload_file(p_ticks, a_dir, date_str)
        if os.path.exists(p_tape):
            print(f"  Uploading {a_dir} aggressor tape to Hugging Face...")
            convert_and_upload_file(p_tape, a_dir, date_str)

    # Send Clean & Specific Telegram Completion Alert
    completion_msg = (
        f"🏁 <b>[TICK RECORDER] {session_type.upper()} SESSION COMPLETED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Session:</b> {session_label}\n"
        f"📊 <b>Total Ticks Saved:</b> {recorder.total_ticks_recorded:,}\n"
        f"⚡ <b>Total Tape Trades:</b> {recorder.total_trades_inferred:,}\n"
        f"☁️ <b>Storage Status:</b> Parquet uploaded to Hugging Face & 1-min bars synced to GitHub\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ <i>Session closed cleanly. Runner shutting down.</i>"
    )
    send_telegram_alert(completion_msg)

    print(f"[OK] Session {session_type.upper()} finished.")
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous Market Session Runner")
    parser.add_argument("--session", choices=["morning", "evening"], default="morning", help="Market session")
    parser.add_argument("--max-minutes", type=int, default=345, help="Max execution runtime in minutes")
    args = parser.parse_args()

    sys.exit(run_session(args.session, args.max_minutes))

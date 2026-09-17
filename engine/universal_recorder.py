"""
===============================================================================
UNIVERSAL MULTI-ASSET OPTIONS & FUTURES RECORDER (CLOUD & LOCAL RUNNER)
===============================================================================
Captures High-Frequency Data (Every 100ms - 200ms) into DEDICATED ASSET FOLDERS:
1. data/nifty/YYYY-MM-DD/
2. data/sensex/YYYY-MM-DD/
3. data/crudeoil/YYYY-MM-DD/
4. data/naturalgas/YYYY-MM-DD/

Features:
- Full 5-Level Depth (Bids 1-5, Asks 1-5) on all Options & Futures
- Aggressor Side Trade Inference (BUY / SELL / INSIDE) with Volume Delta
- Automatic Parquet conversion & upload per asset directly to Hugging Face
- Max Runtime enforcement (for GitHub Actions runner limits)
===============================================================================
"""

import os
import sys
import time
import csv
import math
import json
import threading
from datetime import datetime, time as dtime

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(ENGINE_DIR, ".."))
DATA_ROOT = os.path.join(REPO_ROOT, "data")
os.makedirs(DATA_ROOT, exist_ok=True)

if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)

from kotak_neo_session import get_kotak_session
from universal_options_resolver import UniversalOptionsChainResolver
from hf_dataset_uploader import convert_and_upload_file
from trading_calendar import get_market_status, get_ist_now

ASSET_DIR_MAP = {
    "NIFTY": "nifty",
    "SENSEX": "sensex",
    "CRUDEOIL": "crudeoil",
    "CRUDEOILM": "crudeoil",
    "NATURALGAS": "naturalgas",
    "NATGASMINI": "naturalgas"
}

PRIMARY_ASSETS = ["nifty", "sensex", "crudeoil", "naturalgas"]

class UniversalRecorder:
    def __init__(self, poll_interval=0.20, option_radius=6, max_runtime_minutes=None):
        self.poll_interval = poll_interval
        self.option_radius = option_radius
        self.max_runtime_minutes = max_runtime_minutes
        self.client = None
        self.resolver = None
        self.running = True
        
        self.token_to_meta = {}
        self.request_batches = []
        self.prev_state = {}
        self.minute_bars = {}

        self.total_ticks_recorded = 0
        self.total_trades_inferred = 0
        self.start_time = time.time()

    def initialize(self):
        print("\n" + "="*80)
        print("  INITIALIZING UNIVERSAL MULTI-ASSET RECORDER")
        print("  Dedicated Folders: nifty/ | sensex/ | crudeoil/ | naturalgas/")
        print("="*80)

        self.client = get_kotak_session()
        self.resolver = UniversalOptionsChainResolver()

        # Step 1: Probe underlying prices
        print("[*] Probing underlying market prices for ATM discovery...")
        probe_requests = [
            {"instrument_token": "Nifty 50", "exchange_segment": "nse_cm"},
            {"instrument_token": "SENSEX", "exchange_segment": "bse_cm"},
            {"instrument_token": "565899", "exchange_segment": "mcx_fo"},
            {"instrument_token": "565900", "exchange_segment": "mcx_fo"},
            {"instrument_token": "568245", "exchange_segment": "mcx_fo"},
            {"instrument_token": "568246", "exchange_segment": "mcx_fo"},
        ]

        probe_prices = {
            "NIFTY": 23400.0,
            "SENSEX": 74500.0,
            "CRUDEOIL": 9650.0,
            "CRUDEOILM": 9650.0,
            "NATURALGAS": 280.0,
            "NATGASMINI": 280.0
        }

        try:
            quotes = self.client.quotes(instrument_tokens=probe_requests)
            if isinstance(quotes, list):
                for q in quotes:
                    ltp = float(q.get("ltp", 0.0) or q.get("last_price", 0.0))
                    disp = str(q.get("display_symbol", ""))
                    if ltp > 0:
                        if "Nifty 50" in disp: probe_prices["NIFTY"] = ltp
                        elif "SENSEX" in disp: probe_prices["SENSEX"] = ltp
                        elif "CRUDEOILM" in disp: probe_prices["CRUDEOILM"] = ltp
                        elif "CRUDEOIL" in disp: probe_prices["CRUDEOIL"] = ltp
                        elif "NATGASMINI" in disp: probe_prices["NATGASMINI"] = ltp
                        elif "NATURALGAS" in disp: probe_prices["NATURALGAS"] = ltp
        except Exception as e:
            print(f"[-] Warning probing prices: {e}")

        # Step 2: Build complete instrument universe
        all_tokens = []
        for asset, ref_px in probe_prices.items():
            chain = self.resolver.resolve_asset_options(asset, reference_price=ref_px, radius=self.option_radius)
            fut = chain["future"]
            
            fut_seg = "nse_fo" if asset == "NIFTY" else ("bse_fo" if asset == "SENSEX" else "mcx_fo")
            fut_tok_str = str(fut["token"])
            all_tokens.append({"instrument_token": fut_tok_str, "exchange_segment": fut_seg})
            self.token_to_meta[fut_tok_str] = {
                "asset": asset,
                "asset_dir": ASSET_DIR_MAP.get(asset, "other"),
                "type": "FUT",
                "strike": 0.0,
                "trd_symbol": fut["trd_symbol"],
                "segment": fut_seg
            }

            if asset == "NIFTY":
                spot_sym = "Nifty 50"
                all_tokens.append({"instrument_token": spot_sym, "exchange_segment": "nse_cm"})
                self.token_to_meta[spot_sym] = {
                    "asset": "NIFTY", "asset_dir": "nifty", "type": "SPOT", "strike": 0.0,
                    "trd_symbol": spot_sym, "segment": "nse_cm"
                }
            elif asset == "SENSEX":
                spot_sym = "SENSEX"
                all_tokens.append({"instrument_token": spot_sym, "exchange_segment": "bse_cm"})
                self.token_to_meta[spot_sym] = {
                    "asset": "SENSEX", "asset_dir": "sensex", "type": "SPOT", "strike": 0.0,
                    "trd_symbol": spot_sym, "segment": "bse_cm"
                }

            for opt in chain["options"]:
                tok_str = str(opt["token"])
                all_tokens.append({"instrument_token": tok_str, "exchange_segment": opt["segment"]})
                self.token_to_meta[tok_str] = {
                    "asset": asset,
                    "asset_dir": ASSET_DIR_MAP.get(asset, "other"),
                    "type": opt["type"],
                    "strike": opt["strike"],
                    "trd_symbol": opt["trd_symbol"],
                    "segment": opt["segment"]
                }

            print(f"[+] {asset:<10}: Future {fut['trd_symbol']} + {len(chain['options'])} Option contracts around ATM {chain['atm_strike']}")

        batch_size = 35
        self.request_batches = [all_tokens[i:i + batch_size] for i in range(0, len(all_tokens), batch_size)]
        print(f"\n[OK] Monitored Universe: {len(all_tokens)} total contracts split into {len(self.request_batches)} batches.")

    def get_asset_file_paths(self, asset_dir, date_str):
        day_dir = os.path.join(DATA_ROOT, asset_dir, date_str)
        os.makedirs(day_dir, exist_ok=True)

        ticks_csv = os.path.join(day_dir, f"{asset_dir}_ticks_{date_str}.csv")
        tape_csv  = os.path.join(day_dir, f"{asset_dir}_tape_{date_str}.csv")
        bars_csv  = os.path.join(day_dir, f"{asset_dir}_1min_bars_{date_str}.csv")

        if not os.path.exists(ticks_csv) or os.path.getsize(ticks_csv) == 0:
            with open(ticks_csv, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    "timestamp", "asset", "instrument_type", "strike", "trading_symbol",
                    "ltp", "change", "open", "high", "low", "close", "vwap", "volume", "oi",
                    "b1_px", "b1_qty", "b2_px", "b2_qty", "b3_px", "b3_qty", "b4_px", "b4_qty", "b5_px", "b5_qty",
                    "a1_px", "a1_qty", "a2_px", "a2_qty", "a3_px", "a3_qty", "a4_px", "a4_qty", "a5_px", "a5_qty"
                ])

        if not os.path.exists(tape_csv) or os.path.getsize(tape_csv) == 0:
            with open(tape_csv, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    "timestamp", "asset", "instrument_type", "strike", "trading_symbol",
                    "traded_price", "traded_qty", "aggressor_side", "cumulative_vol", "open_interest"
                ])

        if not os.path.exists(bars_csv) or os.path.getsize(bars_csv) == 0:
            with open(bars_csv, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    "timestamp_minute", "asset", "instrument_type", "strike", "trading_symbol",
                    "open", "high", "low", "close", "volume", "tick_count"
                ])

        return ticks_csv, tape_csv, bars_csv

    def get_all_file_paths(self, date_str):
        return {a_dir: self.get_asset_file_paths(a_dir, date_str) for a_dir in PRIMARY_ASSETS}

    def run(self):
        current_date = get_ist_now().strftime("%Y-%m-%d")
        asset_paths = self.get_all_file_paths(current_date)
        last_flush_minute = get_ist_now().strftime("%Y-%m-%d %H:%M")

        print(f"[*] Recording loop started at {get_ist_now().strftime('%Y-%m-%d %H:%M:%S')} (IST)")

        while self.running:
            t_cycle_start = time.perf_counter()
            now = get_ist_now()
            now_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            minute_str = now.strftime("%Y-%m-%d %H:%M:00")
            today_str = now.strftime("%Y-%m-%d")

            # Check max runtime limit (e.g. for GitHub Actions)
            if self.max_runtime_minutes:
                elapsed_min = (time.time() - self.start_time) / 60.0
                if elapsed_min >= self.max_runtime_minutes:
                    print(f"\n[*] Max runtime reached ({elapsed_min:.1f} min). Gracefully stopping recorder...")
                    break

            # Date rollover
            if today_str != current_date:
                print(f"\n[*] Date rollover: {current_date} -> {today_str}")
                current_date = today_str
                asset_paths = self.get_all_file_paths(current_date)

            tick_buffers = {a: [] for a in PRIMARY_ASSETS}
            tape_buffers = {a: [] for a in PRIMARY_ASSETS}

            for batch in self.request_batches:
                try:
                    quotes = self.client.quotes(instrument_tokens=batch)
                    if not isinstance(quotes, list):
                        continue

                    for q in quotes:
                        tok = str(q.get("exchange_token") or q.get("instrument_token") or q.get("display_symbol") or "")
                        meta = self.token_to_meta.get(tok)
                        if not meta:
                            disp = str(q.get("display_symbol", ""))
                            for k_tok, k_meta in self.token_to_meta.items():
                                if k_meta["trd_symbol"] == disp:
                                    meta = k_meta
                                    tok = k_tok
                                    break
                        if not meta:
                            continue

                        ltp = float(q.get("ltp", 0.0) or q.get("last_price", 0.0))
                        if ltp <= 0:
                            continue

                        a_dir = meta["asset_dir"]
                        if a_dir not in tick_buffers:
                            continue

                        ohlc = q.get("ohlc", {})
                        open_p = float(ohlc.get("open", ltp))
                        high_p = float(ohlc.get("high", ltp))
                        low_p  = float(ohlc.get("low", ltp))
                        close_p= float(ohlc.get("close", ltp))
                        vwap_p = float(q.get("avg_cost", ltp) or ltp)
                        chg    = float(q.get("change", 0.0))
                        vol    = int(q.get("last_volume", 0) or q.get("volume", 0) or 0)
                        oi     = int(q.get("open_int", 0) or q.get("oi", 0) or 0)

                        depth = q.get("depth", {})
                        bids = depth.get("buy", []) if isinstance(depth, dict) else []
                        asks = depth.get("sell", []) if isinstance(depth, dict) else []

                        b_px = [float(bids[i].get("price", 0.0)) if i < len(bids) else 0.0 for i in range(5)]
                        b_qt = [int(bids[i].get("quantity", 0)) if i < len(bids) else 0 for i in range(5)]
                        a_px = [float(asks[i].get("price", 0.0)) if i < len(asks) else 0.0 for i in range(5)]
                        a_qt = [int(asks[i].get("quantity", 0)) if i < len(asks) else 0 for i in range(5)]

                        # Aggressor inference
                        prev = self.prev_state.get(tok)
                        if prev:
                            vol_delta = vol - prev["vol"]
                            if vol_delta > 0:
                                side = "INSIDE"
                                if ltp >= prev["a1_px"] and prev["a1_px"] > 0:
                                    side = "BUY_AGGRESSOR"
                                elif ltp <= prev["b1_px"] and prev["b1_px"] > 0:
                                    side = "SELL_AGGRESSOR"
                                elif ltp > prev["ltp"]:
                                    side = "BUY"
                                elif ltp < prev["ltp"]:
                                    side = "SELL"

                                tape_buffers[a_dir].append([
                                    now_str, meta["asset"], meta["type"], meta["strike"], meta["trd_symbol"],
                                    ltp, vol_delta, side, vol, oi
                                ])
                                self.total_trades_inferred += 1

                        self.prev_state[tok] = {
                            "ltp": ltp, "vol": vol, "b1_px": b_px[0], "a1_px": a_px[0]
                        }

                        # 1-min bar
                        bar_key = (minute_str, tok)
                        if bar_key not in self.minute_bars:
                            self.minute_bars[bar_key] = {
                                "minute": minute_str, "asset": meta["asset"], "asset_dir": a_dir,
                                "type": meta["type"], "strike": meta["strike"], "trd_symbol": meta["trd_symbol"],
                                "open": ltp, "high": ltp, "low": ltp, "close": ltp,
                                "v_start": vol, "v_end": vol, "tick_cnt": 1
                            }
                        else:
                            b = self.minute_bars[bar_key]
                            b["high"] = max(b["high"], ltp)
                            b["low"]  = min(b["low"], ltp)
                            b["close"]= ltp
                            b["v_end"] = vol
                            b["tick_cnt"] += 1

                        tick_buffers[a_dir].append([
                            now_str, meta["asset"], meta["type"], meta["strike"], meta["trd_symbol"],
                            ltp, chg, open_p, high_p, low_p, close_p, vwap_p, vol, oi,
                            b_px[0], b_qt[0], b_px[1], b_qt[1], b_px[2], b_qt[2], b_px[3], b_qt[3], b_px[4], b_qt[4],
                            a_px[0], a_qt[0], a_px[1], a_qt[1], a_px[2], a_qt[2], a_px[3], a_qt[3], a_px[4], a_qt[4]
                        ])

                except Exception as ex:
                    err_msg = str(getattr(ex, 'message', '') or getattr(ex, 'reason', '') or repr(ex))
                    print(f"[-] Quote warning: {err_msg[:120]}")
                    time.sleep(1)

            # Write batches to files
            for a_dir in PRIMARY_ASSETS:
                t_buf = tick_buffers[a_dir]
                if t_buf:
                    ticks_csv = asset_paths[a_dir][0]
                    with open(ticks_csv, "a", newline="", encoding="utf-8") as f:
                        csv.writer(f).writerows(t_buf)
                    self.total_ticks_recorded += len(t_buf)

                tp_buf = tape_buffers[a_dir]
                if tp_buf:
                    tape_csv = asset_paths[a_dir][1]
                    with open(tape_csv, "a", newline="", encoding="utf-8") as f:
                        csv.writer(f).writerows(tp_buf)

            # Flush finalized 1-minute bars
            keys_to_flush = [k for k in self.minute_bars if k[0] < minute_str]
            if keys_to_flush:
                asset_bar_rows = {a: [] for a in PRIMARY_ASSETS}
                for k in keys_to_flush:
                    b = self.minute_bars.pop(k)
                    a_dir = b.get("asset_dir", "other")
                    if a_dir in asset_bar_rows:
                        asset_bar_rows[a_dir].append([
                            b["minute"], b["asset"], b["type"], b["strike"], b["trd_symbol"],
                            b["open"], b["high"], b["low"], b["close"],
                            max(0, b["v_end"] - b["v_start"]), b["tick_cnt"]
                        ])

                for a_dir in PRIMARY_ASSETS:
                    rows = asset_bar_rows[a_dir]
                    if rows:
                        bars_csv = asset_paths[a_dir][2]
                        with open(bars_csv, "a", newline="", encoding="utf-8") as f:
                            csv.writer(f).writerows(rows)

            elapsed = time.perf_counter() - t_cycle_start
            time.sleep(max(0, self.poll_interval - elapsed))

    def flush_all_pending_bars(self):
        """Flushes all unwritten minute bars to disk upon shutdown."""
        current_date = get_ist_now().strftime("%Y-%m-%d")
        asset_paths = self.get_all_file_paths(current_date)
        asset_bar_rows = {a: [] for a in PRIMARY_ASSETS}

        for k, b in self.minute_bars.items():
            a_dir = b.get("asset_dir", "other")
            if a_dir in asset_bar_rows:
                asset_bar_rows[a_dir].append([
                    b["minute"], b["asset"], b["type"], b["strike"], b["trd_symbol"],
                    b["open"], b["high"], b["low"], b["close"],
                    max(0, b["v_end"] - b["v_start"]), b["tick_cnt"]
                ])

        for a_dir in PRIMARY_ASSETS:
            rows = asset_bar_rows[a_dir]
            if rows:
                bars_csv = asset_paths[a_dir][2]
                with open(bars_csv, "a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerows(rows)
        self.minute_bars.clear()
        print("[+] Finalized all 1-minute bars to disk.")

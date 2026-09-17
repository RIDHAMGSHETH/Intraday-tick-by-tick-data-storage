"""
===============================================================================
UNIVERSAL OPTIONS CHAIN & FUTURE RESOLVER (NSE, BSE & MCX)
===============================================================================
Accurately resolves:
- Active Near Futures
- Nearest Unexpired Expiry Date
- ATM Strike based on Live Market Price
- Strikelist (+- radius) with exact Kotak tokens for CE & PE

Covers:
1. NIFTY 50 (NSE)
2. SENSEX (BSE)
3. CRUDE OIL (MCX)
4. CRUDE OIL MINI (MCX)
5. NATURAL GAS (MCX)
6. NATURAL GAS MINI (MCX)
===============================================================================
"""

import os
import re
import pandas as pd
from datetime import datetime

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
NSE_FO_PATH = os.path.join(ENGINE_DIR, "today_nse_fo.csv")
MCX_FO_PATH = os.path.join(ENGINE_DIR, "today_mcx_fo.csv")
BSE_FO_PATH = os.path.join(ENGINE_DIR, "today_bse_fo.csv")

ASSET_SPECS = {
    "NIFTY": {
        "market": "NSE",
        "symbol_name": "NIFTY",
        "spot_symbol": "Nifty 50",
        "spot_seg": "nse_cm",
        "exchange_seg": "nse_fo",
        "fut_inst": "FUTIDX",
        "opt_inst": "OPTIDX",
        "strike_step": 50,
        "default_radius": 15
    },
    "SENSEX": {
        "market": "BSE",
        "symbol_name": "SENSEX",
        "spot_symbol": "SENSEX",
        "spot_seg": "bse_cm",
        "exchange_seg": "bse_fo",
        "fut_inst": "IF",
        "opt_inst": "IO",
        "strike_step": 100,
        "default_radius": 15
    },
    "CRUDEOIL": {
        "market": "MCX",
        "symbol_name": "CRUDEOIL",
        "exchange_seg": "mcx_fo",
        "fut_inst": "FUTCOM",
        "opt_inst": "OPTFUT",
        "strike_step": 50,
        "default_radius": 15
    },
    "CRUDEOILM": {
        "market": "MCX",
        "symbol_name": "CRUDEOILM",
        "exchange_seg": "mcx_fo",
        "fut_inst": "FUTCOM",
        "opt_inst": "OPTFUT",
        "strike_step": 50,
        "default_radius": 15
    },
    "NATURALGAS": {
        "market": "MCX",
        "symbol_name": "NATURALGAS",
        "exchange_seg": "mcx_fo",
        "fut_inst": "FUTCOM",
        "opt_inst": "OPTFUT",
        "strike_step": 5,
        "default_radius": 15
    },
    "NATGASMINI": {
        "market": "MCX",
        "symbol_name": "NATGASMINI",
        "exchange_seg": "mcx_fo",
        "fut_inst": "FUTCOM",
        "opt_inst": "OPTFUT",
        "strike_step": 5,
        "default_radius": 15
    }
}

class UniversalOptionsChainResolver:
    def _ensure_scrip_files(self):
        """Downloads today's master scrip files if missing or from a previous day."""
        import urllib.request
        today_str = datetime.now().strftime("%Y-%m-%d")
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        file_map = {
            NSE_FO_PATH: f"https://lapi.kotaksecurities.com/wso2-scripmaster/v1/prod/{today_str}/transformed/nse_fo.csv",
            MCX_FO_PATH: f"https://lapi.kotaksecurities.com/wso2-scripmaster/v1/prod/{today_str}/transformed/mcx_fo.csv",
            BSE_FO_PATH: f"https://lapi.kotaksecurities.com/wso2-scripmaster/v1/prod/{today_str}/transformed/bse_fo.csv"
        }
        for local_p, remote_url in file_map.items():
            need_download = False
            if not os.path.exists(local_p):
                need_download = True
            else:
                mtime = datetime.fromtimestamp(os.path.getmtime(local_p)).strftime("%Y-%m-%d")
                if mtime != today_str:
                    need_download = True

            if need_download:
                try:
                    print(f"[*] Downloading updated master scrip from Kotak: {os.path.basename(local_p)}...")
                    req = urllib.request.Request(remote_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=30) as resp, open(local_p, 'wb') as out_f:
                        out_f.write(resp.read())
                    print(f"[+] Downloaded {os.path.basename(local_p)} successfully.")
                except Exception as ex:
                    print(f"[-] Warning: Failed to download {os.path.basename(local_p)}: {ex}")

    def __init__(self):
        self._ensure_scrip_files()
        self.nse_df = pd.read_csv(NSE_FO_PATH, low_memory=False)
        self.nse_df.columns = [c.strip().rstrip(';') for c in self.nse_df.columns]

        self.mcx_df = pd.read_csv(MCX_FO_PATH, low_memory=False)
        self.mcx_df.columns = [c.strip().rstrip(';') for c in self.mcx_df.columns]

        if os.path.exists(BSE_FO_PATH):
            self.bse_df = pd.read_csv(BSE_FO_PATH, low_memory=False)
            self.bse_df.columns = [c.strip().rstrip(';') for c in self.bse_df.columns]
        else:
            self.bse_df = pd.DataFrame()

    def _extract_strike(self, symbol_name, trd_symbol, raw_strike):
        """Cleanly extracts the true strike price."""
        ts = str(trd_symbol).strip()
        raw_val = float(raw_strike)

        # 1. Natural Gas: e.g. NATURALGAS23SEP26270CE -> 270.0
        if "NAT" in symbol_name:
            m = re.match(r'^[A-Z]+(?:\d{2}[A-Z]{3}\d{2})?(\d+)(?:CE|PE)$', ts)
            if m:
                return float(m.group(1))
            return raw_val / 100.0 if raw_val > 5000 else raw_val

        # 2. Crude Oil: e.g. 950000 -> 9500.0
        if "CRUDE" in symbol_name:
            if raw_val > 50000:
                return raw_val / 100.0
            return raw_val

        # 3. SENSEX: e.g. 8330000.0 -> 83300.0
        if symbol_name == "SENSEX":
            if raw_val > 100000:
                return raw_val / 100.0
            return raw_val

        # 4. NSE Indices: e.g. NIFTY2691523400CE -> 23400.0
        if raw_val > 500000:
            return raw_val / 100.0
        elif raw_val > 5000:
            m = re.search(r'(\d{4,5})(CE|PE)$', ts)
            if m:
                return float(m.group(1))
            return raw_val / 100.0
        return raw_val

    def resolve_asset_options(self, asset_key, reference_price=None, radius=None):
        spec = ASSET_SPECS.get(asset_key)
        if not spec:
            raise ValueError(f"Unknown asset: {asset_key}")

        if spec["market"] == "NSE":
            df = self.nse_df
        elif spec["market"] == "BSE":
            df = self.bse_df
        else:
            df = self.mcx_df

        sym_name = spec["symbol_name"]
        radius = radius or spec["default_radius"]
        now_ts = datetime.now().timestamp()

        # 1. Resolve Active Future
        fut_sub = df[(df['pSymbolName'].astype(str) == sym_name) & (df['pInstType'].astype(str) == spec["fut_inst"])].copy()
        fut_exp_col = 'lExpiryDate' if 'lExpiryDate' in fut_sub.columns else 'pExpiryDate'
        fut_sub['exp_ts'] = pd.to_numeric(fut_sub[fut_exp_col], errors='coerce')
        fut_unexp = fut_sub[fut_sub['exp_ts'] > now_ts].sort_values('exp_ts')
        if fut_unexp.empty:
            fut_unexp = fut_sub.sort_values('exp_ts')
        fut_row = fut_unexp.iloc[0]
        
        fut_contract = {
            "token": str(fut_row['pSymbol']),
            "trd_symbol": str(fut_row['pTrdSymbol']),
            "expiry": str(fut_row[fut_exp_col]),
            "lot_size": int(fut_row.get('lLotSize', 1))
        }

        # 2. Resolve Active Options Expiry
        opt_sub = df[(df['pSymbolName'].astype(str) == sym_name) & (df['pInstType'].astype(str) == spec["opt_inst"])].copy()
        if opt_sub.empty:
            return {"future": fut_contract, "options": []}

        opt_exp_col = 'lExpiryDate' if 'lExpiryDate' in opt_sub.columns else 'pExpiryDate'
        opt_sub['exp_ts'] = pd.to_numeric(opt_sub[opt_exp_col], errors='coerce')
        
        # Filter unexpired
        unexpired_exps = sorted([e for e in opt_sub['exp_ts'].dropna().unique() if e > now_ts])
        if not unexpired_exps:
            unexpired_exps = sorted(opt_sub['exp_ts'].dropna().unique())
        
        nearest_exp = unexpired_exps[0]
        near_opts = opt_sub[opt_sub['exp_ts'] == nearest_exp].copy()

        # Clean strikes
        near_opts['CleanStrike'] = [
            self._extract_strike(sym_name, row['pTrdSymbol'], row['dStrikePrice'])
            for _, row in near_opts.iterrows()
        ]

        all_strikes = sorted(near_opts['CleanStrike'].dropna().unique())
        if not all_strikes:
            return {"future": fut_contract, "options": []}

        # Select ATM strike
        if reference_price and reference_price > 0:
            atm_strike = min(all_strikes, key=lambda s: abs(s - reference_price))
        else:
            atm_strike = all_strikes[len(all_strikes) // 2]

        atm_idx = all_strikes.index(atm_strike)
        start_idx = max(0, atm_idx - radius)
        end_idx = min(len(all_strikes), atm_idx + radius + 1)
        selected_strikes = all_strikes[start_idx:end_idx]

        options_list = []
        for s in selected_strikes:
            stk_opts = near_opts[near_opts['CleanStrike'] == s]
            ce_row = stk_opts[stk_opts['pOptionType'].astype(str).str.upper() == 'CE']
            pe_row = stk_opts[stk_opts['pOptionType'].astype(str).str.upper() == 'PE']

            if not ce_row.empty:
                r = ce_row.iloc[0]
                options_list.append({
                    "strike": float(s),
                    "type": "CE",
                    "token": str(r['pSymbol']),
                    "trd_symbol": str(r['pTrdSymbol']),
                    "segment": spec["exchange_seg"]
                })
            if not pe_row.empty:
                r = pe_row.iloc[0]
                options_list.append({
                    "strike": float(s),
                    "type": "PE",
                    "token": str(r['pSymbol']),
                    "trd_symbol": str(r['pTrdSymbol']),
                    "segment": spec["exchange_seg"]
                })

        return {
            "asset": asset_key,
            "future": fut_contract,
            "expiry": str(nearest_exp),
            "atm_strike": atm_strike,
            "options": options_list
        }

if __name__ == "__main__":
    res = UniversalOptionsChainResolver()
    sample_prices = {
        "NIFTY": 23485.0,
        "SENSEX": 74375.0,
        "CRUDEOIL": 9527.0,
        "CRUDEOILM": 9525.0,
        "NATURALGAS": 270.0,
        "NATGASMINI": 270.0
    }
    for asset, px in sample_prices.items():
        chain = res.resolve_asset_options(asset, reference_price=px, radius=4)
        print(f"[{asset:<10}] Fut: {chain['future']['trd_symbol']:<20} ATM: {chain['atm_strike']:<8} Options: {len(chain['options'])}")
        if chain['options']:
            print("  Strikes:", sorted(list(set([o['strike'] for o in chain['options']]))))

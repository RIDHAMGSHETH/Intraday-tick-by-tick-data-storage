# Intraday Tick-by-Tick & 1-Minute Bar Data Storage

Automated high-frequency market data recorder powered by Kotak Neo API.

## Tracked Instruments

### 1. Equity Index Derivatives (NSE & BSE)
- **NIFTY 50**: Spot Index, Current-Month Futures (`NIFTY26SEPFUT`) & ATM Options (CE/PE)
- **SENSEX**: Spot Index, Current-Month Futures (`SENSEX26SEPFUT`) & ATM Options (CE/PE) on BSE FO

### 2. MCX Commodity Derivatives
- **CRUDE OIL**: Current-Month 100-BBL Futures (`CRUDEOIL21SEP26FUT`) & ATM Options
- **CRUDE OIL MINI**: Current-Month 10-BBL Futures (`CRUDEOILM21SEP26FUT`) & ATM Options
- **NATURAL GAS**: Current-Month 1250-mmBtu Futures (`NATURALGAS25SEP26FUT`) & ATM Options
- **NATURAL GAS MINI**: Current-Month 250-mmBtu Futures (`NATGASMINI25SEP26FUT`) & ATM Options

---

## Directory Structure
```
data/
├── nifty/
│   └── YYYY-MM-DD/
│       ├── nifty_ticks_YYYY-MM-DD.csv       # Ticks with 5-depth (Parquet on Hugging Face)
│       ├── nifty_tape_YYYY-MM-DD.csv        # Aggressor trade tape
│       └── nifty_1min_bars_YYYY-MM-DD.csv   # 1-minute OHLCV bars
├── sensex/
│   └── YYYY-MM-DD/
│       ├── sensex_ticks_YYYY-MM-DD.csv
│       ├── sensex_tape_YYYY-MM-DD.csv
│       └── sensex_1min_bars_YYYY-MM-DD.csv
├── crudeoil/
│   └── YYYY-MM-DD/
│       ├── crudeoil_ticks_YYYY-MM-DD.csv
│       ├── crudeoil_tape_YYYY-MM-DD.csv
│       └── crudeoil_1min_bars_YYYY-MM-DD.csv
├── naturalgas/
│   └── YYYY-MM-DD/
│       ├── naturalgas_ticks_YYYY-MM-DD.csv
│       ├── naturalgas_tape_YYYY-MM-DD.csv
│       └── naturalgas_1min_bars_YYYY-MM-DD.csv
└── old_data/                                # Historical legacy recordings
    ├── 2026-09-13/
    ├── 2026-09-14/
    └── 2026-09-15/
```

## Data Schema (Tick-by-Tick)
| Column | Type | Description |
|---|---|---|
| `timestamp` | String | ISO Timestamp with millisecond precision |
| `symbol` | String | Asset Name (e.g., `CRUDEOIL`, `NIFTY`) |
| `instrument_type` | String | `SPOT` or `FUT` |
| `trading_symbol` | String | Official exchange trading symbol |
| `ltp` | Float | Last traded price |
| `change` | Float | Net price change |
| `open`, `high`, `low`, `close` | Float | Session OHLC |
| `volume`, `oi` | Int | Cumulative volume & open interest |
| `bid1_px`, `bid1_qty` | Float / Int | Best bid price and quantity |
| `ask1_px`, `ask1_qty` | Float / Int | Best ask price and quantity |
| `aggressor_side` | String | `BUY`, `SELL`, or `INSIDE` |
| `trade_qty` | Int | Incremental traded volume |

---

## Automated Sync
This repository automatically synchronizes with daily recording engines running on the trading workstation.

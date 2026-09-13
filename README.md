# Intraday Tick-by-Tick & 1-Minute Bar Data Storage

Automated high-frequency market data recorder powered by Kotak Neo API.

## Tracked Instruments

### 1. NSE Equity Index Derivatives
- **NIFTY 50**: Spot Index & Current-Month Futures (`NIFTY26SEPFUT`)
- **BANK NIFTY**: Spot Index & Current-Month Futures (`BANKNIFTY26SEPFUT`)
- **FIN NIFTY**: Spot Index & Current-Month Futures (`FINNIFTY26SEPFUT`)

### 2. MCX Commodity Derivatives
- **CRUDE OIL**: Current-Month 100-BBL Futures (`CRUDEOIL21SEP26FUT`)
- **CRUDE OIL MINI**: Current-Month 10-BBL Futures (`CRUDEOILM21SEP26FUT`)
- **NATURAL GAS**: Current-Month 1250-mmBtu Futures (`NATURALGAS25SEP26FUT`)
- **NATURAL GAS MINI**: Current-Month 250-mmBtu Futures (`NATGASMINI25SEP26FUT`)

---

## Directory Structure
```
data/
└── YYYY-MM-DD/
    ├── all_assets_ticks_YYYY-MM-DD.csv      # Tick-by-tick aggressor & level 1 depth
    └── all_assets_1min_bars_YYYY-MM-DD.csv   # Aggregated 1-minute OHLCV bars
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

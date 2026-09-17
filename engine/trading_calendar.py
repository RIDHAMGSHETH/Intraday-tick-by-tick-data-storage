"""
===============================================================================
OFFICIAL 2026 TRADING HOLIDAYS & MARKET HOURS MANAGER
===============================================================================
Maintains accurate schedules for:
1. NSE Equity / F&O (NIFTY, BANKNIFTY, FINNIFTY): 09:15 - 15:30 IST
2. MCX Commodities (CRUDE OIL, CRUDE MINI, NATURAL GAS, NATGAS MINI):
   - Regular Days: 09:00 - 23:30 / 23:55 IST
   - Evening-Only Days (e.g. Ganesh Chaturthi, Holi): 17:00 - 23:30 IST
   - Full Holidays: Closed
3. Weekends: Saturday & Sunday Closed
===============================================================================
"""

import os
import json
from datetime import datetime, date, time as dtime

# Official NSE & MCX Trading Holidays for 2026
# Source: National Stock Exchange of India & MCX Holiday Master
HOLIDAYS_2026 = {
    "2026-01-15": {"name": "Municipal Corporation Election - Maharashtra", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": True},
    "2026-01-26": {"name": "Republic Day", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": False},
    "2026-02-15": {"name": "Mahashivratri", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": False},
    "2026-03-03": {"name": "Holi", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": True},
    "2026-03-21": {"name": "Id-Ul-Fitr (Ramadan Eid)", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": False},
    "2026-03-26": {"name": "Shri Ram Navami", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": True},
    "2026-03-31": {"name": "Shri Mahavir Jayanti", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": True},
    "2026-04-03": {"name": "Good Friday", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": False},
    "2026-04-14": {"name": "Dr. Baba Saheb Ambedkar Jayanti", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": True},
    "2026-05-01": {"name": "Maharashtra Day", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": True},
    "2026-05-28": {"name": "Bakri Id", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": True},
    "2026-06-26": {"name": "Muharram", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": True},
    "2026-08-15": {"name": "Independence Day", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": False},
    "2026-09-14": {"name": "Ganesh Chaturthi", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": True},
    "2026-10-02": {"name": "Mahatma Gandhi Jayanti", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": False},
    "2026-10-20": {"name": "Dussehra", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": True},
    "2026-11-08": {"name": "Diwali Laxmi Pujan (Muhurat Trading only)", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": False},
    "2026-11-10": {"name": "Diwali-Balipratipada", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": True},
    "2026-11-24": {"name": "Prakash Gurpurb Sri Guru Nanak Dev", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": True},
    "2026-12-25": {"name": "Christmas", "nse_closed": True, "mcx_morning_closed": True, "mcx_evening_open": False},
}

def is_weekend(dt=None):
    """Returns True if Saturday (5) or Sunday (6)."""
    if dt is None:
        dt = datetime.now()
    return dt.weekday() in (5, 6)

def get_market_status(dt=None):
    """
    Returns the market trading state for both NSE and MCX at given timestamp.
    Returns:
      {
         'is_trading_day': bool,
         'nse_open': bool,
         'mcx_open': bool,
         'reason': str
      }
    """
    if dt is None:
        dt = datetime.now()

    date_str = dt.strftime("%Y-%m-%d")
    cur_time = dt.time()

    # 1. Weekend Check
    if dt.weekday() == 5:
        return {'is_trading_day': False, 'nse_open': False, 'mcx_open': False, 'reason': 'Saturday (Weekend)'}
    if dt.weekday() == 6:
        return {'is_trading_day': False, 'nse_open': False, 'mcx_open': False, 'reason': 'Sunday (Weekend)'}

    # 2. Holiday Check
    holiday_info = HOLIDAYS_2026.get(date_str)
    
    nse_trading_active = False
    mcx_trading_active = False
    reasons = []

    # NSE Schedule: 09:15 to 15:30
    if holiday_info and holiday_info.get("nse_closed"):
        reasons.append(f"NSE Closed: {holiday_info['name']}")
    else:
        if dtime(9, 15) <= cur_time <= dtime(15, 30):
            nse_trading_active = True
        elif cur_time < dtime(9, 15):
            reasons.append("NSE Pre-market (Opens 09:15)")
        else:
            reasons.append("NSE Post-market (Closed 15:30)")

    # MCX Schedule: 09:00 to 23:30 (or 17:00 to 23:30 on evening-only days)
    if holiday_info and holiday_info.get("mcx_morning_closed") and not holiday_info.get("mcx_evening_open"):
        reasons.append(f"MCX Full Holiday: {holiday_info['name']}")
    elif holiday_info and holiday_info.get("mcx_morning_closed") and holiday_info.get("mcx_evening_open"):
        # Evening only session: 17:00 to 23:30
        if dtime(17, 0) <= cur_time <= dtime(23, 30):
            mcx_trading_active = True
        elif cur_time < dtime(17, 0):
            reasons.append(f"MCX Morning Closed ({holiday_info['name']}), Opens 17:00")
        else:
            reasons.append("MCX Closed for the night (23:30)")
    else:
        # Standard MCX Day: 09:00 to 23:30
        if dtime(9, 0) <= cur_time <= dtime(23, 30):
            mcx_trading_active = True
        elif cur_time < dtime(9, 0):
            reasons.append("MCX Opens at 09:00")
        else:
            reasons.append("MCX Closed for the night (23:30)")

    is_active = nse_trading_active or mcx_trading_active

    return {
        'date': date_str,
        'time': cur_time.strftime("%H:%M:%S"),
        'is_trading_day': (holiday_info is None or not (holiday_info.get("nse_closed") and not holiday_info.get("mcx_evening_open"))),
        'nse_open': nse_trading_active,
        'mcx_open': mcx_trading_active,
        'reason': " | ".join(reasons) if reasons else "Market Active"
    }

if __name__ == "__main__":
    status = get_market_status()
    print("Market Status Right Now:")
    for k, v in status.items():
        print(f"  {k}: {v}")

    # Tomorrow check (Ganesh Chaturthi - 2026-09-14)
    tomorrow = datetime(2026, 9, 14, 11, 0)
    print(f"\nStatus on Tomorrow ({tomorrow}):")
    st = get_market_status(tomorrow)
    for k, v in st.items():
        print(f"  {k}: {v}")

    tomorrow_evening = datetime(2026, 9, 14, 18, 0)
    print(f"\nStatus on Tomorrow Evening ({tomorrow_evening}):")
    st = get_market_status(tomorrow_evening)
    for k, v in st.items():
        print(f"  {k}: {v}")

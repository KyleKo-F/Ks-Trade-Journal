import sqlite3
import threading
import requests
from tradingview_ta import TA_Handler, Interval
import database as db

# Mapping of pair symbols to TradingView specifications
TV_SYMBOL_MAP = {
    "EUR/USD": ("EURUSD", "FX", "forex"),
    "GBP/USD": ("GBPUSD", "FX", "forex"),
    "USD/JPY": ("USDJPY", "FX", "forex"),
    "USD/CHF": ("USDCHF", "FX", "forex"),
    "AUD/USD": ("AUDUSD", "FX", "forex"),
    "USD/CAD": ("USDCAD", "FX", "forex"),
    "NZD/USD": ("NZDUSD", "FX", "forex"),
    "EUR/GBP": ("EURGBP", "FX", "forex"),
    "EUR/JPY": ("EURJPY", "FX", "forex"),
    "EUR/CHF": ("EURCHF", "FX", "forex"),
    "EUR/CAD": ("EURCAD", "FX", "forex"),
    "EUR/AUD": ("EURAUD", "FX", "forex"),
    "EUR/NZD": ("EURNZD", "FX", "forex"),
    "GBP/JPY": ("GBPJPY", "FX", "forex"),
    "GBP/CHF": ("GBPCHF", "FX", "forex"),
    "GBP/CAD": ("GBPCAD", "FX", "forex"),
    "GBP/AUD": ("GBPAUD", "FX", "forex"),
    "GBP/NZD": ("GBPNZD", "FX", "forex"),
    "AUD/JPY": ("AUDJPY", "FX", "forex"),
    "AUD/NZD": ("AUDNZD", "FX", "forex"),
    "AUD/CAD": ("AUDCAD", "FX", "forex"),
    "AUD/CHF": ("AUDCHF", "FX", "forex"),
    "NZD/JPY": ("NZDJPY", "FX", "forex"),
    "NZD/CAD": ("NZDCAD", "FX", "forex"),
    "NZD/CHF": ("NZDCHF", "FX", "forex"),
    "CAD/JPY": ("CADJPY", "FX", "forex"),
    "CAD/CHF": ("CADCHF", "FX", "forex"),
    "CHF/JPY": ("CHFJPY", "FX", "forex"),
    "XAU/USD (Gold)": ("GOLD", "TVC", "cfd"),
    "BTC/USD (Crypto)": ("BTCUSD", "BITSTAMP", "crypto"),
    "ETH/USD (Crypto)": ("ETHUSD", "BITSTAMP", "crypto")
}

def get_tradingview_prices(pair_name):
    """Fetches high, low, and close prices for a given pair from TradingView."""
    map_info = TV_SYMBOL_MAP.get(pair_name)
    if not map_info:
        # Fallback search if exact key has visual labels (e.g. "EUR/USD")
        clean_pair = pair_name.split()[0].replace(" ", "")
        map_info = TV_SYMBOL_MAP.get(clean_pair)
        if not map_info:
            return None, None, None

    tv_symbol, tv_exchange, tv_screener = map_info

    # Method 1: Using tradingview_ta library
    try:
        handler = TA_Handler(
            symbol=tv_symbol,
            exchange=tv_exchange,
            screener=tv_screener,
            interval=Interval.INTERVAL_1_MINUTE
        )
        analysis = handler.get_analysis()
        high = analysis.indicators.get("high")
        low = analysis.indicators.get("low")
        close = analysis.indicators.get("close")
        if close is not None:
            return high or close, low or close, close
    except Exception:
        pass

    # Method 2: Fallback to TradingView direct API endpoint
    try:
        url = f"https://scanner.tradingview.com/{tv_screener}/scan"
        payload = {
            "symbols": {"tickers": [f"{tv_exchange}:{tv_symbol}"]},
            "columns": ["high", "low", "close"]
        }
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data") and len(data["data"]) > 0:
                vals = data["data"][0]["d"]
                return vals[0], vals[1], vals[2]
    except Exception as e:
        print(f"TradingView fetch error for {pair_name}: {e}")

    return None, None, None

def get_pip_multiplier(pair):
    """Returns pip scaling factor based on asset class."""
    pair_u = pair.upper()
    if "JPY" in pair_u:
        return 100.0
    elif "XAU" in pair_u or "GOLD" in pair_u:
        return 10.0
    elif "BTC" in pair_u or "ETH" in pair_u:
        return 1.0
    return 10000.0

def check_open_trades():
    """Scans all OPEN trades and checks if TradingView live price hit TP or SL."""
    conn = sqlite3.connect("trading_journal.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, pair, direction, entry_price, stop_loss, take_profit FROM trades WHERE status = 'OPEN'")
    open_trades = cursor.fetchall()
    
    if not open_trades:
        conn.close()
        return

    for trade in open_trades:
        trade_id, pair, direction, entry, sl, tp = trade
        
        try:
            entry = float(entry)
            sl = float(sl)
            tp = float(tp)
        except (ValueError, TypeError):
            continue

        high, low, current_price = get_tradingview_prices(pair)
        if current_price is None:
            continue

        hit_status = None
        
        # Check Long positions
        if direction.upper() in ["BUY", "LONG"]:
            if high >= tp:
                hit_status = "WIN"
            elif low <= sl:
                hit_status = "LOSS"
                
        # Check Short positions
        elif direction.upper() in ["SELL", "SHORT"]:
            if low <= tp:
                hit_status = "WIN"
            elif high >= sl:
                hit_status = "LOSS"

        if hit_status:
            multiplier = get_pip_multiplier(pair)
            pnl_pips = (tp - entry if hit_status == "WIN" else sl - entry) * multiplier
            if direction.upper() in ["SELL", "SHORT"]:
                pnl_pips = -pnl_pips

            cursor.execute(
                "UPDATE trades SET status = ?, pnl_pips = ? WHERE id = ?",
                (hit_status, round(pnl_pips, 1), trade_id)
            )
            print(f"Trade #{trade_id} ({pair}) closed as {hit_status} via TradingView price update!")

    conn.commit()
    conn.close()
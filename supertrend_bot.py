import streamlit as st
st.set_page_config(page_title="Supertrend Trading Bot", layout="wide")  # ✅ Must come first

import pandas as pd
import requests
import time
from datetime import datetime, timedelta
import hmac
from hashlib import sha256

# === CONFIG ===
SYMBOL = "ethusdt"
INTERVAL = "1m"
TRADE_AMOUNT_USDT = 10
LEVERAGE = 10
API_URL = "https://open-api.bingx.com"
API_KEY = st.text_input("API Key", type="password")
SECRET_KEY = st.text_input("Secret Key", type="password")

# === STATE ===
current_position = None
entry_price = None
stop_loss = None
wait_confirm_time = None
waiting_side = None
log_messages = []

# === UTILS ===
def parse_params(params):
    sorted_keys = sorted(params)
    base = "&".join(f"{key}={params[key]}" for key in sorted_keys)
    timestamp = f"timestamp={int(time.time() * 1000)}"
    return f"{base}&{timestamp}" if base else timestamp

def log(msg):
    global log_messages
    timestamp = datetime.now().strftime('%H:%M:%S')
    full_msg = f"[{timestamp}] {msg}"
    log_messages.insert(0, full_msg)

def get_klines(symbol, interval, limit=100):
    # No signature required for public market data
    url = f"https://api-swap-rest.bingx.com/api/v1/market/kline"
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit
    }
    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        if 'data' not in data:
            log(f"⚠️ API Error: {data}")
            return None
        df = pd.DataFrame(data['data'])
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)
        return df
    except Exception as e:
        log(f"⚠️ No data returned from API. Skipping strategy run.")
        return None

def compute_supertrend(df, length, multiplier):
    hl2 = (df['high'] + df['low']) / 2
    tr1 = df['high'] - df['low']
    tr2 = abs(df['high'] - df['close'].shift())
    tr3 = abs(df['low'] - df['close'].shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(length).mean()

    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)

    final_upperband = upperband.copy()
    final_lowerband = lowerband.copy()
    supertrend = [True] * len(df)

    for i in range(1, len(df)):
        if df['close'][i] > final_upperband[i-1]:
            supertrend[i] = True
        elif df['close'][i] < final_lowerband[i-1]:
            supertrend[i] = False
        else:
            supertrend[i] = supertrend[i-1]
            if supertrend[i] and final_lowerband[i] < final_lowerband[i-1]:
                final_lowerband[i] = final_lowerband[i-1]
            if not supertrend[i] and final_upperband[i] > final_upperband[i-1]:
                final_upperband[i] = final_upperband[i-1]

    trend = ['BUY' if val else 'SELL' for val in supertrend]
    return pd.DataFrame({
        'upperband': final_upperband,
        'lowerband': final_lowerband,
        'trend': trend
    })

def get_latest_signals():
    df = get_klines(SYMBOL, INTERVAL)
    if df is None:
        return None
    st1 = compute_supertrend(df, 14, 2)
    st2 = compute_supertrend(df, 21, 1)

    df['st1_signal'] = st1['trend']
    df['st1_lb'] = st1['lowerband']
    df['st1_ub'] = st1['upperband']
    df['st2_signal'] = st2['trend']
    df['st2_lb'] = st2['lowerband']
    df['st2_ub'] = st2['upperband']
    return df

def enter_trade(side, price, sl):
    global current_position, entry_price, stop_loss
    current_position = side
    entry_price = price
    stop_loss = sl
    log(f"🟢 ENTER {side} @ {price:.2f}, SL: {sl:.2f}")

def close_trade(price):
    global current_position, entry_price
    if current_position:
        profit = (price - entry_price) if current_position == 'LONG' else (entry_price - price)
        log(f"🔴 EXIT {current_position} @ {price:.2f} | PnL: {profit:.2f} USDT")
    current_position = None

def strategy():
    global current_position, wait_confirm_time, waiting_side, stop_loss

    df = get_latest_signals()
    if df is None:
        return

    latest = df.iloc[-1]
    st1_sig = latest['st1_signal']
    st2_sig = latest['st2_signal']
    price = latest['close']

    if current_position:
        if price <= stop_loss and current_position == 'LONG':
            log(f"❌ SL hit on LONG @ {price:.2f}")
            close_trade(price)
        elif price >= stop_loss and current_position == 'SHORT':
            log(f"❌ SL hit on SHORT @ {price:.2f}")
            close_trade(price)
        elif (st1_sig != current_position or st2_sig != current_position):
            log(f"⚠️ Signal flip detected — closing {current_position}")
            close_trade(price)
        return

    now = datetime.now()

    if not wait_confirm_time and st1_sig == st2_sig:
        wait_confirm_time = now + timedelta(minutes=1)
        waiting_side = st1_sig
        log(f"⏳ Signal match: {waiting_side} — waiting 1 min confirmation...")
        return

    if wait_confirm_time and now >= wait_confirm_time:
        if st1_sig == waiting_side and st2_sig == waiting_side:
            if waiting_side == 'BUY':
                sl = latest['st2_lb']
                enter_trade('LONG', price, sl)
            elif waiting_side == 'SELL':
                sl = latest['st2_ub']
                enter_trade('SHORT', price, sl)
        else:
            log(f"❌ Signal mismatch after 1 min — skipping trade")
        wait_confirm_time = None
        waiting_side = None

# === STREAMLIT DASHBOARD ===
st.set_page_config(page_title="Supertrend Trading Bot", layout="wide")
st.title("📈 Supertrend BingX Trading Bot")

if st.button("Run Strategy Once"):
    strategy()

st.markdown("### Live Log")
for entry in log_messages[:30]:
    st.text(entry)

st.markdown("---")
st.markdown("*Note: This demo does not place real orders. You can integrate BingX API for live trading.*")

import time
import hmac
import hashlib
import requests
import pandas as pd
from datetime import datetime

# === CONFIG ===
APIKEY = "YOUR_API_KEY"
SECRETKEY = "YOUR_SECRET_KEY"
BASE_URL = "https://open-api.bingx.com"
SYMBOL = "ONDO-USDT"
INTERVAL = "3m"
QUANTITY = 1

# Supertrend params
ST1_LEN = 14
ST1_MUL = 2
ST2_LEN = 21
ST2_MUL = 1

# === STATE ===
position = None  # 'LONG', 'SHORT', or None
entry_price = None
stop_loss = None

# === UTILS ===
def get_signature(secret, payload):
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

def signed_request(method, path, params=None):
    if params is None:
        params = {}
    params['timestamp'] = int(time.time() * 1000)
    query_string = '&'.join([f"{k}={params[k]}" for k in sorted(params)])
    signature = get_signature(SECRETKEY, query_string)
    url = f"{BASE_URL}{path}?{query_string}&signature={signature}"
    headers = {"X-BX-APIKEY": APIKEY}
    response = requests.request(method, url, headers=headers)
    return response.json()

# === CANDLE FETCH ===
def fetch_klines(symbol, interval, limit=100):
    url = f"https://open-api.bingx.com/openApi/linear/v1/market/kline?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url).json()
        if 'data' not in res or not isinstance(res['data'], list):
            print("Unexpected API response:", res)
            return pd.DataFrame()  # Return empty DataFrame to avoid crash
        df = pd.DataFrame(res['data'])
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df.set_index('open_time', inplace=True)
        df = df.astype(float)
        return df
    except Exception as e:
        print(f"[Error] fetch_klines() failed: {e}")
        return pd.DataFrame()

# === SUPERTREND ===
def calculate_supertrend(df, length, multiplier):
    hl2 = (df['high'] + df['low']) / 2
    atr = df['high'].combine(df['low'], max) - df['low'].combine(df['close'].shift(1), min)
    atr = atr.rolling(length).mean()
    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)

    final_upperband = upperband.copy()
    final_lowerband = lowerband.copy()

    supertrend = [True] * len(df)
    for i in range(1, len(df)):
        if df['close'][i] > final_upperband[i - 1]:
            supertrend[i] = True
        elif df['close'][i] < final_lowerband[i - 1]:
            supertrend[i] = False
        else:
            supertrend[i] = supertrend[i - 1]
            if supertrend[i] and lowerband[i] < final_lowerband[i - 1]:
                final_lowerband[i] = final_lowerband[i - 1]
            if not supertrend[i] and upperband[i] > final_upperband[i - 1]:
                final_upperband[i] = final_upperband[i - 1]

    df[f'supertrend_{length}_{multiplier}'] = supertrend
    df[f'upperband_{length}_{multiplier}'] = final_upperband
    df[f'lowerband_{length}_{multiplier}'] = final_lowerband
    return df

# === TRADE FUNCTIONS ===
def place_order(side):
    print(f"\nPlacing {side} order")
    params = {
        "symbol": SYMBOL,
        "side": side,
        "positionSide": "LONG" if side == "BUY" else "SHORT",
        "type": "MARKET",
        "quantity": QUANTITY,
    }
    res = signed_request("POST", "/openApi/swap/v2/trade/order", params)
    print("Order response:", res)
    return res

def close_position():
    global position
    if not position:
        print("No open position to close.")
        return
    side = "SELL" if position == "LONG" else "BUY"
    print(f"Manually closing {position} position")
    place_order(side)
    position = None

# === MAIN LOOP ===
def run_bot():
    global position, entry_price, stop_loss
    df = fetch_klines(SYMBOL, INTERVAL)
    df = calculate_supertrend(df, ST1_LEN, ST1_MUL)
    df = calculate_supertrend(df, ST2_LEN, ST2_MUL)

    st1 = df[f'supertrend_{ST1_LEN}_{ST1_MUL}'].iloc[-1]
    st2 = df[f'supertrend_{ST2_LEN}_{ST2_MUL}'].iloc[-1]

    print(f"ST1: {st1}, ST2: {st2}, Position: {position}")

    if not position:
        prev_st1 = df[f'supertrend_{ST1_LEN}_{ST1_MUL}'].iloc[-2]
        prev_st2 = df[f'supertrend_{ST2_LEN}_{ST2_MUL}'].iloc[-2]

        if st1 == st2 and st1 != prev_st1 and st2 != prev_st2:
            side = "BUY" if st1 else "SELL"
            order = place_order(side)
            position = "LONG" if side == "BUY" else "SHORT"
            entry_price = float(df['close'].iloc[-1])
            stop_loss = df[f'lowerband_{ST2_LEN}_{ST2_MUL}'].iloc[-1] if position == "LONG" else df[f'upperband_{ST2_LEN}_{ST2_MUL}'].iloc[-1]
            print(f"Entry: {entry_price}, Stop Loss: {stop_loss}")

    elif position:
        current_price = float(df['close'].iloc[-1])
        if (position == "LONG" and (not st1 or not st2 or current_price < stop_loss)) or \
           (position == "SHORT" and (st1 or st2 or current_price > stop_loss)):
            print("Exit conditions met")
            close_position()

if __name__ == "__main__":
    while True:
        run_bot()
        for _ in range(3):
            print("Type 'exit' to close trade manually or wait...")
            cmd = input()
            if cmd.strip().lower() == 'exit':
                close_position()
                break
        time.sleep(60)  # 1-minute cycle

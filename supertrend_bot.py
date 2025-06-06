import time
import requests
import pandas as pd

# --- CONFIG ---
APIURL = "https://open-api.bingx.com"
APIKEY = ""
SECRETKEY = ""
SYMBOL = "ONDOUSDT"     # Note: no dash, as required by API
INTERVAL = "3m"
QUANTITY = 1

ST1_LEN, ST1_MUL = 14, 2
ST2_LEN, ST2_MUL = 21, 1

# --- FETCH KLINES FROM PUBLIC MARKET API (no API key/signature required) ---
def fetch_klines(symbol, interval, limit=500):
    url = "https://api.bingx.com/api/v1/market/kline"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": str(limit)
    }
    response = requests.get(url, params=params)
    res = response.json()
    if 'data' not in res:
        print("Error fetching klines:", res)
        return None
    klines = res['data']
    columns = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'turnover']
    df = pd.DataFrame(klines, columns=columns)
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
        df[col] = df[col].astype(float)
    return df

# --- CALCULATE SUPER TREND ---
def calculate_supertrend(df, length, multiplier):
    hl2 = (df['high'] + df['low']) / 2
    atr = df['high'].rolling(length).max() - df['low'].rolling(length).min()
    atr = atr.rolling(length).mean()
    # True ATR calculation (classic)
    tr1 = df['high'] - df['low']
    tr2 = abs(df['high'] - df['close'].shift(1))
    tr3 = abs(df['low'] - df['close'].shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(length).mean()

    basic_upperband = hl2 + (multiplier * atr)
    basic_lowerband = hl2 - (multiplier * atr)

    final_upperband = basic_upperband.copy()
    final_lowerband = basic_lowerband.copy()

    for i in range(1, len(df)):
        if (basic_upperband[i] < final_upperband[i-1]) or (df['close'][i-1] > final_upperband[i-1]):
            final_upperband[i] = basic_upperband[i]
        else:
            final_upperband[i] = final_upperband[i-1]

        if (basic_lowerband[i] > final_lowerband[i-1]) or (df['close'][i-1] < final_lowerband[i-1]):
            final_lowerband[i] = basic_lowerband[i]
        else:
            final_lowerband[i] = final_lowerband[i-1]

    supertrend = [True]  # True = uptrend, False = downtrend

    for i in range(1, len(df)):
        if (df['close'][i] > final_upperband[i-1]):
            supertrend.append(True)
        elif (df['close'][i] < final_lowerband[i-1]):
            supertrend.append(False)
        else:
            supertrend.append(supertrend[i-1])

        # Override to upper/lower bands depending on trend
        if supertrend[i]:
            final_upperband[i] = float('nan')
        else:
            final_lowerband[i] = float('nan')

    df[f'ST_{length}_{multiplier}_trend'] = supertrend
    df[f'ST_{length}_{multiplier}_upperband'] = final_upperband
    df[f'ST_{length}_{multiplier}_lowerband'] = final_lowerband

    return df

# --- MOCK TRADING FUNCTIONS (Replace with real API calls) ---
def place_order(side, quantity, symbol=SYMBOL):
    print(f"Placing {side} order for {quantity} {symbol}")
    # TODO: implement real API order placing here
    return True

def close_position():
    print("Manually closing position now!")
    # TODO: implement real API close position call here

# --- BOT LOGIC ---
def run_bot():
    position = None  # 'LONG' or 'SHORT' or None
    stop_loss = None

    while True:
        df = fetch_klines(SYMBOL, INTERVAL, limit=100)
        if df is None:
            time.sleep(10)
            continue

        # Calculate both Supertrends
        df = calculate_supertrend(df, ST1_LEN, ST1_MUL)
        df = calculate_supertrend(df, ST2_LEN, ST2_MUL)

        # Use last candle data
        last = df.iloc[-1]

        st1_trend = last[f'ST_{ST1_LEN}_{ST1_MUL}_trend']
        st2_trend = last[f'ST_{ST2_LEN}_{ST2_MUL}_trend']
        st2_upper = last[f'ST_{ST2_LEN}_{ST2_MUL}_upperband']
        st2_lower = last[f'ST_{ST2_LEN}_{ST2_MUL}_lowerband']

        # Check if both ST give same signal
        if st1_trend == st2_trend:
            if position is None:
                print(f"[{last['open_time']}] Signal: Entering {'LONG' if st1_trend else 'SHORT'}")
                side = "BUY" if st1_trend else "SELL"
                if place_order(side, QUANTITY):
                    position = "LONG" if st1_trend else "SHORT"
                    stop_loss = st2_lower if position == "LONG" else st2_upper
                    print(f"Entered {position} at close={last['close']:.4f}, Stop Loss set at {stop_loss:.4f}")
            else:
                # Check for early exit condition: if any ST flips
                if (position == "LONG" and (not st1_trend or not st2_trend)) or (position == "SHORT" and (st1_trend or st2_trend)):
                    print(f"[{last['open_time']}] Early exit signal detected. Closing position.")
                    close_position()
                    position = None
                    stop_loss = None
                else:
                    # Update stop loss dynamically
                    new_stop_loss = st2_lower if position == "LONG" else st2_upper
                    if new_stop_loss != stop_loss:
                        print(f"Updating Stop Loss from {stop_loss:.4f} to {new_stop_loss:.4f}")
                        stop_loss = new_stop_loss

        else:
            print(f"[{last['open_time']}] Supertrend mismatch, no trade action.")

        print(f"Current Position: {position}, Stop Loss: {stop_loss}")
        print("-" * 50)

        # Manual close check
        # You can implement a manual close trigger, e.g. keyboard input, file flag, API call, etc.
        # For simplicity here, just sleep and continue
        time.sleep(180)  # Sleep for 3 minutes (candle duration)


if __name__ == "__main__":
    run_bot()

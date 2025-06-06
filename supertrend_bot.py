import time
import requests
import hmac
from hashlib import sha256
import pandas as pd

APIURL = "https://open-api.bingx.com"
APIKEY = ""  # Add your API key
SECRETKEY = ""  # Add your secret key

SYMBOL = "ONDO-USDT"  # Correct BingX symbol format, confirm on BingX API docs
INTERVAL = "3m"  # 3-minute candles
QUANTITY = 1

ST1_LEN, ST1_MUL = 14, 2
ST2_LEN, ST2_MUL = 21, 1

TRADE_ACTIVE = False
TRADE_SIDE = None
STOP_LOSS = None

def get_sign(api_secret, payload):
    return hmac.new(api_secret.encode("utf-8"), payload.encode("utf-8"), digestmod=sha256).hexdigest()

def parse_param(paramsMap):
    sortedKeys = sorted(paramsMap)
    paramsStr = "&".join(f"{k}={paramsMap[k]}" for k in sortedKeys)
    if paramsStr != "":
        return paramsStr + "&timestamp=" + str(int(time.time() * 1000))
    else:
        return paramsStr + "timestamp=" + str(int(time.time() * 1000))

def send_request(method, path, paramsMap):
    paramsStr = parse_param(paramsMap)
    signature = get_sign(SECRETKEY, paramsStr)
    url = f"{APIURL}{path}?{paramsStr}&signature={signature}"
    headers = {'X-BX-APIKEY': APIKEY}
    response = requests.request(method, url, headers=headers)
    return response.json()

def fetch_klines(symbol, interval, limit=500):
    path = "/openApi/swap/v3/quote/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": str(limit),
    }
    res = send_request("GET", path, params)
    # print("Raw Klines response:", res)  # Debug print
    
    if 'data' not in res:
        print("Error fetching klines:", res)
        return None
    
    klines = res['data']  # List of lists
    
    # BingX returns kline arrays - assign columns as per API docs:
    columns = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume',
               'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore']
    
    df = pd.DataFrame(klines, columns=columns)
    
    # Convert columns to proper dtypes:
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
    
    return df

def calculate_supertrend(df, length, multiplier):
    hl2 = (df['high'] + df['low']) / 2
    atr = df['high'].rolling(length).max() - df['low'].rolling(length).min()
    atr = atr.ewm(alpha=1/length, adjust=False).mean()
    upperband = hl2 + (multiplier * atr)
    lowerband = hl2 - (multiplier * atr)
    
    supertrend = [True] * len(df)  # True means bullish, False bearish
    final_upperband = [0] * len(df)
    final_lowerband = [0] * len(df)
    
    for i in range(1, len(df)):
        final_upperband[i] = upperband[i] if (upperband[i] < final_upperband[i-1] or df['close'][i-1] > final_upperband[i-1]) else final_upperband[i-1]
        final_lowerband[i] = lowerband[i] if (lowerband[i] > final_lowerband[i-1] or df['close'][i-1] < final_lowerband[i-1]) else final_lowerband[i-1]
        
        if df['close'][i] > final_upperband[i-1]:
            supertrend[i] = True
        elif df['close'][i] < final_lowerband[i-1]:
            supertrend[i] = False
        else:
            supertrend[i] = supertrend[i-1]
    
    df['supertrend'] = supertrend
    df['final_upperband'] = final_upperband
    df['final_lowerband'] = final_lowerband
    
    return df

def place_order(side):
    # Here, use your BingX order placement logic using their API.
    # Example placeholder print:
    print(f"Placing {side} order for quantity {QUANTITY} on {SYMBOL}")
    # You should implement actual API order calls here.
    global TRADE_ACTIVE, TRADE_SIDE
    TRADE_ACTIVE = True
    TRADE_SIDE = side

def close_trade():
    # Implement actual order close logic here
    print("Manually closing trade...")
    global TRADE_ACTIVE, TRADE_SIDE, STOP_LOSS
    TRADE_ACTIVE = False
    TRADE_SIDE = None
    STOP_LOSS = None

def run_bot():
    global STOP_LOSS, TRADE_ACTIVE, TRADE_SIDE
    
    while True:
        df = fetch_klines(SYMBOL, INTERVAL)
        if df is None:
            print("Failed to fetch data, retrying...")
            time.sleep(5)
            continue
        
        df_st1 = calculate_supertrend(df.copy(), ST1_LEN, ST1_MUL)
        df_st2 = calculate_supertrend(df.copy(), ST2_LEN, ST2_MUL)
        
        last = len(df) - 1
        
        st1_signal = df_st1['supertrend'].iloc[last]
        st2_signal = df_st2['supertrend'].iloc[last]
        
        print(f"ST1 Signal: {'LONG' if st1_signal else 'SHORT'}, ST2 Signal: {'LONG' if st2_signal else 'SHORT'}")
        
        # Trade only if both Supertrends agree
        if st1_signal == st2_signal:
            signal = "LONG" if st1_signal else "SHORT"
        else:
            signal = None
        
        # Wait 1 min for reconfirmation: implement by checking signal stays same next loop
        
        if TRADE_ACTIVE:
            # Check early exit conditions
            if TRADE_SIDE == "LONG":
                # If any supertrend flips to SHORT, close trade
                if not st1_signal or not st2_signal:
                    print("Early exit: Supertrend flipped against LONG, closing trade")
                    close_trade()
                    continue
                
                # Update stop loss to ST2 lower band
                new_sl = df_st2['final_lowerband'].iloc[last]
                if STOP_LOSS != new_sl:
                    STOP_LOSS = new_sl
                    print(f"Updated Stop Loss (LONG): {STOP_LOSS}")
                
            elif TRADE_SIDE == "SHORT":
                # If any supertrend flips to LONG, close trade
                if st1_signal or st2_signal:
                    print("Early exit: Supertrend flipped against SHORT, closing trade")
                    close_trade()
                    continue
                
                # Update stop loss to ST2 upper band
                new_sl = df_st2['final_upperband'].iloc[last]
                if STOP_LOSS != new_sl:
                    STOP_LOSS = new_sl
                    print(f"Updated Stop Loss (SHORT): {STOP_LOSS}")
        
        else:
            # No active trade, check if new trade entry condition met
            if signal:
                print(f"Signal confirmed: {signal}. Entering trade...")
                place_order(signal)
                # Set initial stop loss
                if signal == "LONG":
                    STOP_LOSS = df_st2['final_lowerband'].iloc[last]
                else:
                    STOP_LOSS = df_st2['final_upperband'].iloc[last]
                print(f"Initial Stop Loss set at: {STOP_LOSS}")
            else:
                print("No matching Supertrend signal, no trade.")
        
        # Manual close option input (non-blocking workaround)
        # You can use threading or signal or external trigger. For simplicity:
        user_input = input("Type 'close' to manually close trade, or just press Enter to continue: ").strip().lower()
        if user_input == "close" and TRADE_ACTIVE:
            close_trade()
        
        time.sleep(60)  # Wait 1 minute before next check

if __name__ == "__main__":
    run_bot()

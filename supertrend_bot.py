import time
import requests
import hmac
from hashlib import sha256
import pandas as pd

APIURL = "https://open-api.bingx.com"
APIKEY = ""      # Put your API Key here
SECRETKEY = ""   # Put your Secret Key here

def parse_params(params):
    sorted_keys = sorted(params)
    params_str = "&".join(f"{k}={params[k]}" for k in sorted_keys)
    if params_str != "":
        return params_str + "&timestamp=" + str(int(time.time() * 1000))
    else:
        return "timestamp=" + str(int(time.time() * 1000))

def get_sign(secret, payload):
    return hmac.new(secret.encode(), payload.encode(), sha256).hexdigest()

def fetch_klines(symbol, interval, limit=100):
    path = "/openApi/swap/v3/quote/klines"
    method = "GET"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": str(limit)
    }
    params_str = parse_params(params)
    signature = get_sign(SECRETKEY, params_str)
    url = f"{APIURL}{path}?{params_str}&signature={signature}"
    headers = {
        'X-BX-APIKEY': APIKEY
    }

    response = requests.get(url, headers=headers)
    print("Status code:", response.status_code)
    print("Response:", response.text)

    if response.status_code == 200:
        data = response.json()
        if 'data' in data:
            df = pd.DataFrame(data['data'])
            return df
        else:
            print("API response missing 'data' field:", data)
    else:
        print("Failed to fetch klines:", response.text)
    return None

if __name__ == "__main__":
    df = fetch_klines("ONDOUSDT", "3m", limit=10)
    if df is not None:
        print(df.head())
    else:
        print("Failed to get data.")

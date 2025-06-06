import requests

try:
    response = requests.get("https://api.binance.com/api/v3/time")
    print("Binance API time:", response.json())
except Exception as e:
    print("Error:", e)

import streamlit as st
import requests

try:
    response = requests.get("https://api.binance.com/api/v3/time")
    st.write("Binance API time:", response.json())  # Shows in Streamlit UI
except Exception as e:
    st.error(f"Error: {e}")

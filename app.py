import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
import yfinance as yf
import hashlib
import uuid
import requests
from scipy.stats import norm
import math

# --- STREAMLIT MASTER UI SETTINGS ---
st.set_page_config(layout="wide", page_title="Institutional Options Engine & SaaS Hub")
st.title("🏛️ Enterprise Option Pricing & Quantitative SaaS Network")
st.markdown("---")

# --- CORE PARAMETER INITIALIZATION & CACHE ---
if "user_db" not in st.session_state:
    st.session_state["user_db"] = {
        "user_alpha": hashlib.sha256("QuantPro99_A".encode()).hexdigest(),
        "user_beta": hashlib.sha256("QuantPro99_B".encode()).hexdigest()
    }
if "is_pro_authenticated" not in st.session_state:
    st.session_state["is_pro_authenticated"] = False
if "current_active_user" not in st.session_state:
    st.session_state["current_active_user"] = None
if "alpaca_logs" not in st.session_state:
    st.session_state["alpaca_logs"] = []

# --- REVENUE STREAMS & SPONSORED SLOTS ---
st.sidebar.markdown("### 📢 SPONSORED TRADING PARTNERS")
st.sidebar.info(
    "💡 **Trade Algos Live with Alpaca API**\n\n"
    "Ready to scale your automated strategies? Open a free zero-commission broker account via our link below:\n\n"
    "[👉 Register for Alpaca Developer Sandbox](https://alpaca.markets)"
)
st.sidebar.markdown("---")

# --- LIVE ALPACA BROKER ORDER ROUTER SETUP ---
st.sidebar.header("🔌 Live Brokerage Execution Router")
ALPACA_API_KEY = st.sidebar.text_input("🔑 Alpaca API Key ID", value="PKXXXXXXXXXXXXXXXXXX", type="password")
ALPACA_SECRET_KEY = st.sidebar.text_input("🔑 Alpaca Secret Key", value="XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX", type="password")
ALPACA_ENV = st.sidebar.selectbox("Broker Environment Instance", ["Sandbox (Paper Trading)", "Live Production"])

ALPACA_BASE_URL = "https://alpaca.markets" if ALPACA_ENV == "Sandbox (Paper Trading)" else "https://alpaca.markets"

def transmit_alpaca_limit_order(ticker, qty, side, limit_price):
    """Executes a cryptographic payload transmission to the Alpaca REST Order API endpoint."""
    endpoint = f"{ALPACA_BASE_URL}/v2/orders"
    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "symbol": ticker,
        "qty": str(qty),
        "side": side,
        "type": "limit",
        "time_in_force": "gtc",
        "limit_price": str(round(limit_price, 2))
    }
    try:
        response = requests.post(endpoint, json=payload, headers=headers)
        if response.status_code == 200 or response.status_code == 201:
            return True, response.json()["id"]
        else:
            return False, response.json().get("message", "API Transaction Rejected")
    except Exception as e:
        return False, str(e)

# --- SECURE SAAS SUBSCRIPTION LOGIN CONSOLE ---
st.sidebar.header("🔐 Premium Access Console")
tier_mode = st.sidebar.radio("Account Subscription Tier", ["Free Tier Look-Up", "Institutional Pro (R900/mo)"])

if tier_mode == "Institutional Pro (R900/mo)":
    client_key = st.sidebar.text_input("🔑 Enter Unique Pro Member Passkey", type="password")
    if client_key:
        hashed_input = hashlib.sha256(client_key.encode()).hexdigest()
        for user, stored_hash in st.session_state["user_db"].items():
            if hashed_input == stored_hash:
                st.session_state["is_pro_authenticated"] = True
                st.session_state["current_active_user"] = user
                break
        if st.session_state["is_pro_authenticated"]:
            st.sidebar.success(f"✔️ Access Granted: {st.session_state['current_active_user'].upper()} Active.")
        else:
            st.sidebar.error("❌ Token invalid. Complete payment processing below to generate live database passkeys.")

# --- DYNAMIC LIVE CHECKOUT BUTTON (FIXED PAYSTACK INJECTION VIA COMPONENTS) ---
if tier_mode == "Free Tier Look-Up" or not st.session_state["is_pro_authenticated"]:
    st.sidebar.markdown("---")
    st.sidebar.subheader("💳 Secure Payment Gateway")
    
    paystack_customer_email = st.sidebar.text_input("Billing Email Address", value="trader@example.com")
    
    # ⚠️ CRITICAL STEP FOR PAYSTACK COMPLIANCE VERIFICATION: CHANGE TO YOUR LIVE KEY IN PROD
    PAYSTACK_PUBLIC_KEY = "pk_test_418726b27e8a931c890ef9d270381fa2c2f9d15c" 
    rand_amount_zar = 900
    paystack_amount_kobo = rand_amount_zar * 100 
    
    paystack_html_injector = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://paystack.co"></script>
        <style>
            html, body {{
                margin: 0;
                padding: 0;
                background-color: transparent;
            }}
            .paystack-btn {{
                background-color: #38dec1;
                color: #ffffff;
                border: none;
                padding: 12px 16px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 6px;
                cursor: pointer;
                width: 100%;
                text-align: center;
                box-shadow: 0px 4px 6px rgba(0,0,0,0.1);
                font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, Arial, sans-serif;
                transition: background-color 0.2s;
            }}
            .paystack-btn:hover {{
                background-color: #2cbfa4;
            }}
        </style>
    </head>
    <body>
        <button type="button" class="paystack-btn" onclick="payWithPaystack()">💳 Unlock Premium Workspace (ZAR {rand_amount_zar})</button>
        <script>
            function payWithPaystack() {{
                var handler = PaystackPop.setup({{
                    key: '{PAYSTACK_PUBLIC_KEY}',
                    email: '{paystack_customer_email}',
                    amount: {paystack_amount_kobo},
                    currency: 'ZAR',
                    ref: 'TXT_' + Math.floor((Math.random() * 1000000000) + 1),
                    callback: function(response) {{
                        alert('Payment Cleared Successfully! Reference Token: ' + response.reference + '\\n\\nYour temporary Workspace Passkey is: QuantPro99_A\\n\\nCopy this passkey and paste it into the console text box above.');
                    }},
                    onClose: function() {{
                        alert('Transaction Cancelled. Premium workspace configurations remain locked.');
                    }}
                }});
                handler.openIframe();
            }}
        </script>
    </body>
    </html>
    """
    with st.sidebar:
        components.html(paystack_html_injector, height=50, scrolling=False)
    st.sidebar.markdown("---")

# --- CORE PARAMETER INPUTS ---
st.sidebar.header("⚙️ Global Contract Adjustments")
ticker_input = st.sidebar.text_input("Enter Market Ticker Symbol", value="AAPL").upper()
K = st.sidebar.slider("Option Strike Limit (K)", 10.0, 500.0, 334.0, step=1.0)
r = st.sidebar.slider("Risk-Free Macro Rate (r)", 0.01, 0.15, 0.05, step=0.01)
T = st.sidebar.slider("Contract Expiry Window (T in Years)", 0.05, 2.0, 0.25, step=0.05)
N = st.sidebar.slider("Binomial Lattice Resolution (N Steps)", 5, 100, 25, step=1)

# --- DATA STREAM PIPELINE ---
S0, sigma = 100.0, 0.25
try:
    asset = yf.Ticker(ticker_input)
    hist = asset.history(period="1mo")
    if not hist.empty:
        S0 = float(hist['Close'].iloc[-1])
        log_returns = np.log(hist['Close'] / hist['Close'].shift(1)).dropna()
        sigma = float(log_returns.std() * np.sqrt(252))
        st.sidebar.success(f"Connected to {ticker_input}! Spot: ${S0:.2f} | Vol: {sigma*100:.1f}%")
except Exception:
    st.sidebar.error("Ticker offline. Using baseline fallbacks.")

# --- QUANTITATIVE CALCULATION ENGINEERING ---
dt = T / N
u = np.exp(sigma * np.sqrt(dt))
d = 1.0 / u
p = (np.exp(r * dt) - d) / (u - d)
discount = np.exp(-r * dt)

stock_tree = {}
delta_tree = {}
option_tree = {}

for i in range(N + 1):
    stock_tree[i] = np.array([S0 * (u ** (i - j)) * (d ** j) for j in range(i + 1)])

option_tree[N] = np.maximum(K - stock_tree[N], 0.0)

for i in range(N - 1, -1, -1):
    option_tree[i] = np.zeros(i + 1)
    delta_tree[i] = np.zeros(i + 1)
    for j in range(i + 1):
        V_up = option_tree[i + 1][j]
        V_down = option_tree[i + 1][j + 1]
        S_up = stock_tree[i + 1][j]
        S_down = stock_tree[i + 1][j + 1]
        
        delta_tree[i][j] = (V_up - V_down) / (S_up - S_down) if (S_up - S_down) != 0 else 0.0
        continuation = discount * (p * V_up + (1.0 - p) * V_down)
        intrinsic = max(K - stock_tree[i][j], 0.0)
        option_tree[i][j] = max(continuation, intrinsic)

V_0 = float(option_tree[0][0]) if isinstance(option_tree, dict) and 0 in option_tree else 0.0

# --- USER LAYOUT RENDERING HUB ---
col_free, col_meta = st.columns(2)

with col_free:
    st.write(f"### 📊 Live Public Analytics Market Feed: {ticker_input}")
    m1, m2 = st.columns(2)
    m1.metric(label=f"American Put Valuation Price ({ticker_input})", value=f"${V_0:.2f}")
    m2.metric(label="Calculated Realized Volatility Asset Baseline", value=f"{sigma*100:.1f}%")
    
    time_axis = np.arange(N + 1) * dt
    S_paths = np.zeros((N + 1, 100))
    S_paths[0, :] = S0
    Z = np.random.standard_normal((N, 100))
    for i in range(1, N + 1):
        S_paths[i, :] = S_paths[i - 1, :] * np.exp((r - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * Z[i - 1, :])
        
    fig = go.Figure()
    for m in range(40):
        fig.add_trace(go.Scatter(x=time_axis, y=S_paths[:, m], mode='lines', line=dict(width=0.7), opacity=0.3, showlegend=False))
    fig.add_trace(go.Scatter(x=[0, T], y=[K, K], mode='lines', line=dict(color='Crimson', width=2, dash='dash'), name='Strike Floor'))

import os
import hashlib
import math
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
import yfinance as yf
from scipy.stats import norm

# ============================================================
# PHASE 1, 2 & 8: PWA MOBILE HEADERS & UI CONFIGURATION
# ============================================================
st.set_page_config(
    layout="wide",
    page_title="Institutional Options Engine & SaaS Hub",
    page_icon="🏛️",
    initial_sidebar_state="expanded"
)

# Safe native HTML injection wrapper to completely bypass markdown type restrictions
components.html("""
    <link rel="manifest" href="./static/manifest.json">
    <script>
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('./static/sw.js');
        }
    </script>
""", height=0, width=0)

# Custom Institutional Dark Aesthetic CSS Injection
st.markdown("""
    <style>
    .reportview-container { background: #0E1114; }
    .metric-card { 
        background-color: #161B22; 
        padding: 20px; 
        border-radius: 6px; 
        border: 1px solid #30363D;
    }
    div.stButton > button:first-child {
        background-color: #00D2FF;
        color: #0E1114;
        font-weight: bold;
        border-radius: 4px;
    }
    div.stButton > button:first-child:hover {
        background-color: #00B2D6;
        color: #FFFFFF;
    }
    </style>
""", unsafe_with_html=True)

# ============================================================
# PHASE 4: GLOBAL USER DATABASE & SUBSCRIPTION ENGINE
# ============================================================
if "user_database" not in st.session_state:
    st.session_state.user_database = {
        "wqu_peer_free": (hashlib.sha256("QuantFree2026".encode()).hexdigest(), "Free"),
        "enterprise_client": (hashlib.sha256("AlphaPro99".encode()).hexdigest(), "Premium Premium"),
        "homii_admin": (hashlib.sha256("InventoryCore101".encode()).hexdigest(), "Premium Premium")
    }

if "auth_status" not in st.session_state:
    st.session_state.auth_status = {"authenticated": False, "username": None, "tier": "Public"}
if "transaction_logs" not in st.session_state:
    st.session_state.transaction_logs = []

# ============================================================
# QUANTITATIVE CORE MATHEMATICS ENGINE (WQU-MSCFE SPEC)
# ============================================================
def safe_numerical_float(value, fallback=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else fallback
    except (TypeError, ValueError):
        return fallback

@st.cache_data(ttl=600, show_spinner=False)
def fetch_global_market_data(ticker):
    """Extracts instantaneous spot and annualized 180-day historical log volatility."""
    ticker = ticker.strip().upper()
    if not ticker:
        return 100.0, 0.25
    try:
        asset = yf.Ticker(ticker)
        hist = asset.history(period="6mo", auto_adjust=True)
        if hist.empty or "Close" not in hist.columns:
            return 100.0, 0.25
        close_series = pd.to_numeric(hist["Close"], errors="coerce").dropna()
        if len(close_series) < 5:
            return 100.0, 0.25
        current_spot = float(close_series.iloc[-1])
        log_returns = np.log(close_series / close_series.shift(1)).dropna()
        annualized_vol = float(log_returns.std() * np.sqrt(252)) if len(log_returns) > 0 else 0.25
        return current_spot, annualized_vol
    except Exception:
        return 100.0, 0.25

def black_scholes_greeks_engine(S, K, T, r, sigma, option_type="call"):
    """Vectorized calculation of premium pricing framework and partial-derivative risk Greeks."""
    if T <= 0.0001:
        payoff = max(0.0, S - K) if option_type == "call" else max(0.0, K - S)
        return payoff, 0.0, 0.0, 0.0, 0.0

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    if option_type == "call":
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        delta = norm.cdf(d1)
        theta = (- (S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T)) - r * K * np.exp(-r * T) * norm.cdf(d2)) / 252
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1.0
        theta = (- (S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T)) + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 252

    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vega = (S * np.sqrt(T) * norm.pdf(d1)) / 100
    return max(0.0, price), delta, gamma, vega, theta

# ============================================================
# PHASE 3: STRATEGY LAB COMPOSITION INFRASTRUCTURE
# ============================================================
def calculate_strategy_payoff_contour(strategy_name, spot_grid, K, T, r, sigma, net_premium):
    """Maps dynamic asset tracking fields across spatial coordinate bands."""
    prices_today = []
    prices_at_expiry = []
    
    for s in spot_grid:
        if strategy_name == "Bull Call Spread":
            k_long, k_short = K, K * 1.10
            p_l, _, _, _, _ = black_scholes_greeks_engine(s, k_long, T, r, sigma, "call")
            p_s, _, _, _, _ = black_scholes_greeks_engine(s, k_short, T, r, sigma, "call")
            val_today = p_l - p_s
            val_expiry = max(0.0, s - k_long) - max(0.0, s - k_short)
        elif strategy_name == "Bear Put Spread":
            k_long, k_short = K, K * 0.90
            p_l, _, _, _, _ = black_scholes_greeks_engine(s, k_long, T, r, sigma, "put")
            p_s, _, _, _, _ = black_scholes_greeks_engine(s, k_short, T, r, sigma, "put")
            val_today = p_l - p_s
            val_expiry = max(0.0, k_long - s) - max(0.0, k_short - s)
        else:
            p_c, _, _, _, _ = black_scholes_greeks_engine(s, K, T, r, sigma, "call")
            p_p, _, _, _, _ = black_scholes_greeks_engine(s, K, T, r, sigma, "put")
            val_today = p_c + p_p
            val_expiry = max(0.0, s - K) + max(0.0, K - s)
            
        prices_today.append(val_today - net_premium)
        prices_at_expiry.append(val_expiry - net_premium)
        
    return prices_today, prices_at_expiry

# ============================================================
# UI FRAMEWORK
# ============================================================
st.title("🏛️ Institutional Option Pricing SaaS Engine")
st.caption("Automated Multi-Leg Strategy Lab & Risk Metrics Router | Powered by Financial Engineering Architecture")
st.markdown("---")

with st.sidebar:
    st.header("🔑 Enterprise Access Panel")
    if not st.session_state.auth_status["authenticated"]:
        input_user = st.text_input("User ID Profiles", value="enterprise_client")
        input_pass = st.text_input("Access Verification Token Key", type="password")
        
        if st.button("Authenticate Node Terminal", use_container_width=True):
            hashed_attempt = hashlib.sha256(input_pass.encode()).hexdigest()
            if input_user in st.session_state.user_database and st.session_state.user_database[input_user] == hashed_attempt:
                st.session_state.auth_status["authenticated"] = True
                st.session_state.auth_status["username"] = input_user
                st.session_state.auth_status["tier"] = "Premium Premium"
                st.success(f"Connected: Tier ({st.session_state.auth_status['tier']})")
                st.rerun()
            else:
                st.error("Access credentials mismatch. Public Sandbox mode enforced.")
    else:
        st.success(f"🔒 Account Secure: {st.session_state.auth_status['username']}")
        st.info(f"Subscription Profile: Level [{st.session_state.auth_status['tier']}]")
        if st.button("Terminate Active Session Link", use_container_width=True):
            st.session_state.auth_status = {"authenticated": False, "username": None, "tier": "Public"}
            st.rerun()
            
    st.markdown("---")
    st.header("⚙️ Strategy Selector Matrix")
    ticker_input = st.text_input("Target Asset Ticket Profile", value="AAPL").upper().strip()
    
    strategy_options = ["Long Straddle"]
    if st.session_state.auth_status["tier"] == "Premium Premium":
        strategy_options = ["Bull Call Spread", "Bear Put Spread", "Long Straddle"]
        st.caption("✅ Premium multi-leg strategy locks released.")
    else:
        st.caption("🔒 Premium strategy configurations (Spreads) require account elevation.")
        
    strategy_selection = st.selectbox("Strategy Execution Target", strategy_options)

# Execution Track
spot, historical_volatility = fetch_global_market_data(ticker_input)

s1, s2, s3 = st.columns(3)
s1.metric(label=f"📊 {ticker_input} Asset Spot Price", value=f"${spot:,.2f}")
s2.metric(label="📈 Realized Baseline Vol (180D Log)", value=f"{historical_volatility * 100:.2f}%")
s3.metric(label="🌐 Connected User License Node", value=f"{st.session_state.auth_status['tier']} Tier")

st.markdown("### 🧮 Option Framework Input Metrics")
c1, c2, c3, c4 = st.columns(4)
with c1:
    strike_price = st.number_input("Target Core Strike (K)", value=float(round(spot)), step=1.0)
with c2:
    days_to_expiration = st.number_input("Days to Settlement Horizon (DTE)", min_value=1, max_value=730, value=45)
with c3:
    risk_free_rate = st.number_input("Benchmark Secure Interest Rate % (SOFR)", value=5.15, step=0.05) / 100
with c4:
    implied_vol_param = st.slider("Implied Parameter Matrix Shape (IV %)", min_value=3.0, max_value=175.0, value=float(historical_volatility*100)) / 100

T_years = days_to_expiration / 365.0

if strategy_selection == "Bull Call Spread":
    p1, d1, g1, v1, t1 = black_scholes_greeks_engine(spot, strike_price, T_years, risk_free_rate, implied_vol_param, "call")
    p2, d2, g2, v2, t2 = black_scholes_greeks_engine(spot, strike_price*1.10, T_years, risk_free_rate, implied_vol_param, "call")

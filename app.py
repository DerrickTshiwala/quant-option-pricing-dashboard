import os
import hashlib
import math

import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
from scipy.stats import norm


# ============================================================
# STREAMLIT CONFIG
# ============================================================
st.set_page_config(
    layout="wide",
    page_title="Institutional Options Engine & SaaS Hub",
    page_icon="🏛️",
)

st.title("🏛️ Enterprise Option Pricing & Quantitative SaaS Network")
st.markdown("---")


# ============================================================
# SESSION STATE
# ============================================================
if "user_db" not in st.session_state:
    st.session_state.user_db = {
        "user_alpha": hashlib.sha256("QuantPro99_A".encode()).hexdigest(),
        "user_beta": hashlib.sha256("QuantPro99_B".encode()).hexdigest(),
    }

if "is_pro_authenticated" not in st.session_state:
    st.session_state.is_pro_authenticated = False

if "current_active_user" not in st.session_state:
    st.session_state.current_active_user = None

if "alpaca_logs" not in st.session_state:
    st.session_state.alpaca_logs = []


# ============================================================
# HELPERS
# ============================================================
def safe_float(value, fallback):
    try:
        value = float(value)
        return value if math.isfinite(value) else fallback
    except (TypeError, ValueError):
        return fallback


@st.cache_data(ttl=300, show_spinner=False)
def get_market_data(ticker):
    """Fetch recent market data and annualized realized volatility."""
    ticker = ticker.strip().upper()

    if not ticker:
        raise ValueError("Ticker symbol cannot be empty.")

    asset = yf.Ticker(ticker)
    hist = asset.history(period="3mo", auto_adjust=True)

    if hist.empty or "Close" not in hist.columns:
        raise ValueError(f"No market data returned for {ticker}.")

    close = pd.to_numeric(hist["Close"], errors="coerce").dropna()

    if close.empty:
        raise ValueError(f"No valid closing prices returned for {ticker}.")

    spot = float(close.iloc[-1])

    if len(close) >= 3:
        log_returns = np.log(close / close.shift(1)).dropna()
        volatility = safe_float(
            log_returns.std(ddof=1) * np.sqrt(252),
            0.25,
        )
    else:
        volatility = 0.25

    # Prevent invalid/unstable lattice parameters.
    volatility = float(np.clip(volatility, 1e-6, 5.0))

    return spot, volatility, close


def price_american_put_binomial(S0, K, r, T, sigma, N):
    """
    Cox-Ross-Rubinstein binomial valuation for an American put.
    Returns price, root delta and lattice arrays.
    """
    if S0 <= 0:
        raise ValueError("Spot price must be greater than zero.")
    if K <= 0:
        raise ValueError("Strike must be greater than zero.")
    if T <= 0:
        raise ValueError("Expiry must be greater than zero.")
    if sigma <= 0:
        raise ValueError("Volatility must be greater than zero.")
    if N < 1:
        raise ValueError("Number of steps must be at least 1.")

    dt = T / N
    u = np.exp(sigma * np.sqrt(dt))
    d = 1.0 / u

    # CRR risk-neutral probability.
    p = (np.exp(r * dt) - d) / (u - d)

    if not 0.0 < p < 1.0:
        raise ValueError(
            "Invalid CRR probability. Adjust rate, volatility, expiry, "
            "or increase the number of lattice steps."
        )

    discount = np.exp(-r * dt)

    stock_tree = {}
    option_tree = {}
    delta_tree = {}

    for i in range(N + 1):
        stock_tree[i] = np.array(
            [S0 * (u ** (i - j)) * (d ** j) for j in range(i + 1)],
            dtype=float,
        )

    # American put terminal payoff.
    option_tree[N] = np.maximum(K - stock_tree[N], 0.0)

    # Backward induction with early exercise.
    for i in range(N - 1, -1, -1):
        option_tree[i] = np.zeros(i + 1, dtype=float)
        delta_tree[i] = np.zeros(i + 1, dtype=float)

        for j in range(i + 1):
            v_up = option_tree[i + 1][j]
            v_down = option_tree[i + 1][j + 1]

            s_up = stock_tree[i + 1][j]
            s_down = stock_tree[i + 1][j + 1]

            denominator = s_up - s_down
            delta_tree[i][j] = (
                (v_up - v_down) / denominator
                if abs(denominator) > 1e-14
                else 0.0
            )

            continuation = discount * (
                p * v_up + (1.0 - p) * v_down
            )
            intrinsic = max(K - stock_tree[i][j], 0.0)

            option_tree[i][j] = max(continuation, intrinsic)

    return (
        float(option_tree[0][0]),
        float(delta_tree[0][0]),
        stock_tree,
        option_tree,
        delta_tree,
        p,
        u,
        d,
    )


def black_scholes_put(S0, K, r, T, sigma):
    """European Black-Scholes put for reference."""
    if min(S0, K, T, sigma) <= 0:
        return np.nan, np.nan

    d1 = (
        np.log(S0 / K)
        + (r + 0.5 * sigma**2) * T
    ) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    price = (
        K * np.exp(-r * T) * norm.cdf(-d2)
        - S0 * norm.cdf(-d1)
    )
    delta = norm.cdf(d1) - 1.0

    return float(price), float(delta)


def transmit_alpaca_limit_order(
    ticker,
    qty,
    side,
    limit_price,
    api_key,
    secret_key,
    environment,
):
    """
    Submit a limit order to Alpaca.
    Live trading is intentionally explicit; no credentials are hard-coded.
    """
    ticker = ticker.strip().upper()
    side = side.lower().strip()

    if not ticker:
        return False, "Ticker is required."
    if side not in {"buy", "sell"}:
        return False, "Side must be buy or sell."
    if qty <= 0:
        return False, "Quantity must be greater than zero."
    if limit_price <= 0:
        return False, "Limit price must be greater than zero."
    if not api_key or not secret_key:
        return False, "Enter valid Alpaca API credentials first."

    base_url = (
        "https://paper-api.alpaca.markets"
        if environment == "Sandbox (Paper Trading)"
        else "https://api.alpaca.markets"
    )

    endpoint = f"{base_url}/v2/orders"

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
        "Content-Type": "application/json",
    }

    payload = {
        "symbol": ticker,
        "qty": str(qty),
        "side": side,
        "type": "limit",
        "time_in_force": "gtc",
        "limit_price": str(round(limit_price, 2)),
    }

    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=20,
        )

        try:
            body = response.json()
        except ValueError:
            body = {}

        if response.ok:
            order_id = body.get("id", "Unknown")
            return True, order_id

        message = (
            body.get("message")
            or body.get("code")
            or f"HTTP {response.status_code}"
        )
        return False, str(message)

    except requests.RequestException as exc:
        return False, f"Network/API error: {exc}"


# ============================================================
# SIDEBAR: SPONSORED PARTNER
# ============================================================
st.sidebar.markdown("### 📢 SPONSORED TRADING PARTNERS")
st.sidebar.info(
    "💡 **Trade Algos Live with Alpaca API**\n\n"
    "Use Alpaca's official developer resources to configure paper "
    "or live trading."
)
st.sidebar.markdown(
    "[👉 Visit Alpaca](https://alpaca.markets/)"
)
st.sidebar.markdown("---")


# ============================================================
# SIDEBAR: ALPACA
# ============================================================
st.sidebar.header("🔌 Brokerage Execution Router")

alpaca_api_key = st.sidebar.text_input(
    "🔑 Alpaca API Key ID",
    value=os.getenv("ALPACA_API_KEY", ""),
    type="password",
)

alpaca_secret_key = st.sidebar.text_input(
    "🔑 Alpaca Secret Key",
    value=os.getenv("ALPACA_SECRET_KEY", ""),
    type="password",
)

alpaca_env = st.sidebar.selectbox(
    "Broker Environment",
    ["Sandbox (Paper Trading)", "Live Production"],
)

if alpaca_env == "Live Production":
    st.sidebar.warning(
        "⚠️ LIVE mode can submit real orders. Verify every order before sending."
    )


# ============================================================
# SIDEBAR: PREMIUM ACCESS
# ============================================================
st.sidebar.header("🔐 Premium Access Console")

tier_mode = st.sidebar.radio(
    "Account Subscription Tier",
    ["Free Tier Look-Up", "Institutional Pro (R900/mo)"],
)

if tier_mode == "Institutional Pro (R900/mo)":
    client_key = st.sidebar.text_input(
        "🔑 Enter Pro Member Passkey",
        type="password",
    )

    if client_key:
        hashed_input = hashlib.sha256(client_key.encode()).hexdigest()

        matched_user = next(
            (
                user
                for user, stored_hash in st.session_state.user_db.items()
                if hashed_input == stored_hash
            ),
            None,
        )

        if matched_user:
            st.session_state.is_pro_authenticated = True
            st.session_state.current_active_user = matched_user
            st.sidebar.success(
                f"✔️ Access Granted: {matched_user.upper()} Active."
            )
        else:
            st.session_state.is_pro_authenticated = False
            st.session_state.current_active_user = None
            st.sidebar.error("❌ Invalid Pro passkey.")

if tier_mode == "Free Tier Look-Up":
    st.session_state.is_pro_authenticated = False
    st.session_state.current_active_user = None


# ============================================================
# PAYMENT INFORMATION
# ============================================================
if tier_mode == "Institutional Pro (R900/mo)" and not st.session_state.is_pro_authenticated:
    st.sidebar.markdown("---")
    st.sidebar.subheader("💳 Secure Payment Gateway")

    st.sidebar.info(
        "Payment processing is not simulated in this application. "
        "Connect a verified Paystack backend/webhook before accepting "
        "real payments and granting Pro access."
    )

    st.sidebar.markdown(
        "[👉 Open Paystack](https://paystack.com/)"
    )


# ============================================================
# SIDEBAR: MODEL PARAMETERS
# ============================================================
st.sidebar.header("⚙️ Global Contract Adjustments")

ticker_input = st.sidebar.text_input(
    "Enter Market Ticker Symbol",
    value="AAPL",
).strip().upper()

K = st.sidebar.slider(
    "Option Strike (K)",
    min_value=1.0,
    max_value=1000.0,
    value=334.0,
    step=1.0,
)

r = st.sidebar.slider(
    "Risk-Free Rate (r)",
    min_value=0.0,
    max_value=0.15,
    value=0.05,
    step=0.005,
    format="%.3f",
)

T = st.sidebar.slider(
    "Expiry (T in Years)",
    min_value=0.01,
    max_value=5.0,
    value=0.25,
    step=0.01,
)

N = st.sidebar.slider(
    "Binomial Lattice Steps (N)",
    min_value=5,
    max_value=300,
    value=50,
    step=1,
)


# ============================================================
# MARKET DATA
# ============================================================
S0 = 100.0
sigma = 0.25
close_series = pd.Series(dtype=float)
market_ok = False

try:
    S0, sigma, close_series = get_market_data(ticker_input)
    market_ok = True

    st.sidebar.success(
        f"Connected to {ticker_input}  •  "
        f"Spot: ${S0:.2f}  •  "
        f"Realized Vol: {sigma * 100:.1f}%"
    )

except Exception as exc:
    st.sidebar.warning(
        f"Market data unavailable. Using fallback values. ({exc})"
    )


# ============================================================
# OPTION ENGINE
# ============================================================
try:
    (
        V_0,
        delta_val,
        stock_tree,
        option_tree,
        delta_tree,
        risk_neutral_p,
        u,
        d,
    ) = price_american_put_binomial(
        S0=S0,
        K=K,
        r=r,
        T=T,
        sigma=sigma,
        N=N,
    )

    european_put, european_delta = black_scholes_put(
        S0, K, r, T, sigma
    )

except ValueError as exc:
    st.error(f"Pricing engine error: {exc}")
    st.stop()


# ============================================================
# MAIN DASHBOARD
# ============================================================
col_free, col_meta = st.columns([2.2, 1])

with col_free:
    st.subheader(
        f"📊 Live Public Analytics Market Feed: {ticker_input}"
    )

    m1, m2, m3 = st.columns(3)

    m1.metric(
        "American Put Value",
        f"${V_0:.2f}",
    )

    m2.metric(
        "Spot Price",
        f"${S0:.2f}",
    )

    m3.metric(
        "Realized Volatility",
        f"{sigma * 100:.1f}%",
    )

    # Monte Carlo visualization.
    time_axis = np.linspace(0.0, T, N + 1)
    num_paths = 100

    rng = np.random.default_rng(42)
    Z = rng.standard_normal((N, num_paths))

    S_paths = np.zeros((N + 1, num_paths))
    S_paths[0, :] = S0

    for i in range(1, N + 1):
        S_paths[i, :] = (
            S_paths[i - 1, :]
            * np.exp(
                (r - 0.5 * sigma**2) * (T / N)
                + sigma * np.sqrt(T / N) * Z[i - 1, :]
            )
        )

    fig = go.Figure()

    for m in range(min(40, num_paths)):
        fig.add_trace(
            go.Scatter(
                x=time_axis,
                y=S_paths[:, m],
                mode="lines",
                line=dict(width=0.7),
                opacity=0.3,
                showlegend=False,
            )
        )

    fig.add_trace(
        go.Scatter(
            x=[0, T],
            y=[K, K],
            mode="lines",
            line=dict(width=2, dash="dash"),
            name="Strike",
        )
    )

    fig.update_layout(
        title="Simulated Asset Price Paths",
        xaxis_title="Time (years)",
        yaxis_title="Asset Price ($)",
        height=500,
        margin=dict(l=20, r=20, t=60, b=20),
    )

    st.plotly_chart(fig, use_container_width=True)


with col_meta:
    st.subheader("📈 Model Diagnostics")

    st.metric(
        "American Put",
        f"${V_0:.4f}",
    )

    st.metric(
        "European Put Reference",
        f"${european_put:.4f}",
    )

    st.metric(
        "American Premium",
        f"${max(V_0 - european_put, 0.0):.4f}",
    )

    st.metric(
        "Root Delta",
        f"{delta_val:.4f}",
    )

    st.metric(
        "Risk-Neutral Probability",
        f"{risk_neutral_p:.4f}",
    )

    st.caption(
        "The American price includes early-exercise logic; "
        "the European figure is shown only as a reference."
    )


# ============================================================
# PRO WORKSPACE
# ============================================================
st.markdown("---")

if st.session_state.is_pro_authenticated:
    st.header("🔐 Institutional Pro Workspace")

    tab1, tab2, tab3 = st.tabs(
        ["📐 Greeks & Lattice", "📤 Order Router", "🧾 Session Log"]
    )

    with tab1:
        greek_df = pd.DataFrame(
            {
                "Metric": [
                    "Spot (S₀)",
                    "Strike (K)",
                    "Risk-Free Rate",
                    "Expiry (Years)",
                    "Volatility",
                    "CRR Up Factor",
                    "CRR Down Factor",
                    "Risk-Neutral Probability",
                    "American Put",
                    "European Put",
                    "American Put Delta",
                    "European Put Delta",
                ],
                "Value": [
                    S0,
                    K,
                    r,
                    T,
                    sigma,
                    u,
                    d,
                    risk_neutral_p,
                    V_0,
                    european_put,
                    delta_val,
                    european_delta,
                ],
            }
        )

        st.dataframe(
            greek_df,
            use_container_width=True,
            hide_index=True,
        )

        lattice_level = st.slider(
            "Inspect lattice level",
            min_value=0,
            max_value=N,
            value=min(5, N),
        )

        lattice_df = pd.DataFrame(
            {
                "Node": np.arange(lattice_level + 1),
                "Stock Price": stock_tree[lattice_level],
                "Option Value": option_tree[lattice_level],
            }
        )

        st.dataframe(
            lattice_df,
            use_container_width=True,
            hide_index=True,
        )

    with tab2:
        st.warning(
            "Brokerage execution is disabled until valid credentials are "
            "entered. Live Production can place real trades."
        )

        order_col1, order_col2 = st.columns(2)

        with order_col1:
            order_symbol = st.text_input(
                "Order Symbol",
                value=ticker_input,
            ).strip().upper()

            order_qty = st.number_input(
                "Quantity",
                min_value=0.0001,
                value=1.0,
                step=1.0,
            )

        with order_col2:
            order_side = st.selectbox(
                "Side",
                ["buy", "sell"],
            )

            order_limit = st.number_input(
                "Limit Price ($)",
                min_value=0.01,
                value=max(round(S0, 2), 0.01),
                step=0.01,
            )

        confirm_live = False

        if alpaca_env == "Live Production":
            confirm_live = st.checkbox(
                "I understand this can submit a real order.",
                value=False,
            )
        else:
            confirm_live = True

        if st.button(
            "🚀 Submit Limit Order",
            type="primary",
            disabled=not confirm_live,
        ):
            success, result = transmit_alpaca_limit_order(
                ticker=order_symbol,
                qty=order_qty,
                side=order_side,
                limit_price=order_limit,
                api_key=alpaca_api_key,
                secret_key=alpaca_secret_key,
                environment=alpaca_env,
            )

            log_entry = {
                "Ticker": order_symbol,
                "Quantity": order_qty,
                "Side": order_side,
                "Limit Price": order_limit,
                "Environment": alpaca_env,
                "Result": result,
            }
            st.session_state.alpaca_logs.append(log_entry)

            if success:
                st.success(f"Order accepted. Order ID: {result}")
            else:
                st.error(f"Order rejected: {result}")

    with tab3:
        if st.session_state.alpaca_logs:
            st.dataframe(
                pd.DataFrame(st.session_state.alpaca_logs),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No order attempts in this session.")

else:
    st.info(
        "🔒 Institutional Pro features are locked. "
        "The public analytics dashboard remains available."
    )


# ============================================================
# FOOTER
# ============================================================
st.markdown("---")
st.caption(
    "Quantitative analytics only. Market data may be delayed or unavailable. "
    "This application does not constitute investment advice."
)

import math
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from scipy.stats import norm


# ============================================================
# CONFIG
# ============================================================
st.set_page_config(
    page_title="QuantOptions — Quantitative Options Intelligence",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Lightweight custom CSS. Streamlit remains the zero-rand MVP host.
st.markdown(
    """
    <style>
    .hero {
        padding: 1.5rem 1.7rem;
        border-radius: 18px;
        border: 1px solid rgba(128,128,128,.25);
        margin-bottom: 1rem;
    }
    .hero h1 { margin-bottom: .25rem; }
    .muted { opacity: .75; }
    .card {
        padding: 1rem;
        border-radius: 14px;
        border: 1px solid rgba(128,128,128,.22);
        height: 100%;
    }
    .small { font-size: .88rem; opacity: .78; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SESSION STATE
# ============================================================
if "saved_strategies" not in st.session_state:
    st.session_state.saved_strategies = []

if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["AAPL", "MSFT", "NVDA", "SPY"]


# ============================================================
# QUANT ENGINE
# ============================================================
def validate_inputs(S, K, T, sigma):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        raise ValueError("Spot, strike, expiry and volatility must be positive.")


def bs_price_greeks(S, K, r, T, sigma, option_type):
    validate_inputs(S, K, T, sigma)

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (
        sigma * np.sqrt(T)
    )
    d2 = d1 - sigma * np.sqrt(T)

    if option_type == "Call":
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        delta = norm.cdf(d1)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        delta = norm.cdf(d1) - 1

    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    vega = S * norm.pdf(d1) * np.sqrt(T) / 100.0

    if option_type == "Call":
        theta = (
            -S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
            - r * K * np.exp(-r * T) * norm.cdf(d2)
        ) / 365.0
        rho = K * T * np.exp(-r * T) * norm.cdf(d2) / 100.0
    else:
        theta = (
            -S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
            + r * K * np.exp(-r * T) * norm.cdf(-d2)
        ) / 365.0
        rho = -K * T * np.exp(-r * T) * norm.cdf(-d2) / 100.0

    return {
        "Price": float(price),
        "Delta": float(delta),
        "Gamma": float(gamma),
        "Vega / 1%": float(vega),
        "Theta / day": float(theta),
        "Rho / 1%": float(rho),
        "d1": float(d1),
        "d2": float(d2),
    }


def american_put_binomial(S, K, r, T, sigma, steps=100):
    validate_inputs(S, K, T, sigma)

    dt = T / steps
    u = np.exp(sigma * np.sqrt(dt))
    d = 1 / u
    denominator = u - d
    p = (np.exp(r * dt) - d) / denominator

    if not 0 < p < 1:
        raise ValueError(
            "CRR probability is outside (0,1). Try different model inputs."
        )

    disc = np.exp(-r * dt)

    prices = np.array(
        [S * u ** (steps - j) * d**j for j in range(steps + 1)]
    )
    values = np.maximum(K - prices, 0)

    for i in range(steps - 1, -1, -1):
        prices = np.array(
            [S * u ** (i - j) * d**j for j in range(i + 1)]
        )
        continuation = disc * (p * values[:-1] + (1 - p) * values[1:])
        intrinsic = np.maximum(K - prices, 0)
        values = np.maximum(continuation, intrinsic)

    return float(values[0])


def payoff_at_expiry(S, K, option_type, side, premium, quantity=1):
    if option_type == "Call":
        intrinsic = np.maximum(S - K, 0)
    else:
        intrinsic = np.maximum(K - S, 0)

    multiplier = 1 if side == "Buy" else -1
    return quantity * (multiplier * intrinsic - multiplier * premium)


def build_strategy_payoff(spot, legs, points=250):
    strikes = [leg["strike"] for leg in legs]
    low = min([spot * 0.55] + [k * 0.70 for k in strikes])
    high = max([spot * 1.45] + [k * 1.30 for k in strikes])
    prices = np.linspace(low, high, points)
    total = np.zeros(points)

    for leg in legs:
        total += payoff_at_expiry(
            prices,
            leg["strike"],
            leg["type"],
            leg["side"],
            leg["premium"],
            leg["quantity"],
        )

    return prices, total


def strategy_metrics(prices, payoff):
    max_profit = float(np.max(payoff))
    max_loss = float(np.min(payoff))
    break_even = []

    signs = np.sign(payoff)
    for i in range(len(prices) - 1):
        if signs[i] == 0:
            break_even.append(float(prices[i]))
        elif signs[i] * signs[i + 1] < 0:
            x1, x2 = prices[i], prices[i + 1]
            y1, y2 = payoff[i], payoff[i + 1]
            x = x1 - y1 * (x2 - x1) / (y2 - y1)
            break_even.append(float(x))

    return max_profit, max_loss, break_even


@st.cache_data(ttl=300, show_spinner=False)
def market_snapshot(ticker):
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("Enter a ticker.")

    hist = yf.Ticker(ticker).history(
        period="6mo",
        interval="1d",
        auto_adjust=True,
    )

    if hist.empty or "Close" not in hist.columns:
        raise ValueError(f"No market data was returned for {ticker}.")

    close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
    if close.empty:
        raise ValueError(f"No valid prices were returned for {ticker}.")

    spot = float(close.iloc[-1])
    returns = np.log(close / close.shift(1)).dropna()

    hv = float(returns.std() * np.sqrt(252)) if len(returns) > 2 else 0.25
    hv = float(np.clip(hv, 0.01, 3.0))

    return spot, hv, close


# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.title("📈 QuantOptions")
st.sidebar.caption("Quantitative Options Intelligence")

page = st.sidebar.radio(
    "Workspace",
    [
        "🏠 Dashboard",
        "🧮 Option Analyzer",
        "🧩 Strategy Lab",
        "📉 Volatility Lab",
        "📚 Quant Education",
        "💳 Pricing",
        "📄 Policies",
    ],
)

st.sidebar.markdown("---")
ticker = st.sidebar.text_input("Market ticker", "AAPL").strip().upper()
risk_free = st.sidebar.slider(
    "Risk-free rate",
    0.0,
    0.15,
    0.05,
    0.005,
    format="%.3f",
)

try:
    spot, historical_vol, close_prices = market_snapshot(ticker)
    market_status = f"{ticker}: ${spot:,.2f}"
except Exception as exc:
    spot, historical_vol, close_prices = 100.0, 0.25, pd.Series(dtype=float)
    market_status = "Market data unavailable"
    st.sidebar.warning(str(exc))

st.sidebar.info(market_status)
st.sidebar.caption(
    "Market data can be delayed/unavailable. This product provides "
    "analytics and education, not personalised investment advice."
)


# ============================================================
# HERO
# ============================================================
st.markdown(
    """
    <div class="hero">
        <h1>QuantOptions</h1>
        <div style="font-size:1.2rem;">
            Quantitative Options Intelligence
        </div>
        <p class="muted">
            Analyze options, model strategies, explore volatility and
            understand risk — from one global workspace.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# DASHBOARD
# ============================================================
if page == "🏠 Dashboard":
    st.subheader("Market Intelligence")

    a, b, c, d = st.columns(4)
    a.metric("Spot", f"${spot:,.2f}")
    b.metric("Historical Volatility", f"{historical_vol * 100:.1f}%")
    c.metric("Risk-free Rate", f"{risk_free * 100:.2f}%")
    d.metric("Watchlist", len(st.session_state.watchlist))

    st.markdown("### What do you want to do?")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(
            '<div class="card"><h3>🧮 Analyze an Option</h3>'
            '<p>Price calls and puts and inspect the Greeks.</p></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<div class="card"><h3>🧩 Build a Strategy</h3>'
            '<p>Combine multiple legs and inspect payoff at expiry.</p></div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            '<div class="card"><h3>📉 Study Volatility</h3>'
            '<p>Compare historical volatility across time.</p></div>',
            unsafe_allow_html=True,
        )

    st.markdown("### Price history")

    if not close_prices.empty:
        fig = go.Figure(
            go.Scatter(
                x=close_prices.index,
                y=close_prices.values,
                mode="lines",
                name=ticker,
            )
        )
        fig.update_layout(
            height=430,
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis_title="Date",
            yaxis_title="Price",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Product roadmap")
    roadmap = pd.DataFrame(
        {
            "Stage": [
                "MVP",
                "Growth",
                "Pro",
                "Institutional",
                "Platform",
            ],
            "Capability": [
                "Pricing + Strategy Lab",
                "Accounts + subscriptions",
                "Backtesting + portfolio risk",
                "University/team workspaces",
                "API + broker integrations",
            ],
            "Status": [
                "Building",
                "Next",
                "Planned",
                "Planned",
                "Planned",
            ],
        }
    )
    st.dataframe(roadmap, use_container_width=True, hide_index=True)


# ============================================================
# OPTION ANALYZER
# ============================================================
elif page == "🧮 Option Analyzer":
    st.subheader("Option Analyzer")
    st.caption("Black-Scholes reference analytics + American put binomial valuation.")

    c1, c2, c3, c4 = st.columns(4)
    option_type = c1.selectbox("Option", ["Call", "Put"])
    strike = c2.number_input("Strike", min_value=0.01, value=float(round(spot)), step=1.0)
    expiry = c3.number_input("Expiry (years)", min_value=0.01, value=0.25, step=0.01)
    volatility = c4.number_input(
        "Volatility",
        min_value=0.01,
        max_value=3.0,
        value=float(round(historical_vol, 4)),
        step=0.01,
        format="%.4f",
    )

    try:
        greeks = bs_price_greeks(
            spot, strike, risk_free, expiry, volatility, option_type
        )

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Theoretical Price", f"${greeks['Price']:.4f}")
        m2.metric("Delta", f"{greeks['Delta']:.4f}")
        m3.metric("Gamma", f"{greeks['Gamma']:.6f}")
        m4.metric("Vega / 1%", f"${greeks['Vega / 1%']:.4f}")

        g1, g2 = st.columns(2)
        with g1:
            st.metric("Theta / day", f"${greeks['Theta / day']:.4f}")
        with g2:
            st.metric("Rho / 1%", f"${greeks['Rho / 1%']:.4f}")

        if option_type == "Put":
            try:
                american = american_put_binomial(
                    spot, strike, risk_free, expiry, volatility, steps=100
                )
                st.success(f"American put binomial value: ${american:.4f}")
                st.caption(
                    f"Early-exercise premium vs European reference: "
                    f"${max(american - greeks['Price'], 0):.4f}"
                )
            except ValueError as exc:
                st.warning(str(exc))

        prices = np.linspace(max(0.01, spot * 0.5), spot * 1.5, 180)
        if option_type == "Call":
            theoretical = np.maximum(prices - strike, 0)
        else:
            theoretical = np.maximum(strike - prices, 0)

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=prices,
                y=theoretical,
                mode="lines",
                name="Intrinsic value at expiry",
            )
        )
        fig.add_vline(x=spot, line_dash="dash", annotation_text="Spot")
        fig.add_vline(x=strike, line_dash="dot", annotation_text="Strike")
        fig.update_layout(
            title="Expiration payoff before premium",
            xaxis_title="Underlying price",
            yaxis_title="Payoff",
            height=450,
        )
        st.plotly_chart(fig, use_container_width=True)

        report = pd.DataFrame([greeks])
        st.download_button(
            "⬇️ Download analysis CSV",
            report.to_csv(index=False),
            file_name=f"{ticker}_{option_type.lower()}_analysis.csv",
            mime="text/csv",
        )

    except ValueError as exc:
        st.error(str(exc))


# ============================================================
# STRATEGY LAB
# ============================================================
elif page == "🧩 Strategy Lab":
    st.subheader("Strategy Lab")
    st.write(
        "Build a multi-leg strategy and inspect its expiration payoff. "
        "Premiums are user/model inputs, so replace them with actual "
        "market option quotes when available."
    )

    templates = {
        "Custom": [],
        "Long Call": [("Buy", "Call", round(spot), 1)],
        "Long Put": [("Buy", "Put", round(spot), 1)],
        "Covered Call": [("Sell", "Call", round(spot * 1.05), 1)],
        "Bull Call Spread": [
            ("Buy", "Call", round(spot * 0.98), 1),
            ("Sell", "Call", round(spot * 1.08), 1),
        ],
        "Bear Put Spread": [
            ("Buy", "Put", round(spot * 1.02), 1),
            ("Sell", "Put", round(spot * 0.92), 1),
        ],
        "Long Straddle": [
            ("Buy", "Call", round(spot), 1),
            ("Buy", "Put", round(spot), 1),
        ],
    }

    template = st.selectbox("Start with a template", list(templates))
    legs = []

    if template != "Custom":
        for side, option_type, k, qty in templates[template]:
            default_premium = max(
                0.01,
                bs_price_greeks(
                    spot,
                    float(k),
                    risk_free,
                    0.25,
                    historical_vol,
                    option_type,
                )["Price"],
            )
            legs.append(
                {
                    "side": side,
                    "type": option_type,
                    "strike": float(k),
                    "premium": float(round(default_premium, 2)),
                    "quantity": int(qty),
                }
            )

    st.markdown("### Strategy legs")

    number_of_legs = st.number_input(
        "Number of legs",
        min_value=1,
        max_value=8,
        value=max(1, len(legs)),
        step=1,
    )

    while len(legs) < number_of_legs:
        legs.append(
            {
                "side": "Buy",
                "type": "Call",
                "strike": float(round(spot)),
                "premium": 1.0,
                "quantity": 1,
            }
        )

    legs = legs[:number_of_legs]

    for i in range(number_of_legs):
        leg = legs[i]
        cols = st.columns([1, 1, 1.2, 1.2, 1])
        leg["side"] = cols[0].selectbox(
            f"Side {i+1}",
            ["Buy", "Sell"],
            index=0 if leg["side"] == "Buy" else 1,
            key=f"side_{i}",
        )
        leg["type"] = cols[1].selectbox(
            f"Type {i+1}",
            ["Call", "Put"],
            index=0 if leg["type"] == "Call" else 1,
            key=f"type_{i}",
        )
        leg["strike"] = cols[2].number_input(
            f"Strike {i+1}",
            min_value=0.01,
            value=float(leg["strike"]),
            step=1.0,
            key=f"strike_{i}",
        )
        leg["premium"] = cols[3].number_input(
            f"Premium {i+1}",
            min_value=0.0,
            value=float(leg["premium"]),
            step=0.01,
            key=f"premium_{i}",
        )
        leg["quantity"] = cols[4].number_input(
            f"Qty {i+1}",
            min_value=1,
            value=int(leg["quantity"]),
            step=1,
            key=f"qty_{i}",
        )

    prices, payoff = build_strategy_payoff(spot, legs)
    max_profit, max_loss, break_even = strategy_metrics(prices, payoff)

    m1, m2, m3 = st.columns(3)
    m1.metric("Maximum modeled profit", f"${max_profit:,.2f}")
    m2.metric("Maximum modeled loss", f"${max_loss:,.2f}")
    m3.metric(
        "Approx. break-even",
        ", ".join(f"${x:.2f}" for x in break_even) if break_even else "None in range",
    )

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=prices,
            y=payoff,
            mode="lines",
            name="Strategy payoff",
        )
    )
    fig.add_hline(y=0, line_dash="dot")
    fig.add_vline(x=spot, line_dash="dash", annotation_text="Spot")
    fig.update_layout(
        title=f"{template} — payoff at expiry",
        xaxis_title="Underlying price at expiry",
        yaxis_title="Profit / Loss",
        height=520,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(pd.DataFrame(legs), use_container_width=True, hide_index=True)

    save_name = st.text_input("Save strategy name", template)
    if st.button("💾 Save Strategy"):
        st.session_state.saved_strategies.append(
            {
                "name": save_name,
                "ticker": ticker,
                "legs": legs,
                "saved_at": datetime.utcnow().isoformat(timespec="seconds"),
            }
        )
        st.success("Saved to this browser session.")

    if st.session_state.saved_strategies:
        st.markdown("### Saved in this session")
        st.json(st.session_state.saved_strategies)


# ============================================================
# VOLATILITY LAB
# ============================================================
elif page == "📉 Volatility Lab":
    st.subheader("Volatility Lab")

    if close_prices.empty:
        st.warning("Historical prices are unavailable.")
    else:
        returns = np.log(close_prices / close_prices.shift(1)).dropna()
        windows = [10, 20, 30, 60]
        data = {}

        for window in windows:
            if len(returns) >= window:
                data[f"{window}D HV"] = returns.rolling(window).std() * np.sqrt(252)

        vol_df = pd.DataFrame(data).dropna(how="all")

        fig = go.Figure()
        for col in vol_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=vol_df.index,
                    y=vol_df[col] * 100,
                    mode="lines",
                    name=col,
                )
            )
        fig.update_layout(
            title=f"Historical volatility — {ticker}",
            yaxis_title="Annualised volatility (%)",
            height=480,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            vol_df.tail(20).round(4),
            use_container_width=True,
        )


# ============================================================
# EDUCATION
# ============================================================
elif page == "📚 Quant Education":
    st.subheader("Quant Education")

    lessons = {
        "Black-Scholes": """
Black-Scholes is a foundational model for European option valuation.
Its assumptions include continuous trading, log-normal price dynamics,
constant volatility and a simplified treatment of interest rates.
""",
        "Greeks": """
Delta measures first-order sensitivity to the underlying. Gamma measures
the change in delta. Vega measures sensitivity to volatility. Theta
approximates time decay and Rho measures sensitivity to interest rates.
""",
        "Binomial Models": """
A binomial tree models discrete up/down movements. For American options,
backward induction can compare continuation value with immediate exercise
value at each node.
""",
        "Volatility": """
Historical volatility is estimated from observed returns. Implied
volatility is a market-derived parameter obtained by solving a pricing
model against an observed option price.
""",
        "Strategy Risk": """
A strategy's payoff depends on every leg, including side, strike,
quantity and premium. Expiration payoff is not the same thing as the
full mark-to-market value before expiration.
""",
    }

    lesson = st.selectbox("Lesson", list(lessons))
    st.markdown(lessons[lesson])

    st.info(
        "Educational content is not personalised financial advice."
    )


# ============================================================
# PRICING
# ============================================================
elif page == "💳 Pricing":
    st.subheader("Simple global pricing")

    p1, p2, p3, p4 = st.columns(4)

    with p1:
        st.markdown("### FREE\n**R0 / month**")
        st.write("Core calculators, basic analytics and Strategy Lab.")
        st.button("Start Free", key="free_button")

    with p2:
        st.markdown("### PRO\n**R149 / month**")
        st.write(
            "Unlimited analyses, saved workspaces and advanced analytics."
        )
        st.button("Choose Pro", key="pro_button")

    with p3:
        st.markdown("### PRO+\n**R399 / month**")
        st.write(
            "Backtesting, portfolio risk and advanced research features."
        )
        st.button("Choose Pro+", key="proplus_button")

    with p4:
        st.markdown("### INSTITUTIONAL\n**From R900 / month**")
        st.write(
            "Team, university and research workspaces with institutional "
            "features."
        )
        st.button("Contact", key="institutional_button")

    st.warning(
        "Payment processing is intentionally not activated in this MVP. "
        "Connect Paystack only after server-side transaction verification, "
        "subscription entitlement and webhook handling are implemented."
    )


# ============================================================
# POLICIES
# ============================================================
elif page == "📄 Policies":
    st.subheader("Customer Policies")

    st.markdown("""
### Service

QuantOptions is a digital quantitative-finance analytics platform.
Customers pay for access to software, analytical tools, research and
educational functionality.

### Refunds

Digital subscription fees are generally non-refundable after premium
access begins, subject to applicable consumer law and exceptions such
as duplicate or erroneous payments.

### Cancellation

Recurring subscriptions can be cancelled before the next billing
date. Cancellation normally prevents future billing rather than
refunding a period already started, subject to applicable law.

### Terms

The platform provides analytics and education. It does not provide
personalised investment advice or guarantee profits. Market data can
be delayed or inaccurate. Customers remain responsible for their own
financial decisions.

### Privacy

Customer information should be processed only as reasonably necessary
to operate accounts, subscriptions, support, security and legal
compliance. Payment-card details should be handled by the payment
provider rather than stored by the application.

### Contact

Publish a real support email and legal business details here before
launching paid subscriptions.
""")

st.caption(
    "These policy summaries are product drafts and should be reviewed "
    "for the final business entity, jurisdiction and applicable law."
)


# ============================================================
# FOOTER
# ============================================================
st.markdown("---")
st.caption(
    "© 2026 QuantOptions. Quantitative analytics, research and education. "
    "Not investment advice. Market data may be delayed or unavailable."
)

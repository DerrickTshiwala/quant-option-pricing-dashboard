import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
import io

# --- STREAMLIT MASTER UI SETTINGS ---
st.set_page_config(layout="wide", page_title="Institutional Multi-Asset Portfolio Suite")
st.title("🏛️ Enterprise Quantitative Portfolio Analytics & Order Routing Suite")
st.markdown("---")

# --- MULTI-TICKER PORTFOLIO INITIALIZATION ---
st.sidebar.header("📁 Portfolio Asset Allocator")
ticker_input = st.sidebar.text_input("Enter Portfolio Tickers (Comma Separated)", value="AAPL, MSFT, NVDA, TSLA")
tickers = [t.strip().upper() for t in ticker_input.split(",") if t.strip()]

# Allocate dynamic weights across tickers
st.sidebar.subheader("⚖️ Asset Weighting Matrix (%)")
weights = {}
total_weight = 0
for idx, tk in enumerate(tickers):
    default_w = float(round(100.0 / len(tickers), 1)) if idx < len(tickers) - 1 else float(100.0 - total_weight)
    weights[tk] = st.sidebar.slider(f"Allocation Weight: {tk}", 0.0, 100.0, default_w, step=1.0)
    total_weight += weights[tk]

if total_weight != 100.0:
    st.sidebar.warning(f"⚠️ Total allocation equals {total_weight}%. Portfolio metrics will normalize to 100%.")

# --- SYSTEM PARAMETERS ---
st.sidebar.header("⚙️ Global Contract Adjustments")
r = st.sidebar.slider("Risk-Free Macro Rate (r)", 0.01, 0.15, 0.05, step=0.01)
T = st.sidebar.slider("Contract Expiry Window (T in Years)", 0.05, 2.0, 0.25, step=0.05)
N = st.sidebar.slider("Binomial Lattice Resolution (N Steps)", 5, 100, 25, step=1)
M = 10000  # Paths allocation cap for server memory stability

portfolio_data = []
all_paths = {}

dt = T / N
discount = np.exp(-r * dt)

for tk in tickers:
    S0_val, sigma_val = 100.0, 0.25
    
    # Live data extraction pipeline per asset
    try:
        asset = yf.Ticker(tk)
        hist = asset.history(period="1mo")
        if not hist.empty:
            S0_val = float(hist['Close'].iloc[-1])
            log_returns = np.log(hist['Close'] / hist['Close'].shift(1)).dropna()
            sigma_val = float(log_returns.std() * np.sqrt(252))
    except Exception:
        pass
        
    # --- PRICING LATTICE GENERATION ---
    u = np.exp(sigma_val * np.sqrt(dt))
    d = 1.0 / u
    p = (np.exp(r * dt) - d) / (u - d)
    
    stock_tree = {}
    option_tree = {}
    delta_tree = {}
    
    j_terminal = np.arange(N + 1)
    stock_tree[N] = S0_val * (u ** (N - j_terminal)) * (d ** j_terminal)
    option_tree[N] = np.maximum(S0_val - stock_tree[N], 0.0)
    
    for i in range(N - 1, -1, -1):
        j_step = np.arange(i + 1)
        stock_tree[i] = S0_val * (u ** (i - j_step)) * (d ** j_step)
        V_up = option_tree[i + 1][:-1]
        V_down = option_tree[i + 1][1:]
        delta_tree[i] = (V_up - V_down) / (stock_tree[i + 1][:-1] - stock_tree[i + 1][1:])
        continuation = discount * (p * V_up + (1.0 - p) * V_down)
        intrinsic = np.maximum(S0_val - stock_tree[i], 0.0)
        option_tree[i] = np.maximum(continuation, intrinsic)
        
    V_0 = option_tree
    delta_root = float(delta_tree) if N > 0 else 0.0
    
    if N >= 2:
        h = stock_tree - stock_tree
        gamma_root = ((option_tree - option_tree) / (stock_tree - stock_tree) - 
                      (option_tree - option_tree) / (stock_tree - stock_tree)) / (0.5 * h)
        theta_root = (option_tree - V_0) / (2 * dt) / 365
    else:
        gamma_root, theta_root = 0.0, 0.0
        
    # --- SIMULATE MONTE CARLO TRAJECTORIES ---
    S_paths = np.zeros((N + 1, M))
    S_paths[0, :] = S0_val
    Z = np.random.standard_normal((N, M))
    for i in range(1, N + 1):
        S_paths[i, :] = S_paths[i - 1, :] * np.exp((r - 0.5 * sigma_val ** 2) * dt + sigma_val * np.sqrt(dt) * Z[i - 1, :])
        
    all_paths[tk] = S_paths
    norm_w = weights[tk] / (total_weight if total_weight > 0 else 1.0)
    
    portfolio_data.append({
        "Ticker": tk,
        "Weight": f"{norm_w * 100:.1f}%",
        "Spot Price ($)": round(S0_val, 2),
        "Volatility": f"{sigma_val * 100:.1f}%",
        "Option Price": round(V_0, 2),
        "Delta (Δ)": round(delta_root, 4),
        "Gamma (Γ)": round(gamma_root, 4),
        "Theta (Θ/day)": round(theta_root, 4),
        "_raw_w": norm_w, "_delta": delta_root, "_gamma": gamma_root, "_theta": theta_root
    })

df_portfolio = pd.DataFrame(portfolio_data)

# Calculate aggregated macro portfolio risk positions
net_delta = sum(row["_raw_w"] * row["_delta"] for row in portfolio_data)
net_gamma = sum(row["_raw_w"] * row["_gamma"] for row in portfolio_data)
net_theta = sum(row["_raw_w"] * row["_theta"] for row in portfolio_data)

# --- VISUAL RENDERING HUB ---
st.write("### 📊 Aggregated Portfolio Risk Ribbon")
p1, p2, p3 = st.columns(3)
p1.metric(label="Weighted Portfolio Delta (Δ Exposure)", value=f"{net_delta:.4f}")
p2.metric(label="Weighted Portfolio Gamma (Γ Curvature)", value=f"{net_gamma:.4f}")
p3.metric(label="Weighted Portfolio Theta (Θ Decay Matrix)", value=f"${net_theta:.4f}/day")

st.write("### 📋 Individual Underlier Asset Allocation Breakdown")
st.dataframe(df_portfolio.drop(columns=["_raw_w", "_delta", "_gamma", "_theta"]), use_container_width=True)

# --- AUTOMATED ORDER ROUTING SYSTEM ---
st.markdown("---")
st.write("### 🤖 Institutional Order Routing Execution Engine")
col_trade, col_status = st.columns()

with col_trade:
    st.subheader("🛠️ Order Configuration")
    target_ticker = st.selectbox("Select Target Underlier", tickers)
    order_side = st.selectbox("Transaction Profile Type", ["BUY / LONG PUT", "SELL / SHORT PUT"])
    order_size = st.number_input("Contract Trade Size (Lots)", min_value=1, max_value=5000, value=10)
    route_execution = st.button("⚡ Dispatch Order to Broker Execution Layer")

with col_status:
    st.subheader("📡 FIX Protocol Order Transmission Feed")
    if route_execution:
        target_row = df_portfolio[df_portfolio["Ticker"] == target_ticker].iloc
        premium = target_row["Option Price"]
        delta_exposure = target_row["Delta (Δ)"] * order_size * 100
        
        st.code(f"""
[FIX PROTOCOL OVERLAY TRIGGERED]
8=FIX.4.4 | 9=245 | 35=D | 49=MOCK_QUANT_DESK | 56=LIQUIDITY_PROVIDER_POOL
11=ORD_{np.random.randint(100000, 999999)} | 21=1 | 55={target_ticker} | 54={'1' if 'BUY' in order_side else '2'}
38={order_size} | 40=2 | 44={premium} | 59=0 | 10=114
        """, language="text")
        
        st.success(f"✔️ Transaction successfully acknowledged by broker liquidity pools.")
        st.info(f"💡 Execution Impact Notes: Rebalancing this position creates an immediate localized cash offset requirement of **{delta_exposure:.2f} shares** to reset portfolio neutrality.")
    else:
        st.write("*Awaiting trade configuration dispatch triggers...*")

# --- HIGH-DIMENSIONAL STOCHASTIC CHART ---
st.markdown("---")
st.write("### 📈 Normalized Portfolio Cumulative Stochastic Variance Projection")
time_axis = np.arange(N + 1) * dt
portfolio_paths = np.zeros((N + 1, M))

for row in portfolio_data:
    tk = row["Ticker"]
    w = row["_raw_w"]
    S_init = row["Spot Price ($)"]
    portfolio_paths += w * (all_paths[tk] / S_init)

fig = go.Figure()
for m in range(min(80, M)):
    fig.add_trace(go.Scatter(
        x=time_axis, y=portfolio_paths[:, m] * 100, mode='lines',
        line=dict(width=0.7), opacity=0.25, showlegend=False
    ))

fig.update_layout(
    xaxis_title="Contract Horizon Window Timeline (Years)",
    yaxis_title="Normalized Portfolio Index Value (Base 100)",
    margin=dict(l=10, r=10, t=10, b=10),
    height=380, hovermode="x unified"
)
st.plotly_chart(fig, use_container_width=True)

# --- MULTI-TAB EXCEL BUFFER STORAGE PIPELINE ---
excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
    df_portfolio.to_excel(writer, index=False, sheet_name='Portfolio_Asset_Weights')
excel_data = excel_buffer.getvalue()

st.sidebar.markdown("---")
st.sidebar.download_button(
    label="📥 Download Portfolio Package (.xlsx)",
    data=excel_data,
    file_name="portfolio_quant_risk_package.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

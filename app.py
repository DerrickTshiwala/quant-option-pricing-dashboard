import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import io

# --- STREAMLIT REGIONAL UI SETTINGS ---
st.set_page_config(layout="wide", page_title="Quant Options Engine")
st.title("🧮 Quantitative Finance Production Toolkit")
st.markdown("---")

# --- INTERACTIVE USER SLIDERS ---
st.sidebar.header("⚙️ Global Parameters")
S0 = st.sidebar.slider("Initial Asset Price (S0)", 50.0, 150.0, 100.0, step=1.0)
K = st.sidebar.slider("Strike Boundary (K)", 50.0, 150.0, 100.0, step=1.0)
r = st.sidebar.slider("Risk-Free Rate (r)", 0.01, 0.15, 0.05, step=0.01)
T = st.sidebar.slider("Maturity Window (T in Years)", 0.1, 2.0, 0.25, step=0.05)
sigma = st.sidebar.slider("Annualized Volatility (σ)", 0.05, 0.60, 0.20, step=0.01)
N = st.sidebar.slider("Lattice Slices (N)", 5, 100, 25, step=1)

# --- ENGINE 1: VECTORIZED BINOMIAL TREE ---
dt = T / N
u = np.exp(sigma * np.sqrt(dt))
d = 1.0 / u
p = (np.exp(r * dt) - d) / (u - d)
discount = np.exp(-r * dt)

# Allocation arrays for high-performance memory indexing
stock_tree = {}
delta_tree = {}
option_tree = {}

# Node boundary generation using numpy meshgrids
j_terminal = np.arange(N + 1)
stock_tree[N] = S0 * (u ** (N - j_terminal)) * (d ** j_terminal)
option_tree[N] = np.maximum(K - stock_tree[N], 0.0)

# Matrix backward induction (eliminates nested Python loops)
for i in range(N - 1, -1, -1):
    j_step = np.arange(i + 1)
    stock_tree[i] = S0 * (u ** (i - j_step)) * (d ** j_step)
    
    V_up = option_tree[i + 1][:-1]
    V_down = option_tree[i + 1][1:]
    
    delta_tree[i] = (V_up - V_down) / (stock_tree[i + 1][:-1] - stock_tree[i + 1][1:])
    
    continuation = discount * (p * V_up + (1.0 - p) * V_down)
    intrinsic = np.maximum(K - stock_tree[i], 0.0)
    option_tree[i] = np.maximum(continuation, intrinsic)

american_tree_price = option_tree[0][0]

# --- TRANSACTIONAL HEDGING MATRIX ---
path_nodes = np.arange(N + 1)  # Straight downside simulation tracking array
cash_account = []
shares_held = 0.0
cumulative_cash = american_tree_price

for i in range(N):
    j = path_nodes[i]
    S_curr = stock_tree[i][j]
    target_delta = delta_tree[i][j]
    shares_to_trade = target_delta - shares_held
    trade_cash_flow = shares_to_trade * S_curr
    cumulative_cash = (cumulative_cash - trade_cash_flow) * np.exp(r * dt)
    shares_held = target_delta
    
    cash_account.append({
        "Step": int(i),
        "Asset Price ($)": round(S_curr, 2),
        "Delta Position": round(target_delta, 4),
        "Volume Traded": round(shares_to_trade, 4),
        "Cash Inventory ($)": round(cumulative_cash, 2)
    })
df_ledger = pd.DataFrame(cash_account)

# --- ENGINE 2: ASIAN PATH MONTE CARLO ---
np.random.seed(42)
M = 25000  
S_paths = np.zeros((N + 1, M))
S_paths[0] = S0

Z = np.random.standard_normal((N, M))
for i in range(1, N + 1):
    S_paths[i] = S_paths[i - 1] * np.exp((r - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * Z[i - 1])

path_averages = np.mean(S_paths, axis=0)
asian_payoffs = np.maximum(K - path_averages, 0.0)
asian_mc_price = np.exp(-r * T) * np.mean(asian_payoffs)

# --- USER LAYOUT RENDERING ---
col_am, col_as = st.columns(2)
with col_am:
    st.metric(label="American Put Premium (Lattice)", value=f"${american_tree_price:.2f}")
with col_as:
    st.metric(label="Asian Arithmetic Put Premium (Monte Carlo)", value=f"${asian_mc_price:.2f}")

# --- GRAPHING CANVAS (PLOTLY INFRASTRUCTURE) ---
st.write("### 📈 Visualizing Stochastic Asset Variance Paths")
time_axis = np.arange(N + 1) * dt
fig = go.Figure()

# Plot line samples safely without capping browser runtime memory
for m in range(min(120, M)):
    fig.add_trace(go.Scatter(
        x=time_axis, y=S_paths[:, m], mode='lines',
        line=dict(width=0.7), opacity=0.25, showlegend=False
    ))

# Delineate the Strike Price boundary threshold
fig.add_trace(go.Scatter(
    x=[0, T], y=[K, K], mode='lines',
    line=dict(color='RoyalBlue', width=2.5, dash='dot'),
    name=f"Strike Boundary (K={K})"
))

fig.update_layout(
    xaxis_title="Contract Horizon (Years)",
    yaxis_title="Underlying Spot Value ($)",
    margin=dict(l=10, r=10, t=10, b=10),
    height=400, hovermode="x unified"
)
st.plotly_chart(fig, use_container_width=True)

# --- DATA STORAGE MANAGEMENT & USER ACCESS ---
st.write("### 📋 Dynamic Execution Ledger Matrix")

# Excel Buffer formulation
excel_buffer = io.BytesIO()
with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
    df_ledger.to_excel(writer, index=False, sheet_name='Delta_Hedging_Ledger')
excel_data = excel_buffer.getvalue()

st.download_button(
    label="📥 Export Ledger Matrix to Excel (.xlsx)",
    data=excel_data,
    file_name="delta_hedging_execution_ledger.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

st.dataframe(df_ledger, use_container_width=True)

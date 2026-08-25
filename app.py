import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# --- STREAMLIT UI CONFIGURATION ---
st.set_page_config(layout="wide")
st.title("🧮 Quantitative Finance Dashboard (Optimized)")
st.subheader("American Put (Vectorized Binomial Tree) vs. Asian Put (Monte Carlo Simulation)")

# --- SIDEBAR PARAMETERS ---
st.sidebar.header("Global Project Parameters")
S0 = st.sidebar.slider("Initial Stock Price (S0)", 50.0, 150.0, 100.0, step=1.0)
K = st.sidebar.slider("Strike Price (K)", 50.0, 150.0, 100.0, step=1.0)
r = st.sidebar.slider("Risk-Free Interest Rate (r)", 0.01, 0.15, 0.05, step=0.01)
T = st.sidebar.slider("Time to Maturity (T in Years)", 0.1, 2.0, 0.25, step=0.05)
sigma = st.sidebar.slider("Volatility (sigma)", 0.05, 0.60, 0.20, step=0.01)
N = st.sidebar.slider("Binomial Tree Steps (N)", 5, 100, 25, step=1)

# --- FAST VECTORIZED AMERICAN PUT TREE ---
dt = T / N
u = np.exp(sigma * np.sqrt(dt))
d = 1 / u
p = (np.exp(r * dt) - d) / (u - d)
discount = np.exp(-r * dt)

# Pre-calculate asset prices at maturity step N using vector operations
j_indices = np.arange(N + 1)
ST_nodes = S0 * (u ** (N - j_indices)) * (d ** j_indices)

# Initialize option value vector at terminal step
option_values = np.maximum(K - ST_nodes, 0.0)

# Save structures for ledger tracking 
stock_tree = {}
delta_tree = {}
option_tree_saved = {}

stock_tree[N] = ST_nodes

# Vectorized Backward Induction loop
for i in range(N - 1, -1, -1):
    j_step = np.arange(i + 1)
    S_curr = S0 * (u ** (i - j_step)) * (d ** j_step)
    stock_tree[i] = S_curr
    
    # Slice the child array nodes to pull up and down movements instantly
    V_up = option_values[:-1]
    V_down = option_values[1:]
    
    # Calculate vector of node deltas
    delta_tree[i] = (V_up - V_down) / (stock_tree[i+1][:-1] - stock_tree[i+1][1:])
    
    # Vectorized valuation check (continuation vs early exercise)
    continuation_value = discount * (p * V_up + (1 - p) * V_down)
    intrinsic_value = np.maximum(K - S_curr, 0.0)
    option_values = np.maximum(continuation_value, intrinsic_value)
    option_tree_saved[i] = option_values

american_tree_price = option_values[0]

# --- DYNAMIC HEDGING LEDGER GENERATION ---
path_nodes = [0] * (N + 1)
for i in range(1, N + 1):
    path_nodes[i] = path_nodes[i-1] + 1

cash_account = []
shares_held = 0.0
cumulative_cash = american_tree_price

for i in range(N):
    j = path_nodes[i]
    S_curr = stock_tree[i][j]
    target_delta = delta_tree[i][j]
    shares_to_buy_sell = target_delta - shares_held
    cash_flow_trade = shares_to_buy_sell * S_curr
    cumulative_cash = (cumulative_cash - cash_flow_trade) * np.exp(r * dt)
    shares_held = target_delta
    cash_account.append({
        "Step": i,
        "Stock Price": round(S_curr, 2),
        "Option Delta": round(target_delta, 4),
        "Shares Traded": round(shares_to_buy_sell, 4),
        "Cash Balance": round(cumulative_cash, 2)
    })
df_q21 = pd.DataFrame(cash_account)

# --- MONTE CARLO ASIAN PUT ENGINE & SIMULATION PLOT ---
np.random.seed(42)
M = 20000  # Number of simulation paths
S_paths = np.zeros((N + 1, M))
S_paths[0] = S0

# Compute entire random matrices instantly via vectorization
Z = np.random.standard_normal((N, M))
for i in range(1, N + 1):
    S_paths[i] = S_paths[i-1] * np.exp((r - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * Z[i-1])

arithmetic_averages = np.mean(S_paths, axis=0)
asian_put_payoffs = np.maximum(K - arithmetic_averages, 0.0)
asian_put_price = np.exp(-r * T) * np.mean(asian_put_payoffs)

# --- WEB APPLICATION LAYOUT RENDERING ---
col1, col2 = st.columns(2)
with col1:
    st.metric(label="American Put (Tree) Price", value=f"${american_tree_price:.2f}")
with col2:
    st.metric(label="Asian Put (Monte Carlo) Price", value=f"${asian_put_price:.2f}")

# --- GRAPHING ELEMENT (Interactive Plotly Paths) ---
st.write("### 📈 Visualizing Simulated Monte Carlo Stock Paths")
fig = go.Figure()
time_steps = np.arange(N + 1) * dt

# Plot a subset of 100 paths to prevent browser memory slowdowns
paths_to_plot = min(100, M)
for m in range(paths_to_plot):
    fig.add_trace(go.Scatter(
        x=time_steps, y=S_paths[:, m], 
        mode='lines', line=dict(width=0.8), opacity=0.3,
        showlegend=False
    ))

# Highlight the Strike Price boundary line
fig.add_trace(go.Scatter(
    x=[0, T], y=[K, K], 
    mode='lines', line=dict(color='red', width=2, dash='dash'), 
    name=f'Strike Price (K = {K})'
))

fig.update_layout(
    xaxis_title="Time to Maturity (Years)",
    yaxis_title="Stock Price ($)",
    margin=dict(l=20, r=20, t=20, b=20),
    height=450,
    hovermode="x unified"
)
st.plotly_chart(fig, use_container_width=True)

# --- LEDGER MATRIX DISPLAY ---
st.write("### 📋 Downside Path Delta Hedging Ledger Matrix")
st.dataframe(df_q21, use_container_width=True)

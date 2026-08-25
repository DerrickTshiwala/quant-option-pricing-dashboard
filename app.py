import numpy as np
import pandas as pd
import streamlit as st

# --- STREAMLIT UI CONFIGURATION ---
st.set_page_config(layout="wide")
st.title("🧮 Quantitative Finance Dashboard")
st.subheader("American Put (Binomial Tree) vs. Asian Put (Monte Carlo)")

# --- SIDEBAR PARAMETERS ---
st.sidebar.header("Global Project Parameters")
S0 = st.sidebar.slider("Initial Stock Price (S0)", 50.0, 150.0, 100.0, step=1.0)
K = st.sidebar.slider("Strike Price (K)", 50.0, 150.0, 100.0, step=1.0)
r = st.sidebar.slider("Risk-Free Interest Rate (r)", 0.01, 0.15, 0.05, step=0.01)
T = st.sidebar.slider("Time to Maturity (T in Years)", 0.1, 2.0, 0.25, step=0.05)
sigma = st.sidebar.slider("Volatility (sigma)", 0.05, 0.60, 0.20, step=0.01)
N = st.sidebar.slider("Binomial Tree Steps (N)", 5, 50, 25, step=1)

# --- MATH CORE (Your original logic modified to use sliders) ---
dt = T / N
u = np.exp(sigma * np.sqrt(dt))
d = 1 / u
p = (np.exp(r * dt) - d) / (u - d)
discount = np.exp(-r * dt)

stock_tree = {}
option_tree = {}
delta_tree = {}

for i in range(N + 1):
    stock_tree[i] = np.array([S0 * (u ** (i - j)) * (d ** j) for j in range(i + 1)])

option_tree[N] = np.maximum(K - stock_tree[N], 0.0)

for i in range(N - 1, -1, -1):
    option_tree[i] = np.zeros(i + 1)
    delta_tree[i] = np.zeros(i + 1)
    for j in range(i + 1):
        S_up = stock_tree[i+1][j]
        S_down = stock_tree[i+1][j+1]
        V_up = option_tree[i+1][j]
        V_down = option_tree[i+1][j+1]
        delta_tree[i][j] = (V_up - V_down) / (S_up - S_down)
        
        continuation_value = discount * (p * V_up + (1 - p) * V_down)
        intrinsic_value = max(K - stock_tree[i][j], 0.0)
        option_tree[i][j] = max(continuation_value, intrinsic_value)

# Generate Hedging Path Ledger
path_nodes = [0] * (N + 1)
for i in range(1, N + 1):
    path_nodes[i] = path_nodes[i-1] + 1

cash_account = []
shares_held = 0.0
cumulative_cash = option_tree[0][0]

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

# Monte Carlo Engine for Asian Option
np.random.seed(42)
M = 30000 # Reduced slightly for faster web rendering
S_paths = np.zeros((N + 1, M))
S_paths[0] = S0
for i in range(1, N + 1):
    Z = np.random.standard_normal(M)
    S_paths[i] = S_paths[i-1] * np.exp((r - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * Z)

arithmetic_averages = np.mean(S_paths, axis=0)
asian_put_payoffs = np.maximum(K - arithmetic_averages, 0.0)
asian_put_price = np.exp(-r * T) * np.mean(asian_put_payoffs)

# --- DISPLAY OUTPUTS IN COLS ---
col1, col2 = st.columns(2)
with col1:
    st.metric(label="American Put (Tree) Price", value=f"${option_tree[0][0]:.2f}")
with col2:
    st.metric(label="Asian Put (Monte Carlo) Price", value=f"${asian_put_price:.2f}")

st.write("### Downside Path Delta Hedging Ledger")
st.dataframe(df_q21, use_container_width=True)

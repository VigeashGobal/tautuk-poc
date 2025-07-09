import streamlit as st, pandas as pd, numpy as np, time, datetime, random
from streamlit_autorefresh import st_autorefresh
import openai_helper

# ---- custom CSS ----
st.markdown("""
<style>
/* global tweaks */
section.main > div {padding-top: 1rem;}  /* tighter spacing */
/* metric tiles glass effect */
[data-testid="stMetric"] {
  border: 1px solid rgba(255,255,255,0.6);
  background: rgba(255,255,255,0.55);
  backdrop-filter: blur(10px);
  border-radius: 14px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.03);
  padding: 1.2rem 0.8rem;
}
/* buttons */
button[kind="secondary"] {
  border-radius: 8px;
  padding: 0.4rem 0.9rem;
}
/* sidebar list bullets → nice checkmarks */
.sidebar-content ul li::marker {
  color: #0E6BA8;
  content: "✓ ";
}
</style>
""", unsafe_allow_html=True)

# ---------- config ----------
ROOMS   = ["Office A", "Office B", "Lab"]
METRICS = ["co2", "temp", "rh", "pm"]
REFRESH_MS = 1_000   # 1 s

# ---------- helpers ----------
def init_state():
    if "data" not in st.session_state:
        st.session_state.data = pd.DataFrame(columns=["ts", "room", *METRICS])

def generate_reading(force_high_co2=False):
    return {
        "ts": datetime.datetime.utcnow(),
        "room": random.choice(ROOMS),
        "co2": 1200 if force_high_co2 else np.random.normal(650, 120),
        "temp": np.random.uniform(20, 27),
        "rh": np.random.uniform(35, 60),
        "pm": abs(np.random.normal(12, 6)),
    }

# ---------- page setup ----------
st.set_page_config(page_title="Tautuk POC", layout="wide")
init_state()

# auto-refresh (returns a counter we could use if needed)
st_autorefresh(interval=REFRESH_MS, key="auto")

st.sidebar.markdown("### Why it matters")
st.sidebar.write(
    "- Boost productivity by preventing stale air\n"
    "- Cut HVAC energy with demand-based ventilation\n"
    "- Auto-document IAQ compliance"
)
demo_toggle = st.sidebar.checkbox("💡 Force high CO₂ demo", value=False)

# --------- create a new reading each run ---------
st.session_state.data.loc[len(st.session_state.data)] = generate_reading(demo_toggle)

# keep last 1440 rows (~24 h @1 min) to limit memory
if len(st.session_state.data) > 1440:
    st.session_state.data = st.session_state.data.iloc[-1440:]

st.title("Tautuk – Operational Resource Intelligence (POC)")

latest = st.session_state.data.iloc[-1]
cols = st.columns(4)
cols[0].metric("CO₂ (ppm)",     f"{latest.co2:.0f}")
cols[1].metric("Temp (°C)",     f"{latest.temp:.1f}")
cols[2].metric("Humidity (%)",  f"{latest.rh:.0f}")
cols[3].metric("PM2.5 (µg/m³)", f"{latest.pm:.1f}")

if latest.co2 > 1000:
    st.error(f"⚠️ High CO₂ in {latest.room} — {latest.co2:.0f} ppm!")

with st.expander("24-hour trends", expanded=False):
    if len(st.session_state.data) > 0:
        chart = st.session_state.data.set_index("ts")[METRICS]
        st.line_chart(chart)
    else:
        st.info("No data yet - chart will appear once readings are collected")

# --- AI insight panel ---
st.markdown("### 🧠 AI-Generated Insights (updates every 5 min)")
if st.button("🔄 Refresh insights"):
    openai_helper._CACHE["ts"] = None  # invalidate cache
st.markdown(openai_helper.generate_insight(st.session_state.data))

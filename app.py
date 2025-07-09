import streamlit as st, pandas as pd, numpy as np, time, datetime, random
from streamlit_autorefresh import st_autorefresh
import openai_helper
from collections import OrderedDict

# ---- custom CSS ----
st.markdown("""
<style>
/* Remove Streamlit padding */
section.main > div:first-child {padding-top: 0.5rem;}
/* Card grid */
.card-grid {display: grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); gap: 1.25rem; margin: 1.2rem 0;}
.metric-card {background: var(--secondary-background-color); border-radius: 14px; box-shadow: 0 4px 18px rgba(0,0,0,0.04); padding: 1.1rem 1rem; text-align: center; transition: transform .15s;}
.metric-card:hover {transform: translateY(-2px);}
.metric-label {font-size: 0.82rem; color: #5e5e5e; letter-spacing: 0.2px; margin-bottom: 4px;}
.metric-value {font-size: 2.2rem; font-weight: 600; margin-bottom: 0;}
.metric-unit {font-size: 0.80rem; color: #7a7a7a;}
.metric-border {height: 4px; width: 100%; border-radius: 4px 4px 0 0; margin: -1.1rem -1rem 0.9rem;}
/* Status badge */
.badge {display: inline-block; padding: 0.25rem 0.65rem; border-radius: 999px; font-size: 0.78rem; font-weight: 600; color:#fff;}
</style>
""", unsafe_allow_html=True)

# ---------- helpers ----------
STATUS_COLORS = OrderedDict([
    ("good",  "#2ecc71"),   # green
    ("warn",  "#f1c40f"),   # amber
    ("bad",   "#e74c3c"),   # red
])

def status_color(metric, value):
    if metric == "co2":
        return "bad"  if value > 1000 else "warn" if value > 800 else "good"
    if metric == "temp":
        return "bad"  if value < 18 or value > 27 else "warn" if value < 20 or value > 25 else "good"
    if metric == "rh":
        return "bad"  if value < 30 or value > 70 else "warn" if value < 35 or value > 60 else "good"
    if metric == "pm":
        return "bad"  if value > 35 else "warn" if value > 12 else "good"
    return "good"

def overall_iaq_status(row):
    score = sum(status_color(m, row[m]) != "good" for m in ["co2","temp","rh","pm"])
    return "bad" if score >=2 else "warn" if score ==1 else "good"

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

badge = overall_iaq_status(latest)
color = STATUS_COLORS[badge]
st.markdown(f"<span class=\"badge\" style=\"background:{color}\">Overall Air Quality: {badge.upper()}</span>", unsafe_allow_html=True)

st.markdown("<div class=\"card-grid\">", unsafe_allow_html=True)
for m,label,unit in [
  ("co2","CO₂","ppm"),
  ("temp","Temp","°C"),
  ("rh","Humidity","%"),
  ("pm","PM2.5","µg/m³")]:
    state = status_color(m, latest[m])
    bar  = STATUS_COLORS[state]
    val  = f"{latest[m]:.1f}" if m!="co2" else f"{latest[m]:.0f}"
    st.markdown(
        f"""
        <div class='metric-card'>
          <div class='metric-border' style='background:{bar}'></div>
          <div class='metric-label'>{label}</div>
          <div class='metric-value'>{val} <span class='metric-unit'>{unit}</span></div>
        </div>
        """, unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# ----- alert banner remains unchanged
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

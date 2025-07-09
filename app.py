import streamlit as st, pandas as pd, numpy as np, time, datetime, random
from streamlit_autorefresh import st_autorefresh
import openai_helper
from collections import OrderedDict

# ---- custom CSS ----
st.markdown("""
<style>
html,body{overflow-x:hidden;} section.main>div{padding-top:.3rem;padding-bottom:.3rem;}
h1{font-size:2.1rem;margin:0.4rem 0 0.8rem;} .card-grid{margin:0.6rem 0;gap:0.9rem;}
.badge{margin-top:0.3rem;}
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
REFRESH_MS = 2000   # 2 s

# ---------- helpers ----------
def init_state():
    if "data" not in st.session_state:
        st.session_state.data = pd.DataFrame(columns=["ts", "room", *METRICS])

def generate_reading(force_high_co2=False):
    """AR(1)-style drift so values change smoothly"""
    base = st.session_state.get("last_reading", {
        "co2":650, "temp":23, "rh":50, "pm":10
    })
    nxt = {
        "co2": (0.9*base["co2"] + np.random.normal(0,15)) if not force_high_co2 else 1200,
        "temp": (0.9*base["temp"] + np.random.normal(0,0.3)),
        "rh"  : (0.9*base["rh"]  + np.random.normal(0,1.0)),
        "pm"  : max(0, 0.8*base["pm"] + np.random.normal(0,1))
    }
    st.session_state.last_reading = nxt
    return {
        "ts": datetime.datetime.utcnow(),
        "room": random.choice(ROOMS),
        **nxt,
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

container = st.container()
left,right = container.columns([2,1])
with left:
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

with right:
    st.markdown("### 🧠 AI Insights")
    if st.button("🔄 Refresh insights"):
        openai_helper._CACHE["ts"] = None
    st.markdown(openai_helper.generate_insight(st.session_state.data))

# --- chart and extras below ---

with st.expander("24-hour trends", expanded=False):
    if len(st.session_state.data) > 0:
        chart = st.session_state.data.set_index("ts")[METRICS]
        st.line_chart(chart, height=180)
    else:
        st.info("No data yet - chart will appear once readings are collected")

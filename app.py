import streamlit as st, pandas as pd, numpy as np, time, threading, random, datetime
from streamlit_autorefresh import st_autorefresh

ROOMS = ["Office A", "Office B", "Lab"]
METRICS = ["co2", "temp", "rh", "pm"]

def init_state():
    if "data" not in st.session_state:
        st.session_state.data = pd.DataFrame(columns=["ts", "room", *METRICS])

def simulate():
    while True:
        row = {
            "ts": datetime.datetime.utcnow(),
            "room": random.choice(ROOMS),
            "co2": np.random.normal(650, 120),
            "temp": np.random.uniform(20, 27),
            "rh": np.random.uniform(35, 60),
            "pm": abs(np.random.normal(12, 6)),
        }
        st.session_state.data.loc[len(st.session_state.data)] = row
        time.sleep(1)

# ---------- UI ----------
st.set_page_config(page_title="Tautuk POC", layout="wide")
init_state()

# refresh the page every 1 000 ms so new readings appear
st_autorefresh(interval=1000, key="data_refresh")

# start simulator once
if "sim_thread" not in st.session_state:
    threading.Thread(target=simulate, daemon=True).start()
    st.session_state.sim_thread = True

st.title("Tautuk – Operational Resource Intelligence (POC)")

cols = st.columns(4)
if len(st.session_state.data):
    latest = st.session_state.data.iloc[-1]
    cols[0].metric("CO₂ (ppm)", f"{latest.co2:.0f}")
    cols[1].metric("Temp (°C)", f"{latest.temp:.1f}")
    cols[2].metric("Humidity (%)", f"{latest.rh:.0f}")
    cols[3].metric("PM2.5 (µg/m³)", f"{latest.pm:.1f}")

    if latest.co2 > 1000:
        st.error(f"⚠️ High CO₂ in {latest.room} — {latest.co2:.0f} ppm!")
else:
    for c in cols:
        c.metric("Waiting …", "—")

with st.expander("24-hour trends"):
    chart = st.session_state.data.tail(1440)  # last day @1/min
    st.line_chart(chart.set_index("ts")[METRICS])

st.sidebar.markdown("### Why it matters")
st.sidebar.write("- Boost productivity by preventing stale air\n- Cut HVAC energy with demand-based ventilation\n- Auto-document IAQ compliance")

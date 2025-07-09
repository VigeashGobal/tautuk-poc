import streamlit as st, pandas as pd, numpy as np, time, datetime, random
from streamlit_autorefresh import st_autorefresh
import openai_helper
from collections import OrderedDict
import base64, io, datetime as _dt
from reportlab.pdfgen import canvas
from bs4 import BeautifulSoup

# ### --- helpers: wow section ------------------------------------
def device_health_bar(last_seen_dict, offline_after=8):
    """Return HTML row of dots (green good / gray offline)."""
    now=_dt.datetime.utcnow()
    dot=[]
    for r in ROOMS:
        age=(now-last_seen_dict.get(r,now)).total_seconds()
        color="#2ecc71" if age<offline_after else "#cccccc"
        dot.append(f"<span style='color:{color};font-size:22px;'>●</span>")
    return " ".join(dot)

def floor_svg(colormap):
    """Read assets/floor.svg and recolor each room based on colormap."""
    with open("assets/floor.svg") as f:
        soup=BeautifulSoup(f.read(),"xml")
    for rid,color in colormap.items():
        node=soup.find(id=rid)
        if node: node["fill"]=color
    return soup.decode()

def export_csv(df):
    return df.to_csv(index=False).encode()

def build_pdf(df, overall_status):
    buf=io.BytesIO()
    c=canvas.Canvas(buf,pagesize=(595,842))  # A4-ish
    c.setFont("Helvetica-Bold",20); c.drawString(50,800,"Tautuk IAQ Weekly Report")
    c.setFont("Helvetica",12); c.drawString(50,780,f"Generated: {_dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC")
    c.setFont("Helvetica-Bold",14); c.drawString(50,740,f"Overall status: {overall_status.upper()}")
    y=700; c.setFont("Helvetica",11)
    for m,label in [("co2","CO₂ ppm"),("temp","Temp °C"),("rh","Humidity %"),("pm","PM2.5 µg/m³")]:
        c.drawString(60,y,f"{label}  avg: {df[m].mean():.1f}   max: {df[m].max():.1f}")
        y-=20
    c.showPage(); c.save(); buf.seek(0)
    return buf.read()
# ------------------------------------------------------------------

# ---- custom CSS ----
st.markdown("""
<style>
body::before{content:"";position:fixed;inset:0;background:linear-gradient(120deg,#dff1ff 0%,#f6fbff 50%,#eef7ff 100%);animation:bg 24s infinite ease-in-out alternate;z-index:-1}@keyframes bg{0%{filter:hue-rotate(0deg)}100%{filter:hue-rotate(15deg)}}
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

def generate_reading(force_high_co2=False, force_high_pm=False, force_high_temp=False):
    """
    Mean-reverting random walk:
    - keeps metrics inside "good" band (± small wiggle)
    - big spike only when force_high_* is True
    """
    TARGET = dict(co2=650, temp=23, rh=50, pm=8)   # comfortable mid-points
    SD     = dict(co2=8,   temp=0.25, rh=0.8, pm=0.8)  # noise stdev
    LIMITS = dict(        # clamp to keep status mostly GOOD
        co2=(500, 800),
        temp=(20, 25),
        rh=(35, 60),
        pm=(4, 20),
    )

    base = st.session_state.get("last_reading", TARGET)
    nxt = {}

    for k in TARGET:
        if k == "co2" and force_high_co2:
            nxt[k] = 1200  # trigger alert on cue
            continue
        if k == "pm" and force_high_pm:
            nxt[k] = 40  # high PM2.5
            continue
        if k == "temp" and force_high_temp:
            nxt[k] = 29  # high temp
            continue
        # mean-reversion towards TARGET + small noise
        drift = 0.12 * (TARGET[k] - base[k])
        nxt[k] = base[k] + drift + np.random.normal(0, SD[k])
        # clamp within limits
        low, high = LIMITS[k]
        nxt[k] = max(low, min(high, nxt[k]))

    st.session_state.last_reading = nxt
    return {"ts": datetime.datetime.utcnow(), "room": random.choice(ROOMS), **nxt}

# ---------- page setup ----------
st.set_page_config(page_title="Tautuk POC", layout="wide")
init_state()

# auto-refresh (returns a counter we could use if needed)
st_autorefresh(interval=REFRESH_MS, key="auto")

st.sidebar.markdown("### Why it matters")
st.sidebar.write("- Boost productivity by preventing stale air")
st.sidebar.write("- Cut HVAC energy with demand-based ventilation")
st.sidebar.write("- Auto-document IAQ compliance")

st.title("Tautuk – Operational Resource Intelligence (POC)")

# Tabs for main content
main_tab, floor_tab, trends_tab, roi_tab, report_tab = st.tabs(["Diagnostics & Insights", "Floor Map", "Trends", "ROI & Cost", "Reporting"])

with main_tab:
    # Demo toggles
    st.markdown("#### Demo Conditions")
    col1, col2, col3 = st.columns(3)
    with col1:
        demo_co2 = st.checkbox("💡 Force high CO₂ demo", value=False, key="demo_co2")
    with col2:
        demo_pm = st.checkbox("💡 Force high PM2.5 demo", value=False, key="demo_pm")
    with col3:
        demo_temp = st.checkbox("💡 Force high Temp demo", value=False, key="demo_temp")

    # device health row
    st.markdown(device_health_bar(st.session_state.get("device_last_seen",{})),unsafe_allow_html=True)

    latest = st.session_state.data.iloc[-1]

    badge = overall_iaq_status(latest)
    # Outdoor reference
    OUT_CO2 = 420  # ppm baseline
    co2_delta = latest.co2 - OUT_CO2
    color = STATUS_COLORS[badge]
    st.markdown(f"<span class=\"badge\" style=\"background:{color}\">Overall Air Quality: {badge.upper()}</span> &nbsp;&nbsp; <span style=\"font-size:0.82rem;color:#555\">Indoor-Outdoor ΔCO₂: {co2_delta:.0f} ppm</span>", unsafe_allow_html=True)

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

with floor_tab:
    st.markdown("### Device Health")
    st.markdown(device_health_bar(st.session_state.get("device_last_seen",{})),unsafe_allow_html=True)
    st.markdown("### Floor Map")
    room_colors={r: STATUS_COLORS[status_color("co2", latest.co2)] for r in ROOMS}
    svg= floor_svg(room_colors)
    st.image(svg, use_container_width=True)

with trends_tab:
    st.markdown("### 24-hour Trends")
    with st.expander("Show chart", expanded=True):
        if len(st.session_state.data) > 0:
            chart = st.session_state.data.set_index("ts")[METRICS]
            st.line_chart(chart, height=180)
        else:
            st.info("No data yet - chart will appear once readings are collected")

with roi_tab:
    st.markdown("### ROI & Cost Calculator")
    occ = st.slider("Avg occupants / day",10,500,100)
    rate = st.number_input("Electricity rate  ( ¢ /kWh )",0.05,0.5,0.12)
    annual_save = occ*0.12*rate*240   # rough formula
    st.metric("Est. yearly savings", f"$ {annual_save:,.0f}")

with report_tab:
    st.markdown("### Download Reports")
    if st.button("⬇️ 24h CSV"):
        st.download_button("Download 24h CSV", export_csv(st.session_state.data),"tauk_24h.csv",mime="text/csv",key="csv")
    if st.button("⬇️ 1-week PDF report"):
        badge = overall_iaq_status(latest)
        pdf_bytes=build_pdf(st.session_state.data, badge.upper())
        st.download_button("Download 1-week PDF", pdf_bytes,"tauk_report.pdf",mime="application/pdf",key="pdf")

# --------- create a new reading each run ---------
# simulate 1% chance a sensor skips
row=generate_reading(
    force_high_co2=st.session_state.get("demo_co2", False),
    force_high_pm=st.session_state.get("demo_pm", False),
    force_high_temp=st.session_state.get("demo_temp", False)
)
if random.random()>0.01: st.session_state.data.loc[len(st.session_state.data)] = row
# update last-seen dict
lst=st.session_state.setdefault("device_last_seen",{}); lst[row["room"]]=_dt.datetime.utcnow()

# keep last 1440 rows (~24 h @1 min) to limit memory
if len(st.session_state.data) > 1440:
    st.session_state.data = st.session_state.data.iloc[-1440:]

import time
import warnings
import streamlit as st
import snowflake.connector
import pandas as pd
import pydeck as pdk
import plotly.express as px
import plotly.graph_objects as go

warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="IoT Pipeline Dashboard",
    page_icon="📡",
    layout="wide",
)

REFRESH_SECONDS = 30


def get_connection():
    cfg = st.secrets["snowflake"]
    return snowflake.connector.connect(
        account=cfg["account"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        schema=cfg["schema"],
        warehouse=cfg["warehouse"],
        role=cfg["role"],
    )


def _sql(query):
    conn = get_connection()
    df = pd.read_sql(query, conn)
    conn.close()
    df.columns = [c.lower() for c in df.columns]
    for col in df.columns:
        if col in ("device_id", "event_date", "aqi_severity", "event_ts", "inserted_at"):
            continue
        try:
            df[col] = pd.to_numeric(df[col], errors="ignore")
        except Exception:
            pass
    return df


@st.cache_data(ttl=REFRESH_SECONDS)
def load_kpis():
    return _sql("""
        SELECT
            SUM(event_count)                        AS total_events,
            COUNT(DISTINCT device_id)               AS total_devices,
            ROUND(AVG(avg_aqi), 1)                  AS overall_avg_aqi,
            ROUND(MAX(max_aqi), 1)                  AS peak_aqi,
            ROUND(AVG(avg_temp), 1)                 AS avg_temp_c,
            COUNT(DISTINCT event_date)              AS days_active
        FROM HACKATHON_IOT.ANALYTICS.AGG_DEVICE_DAILY
    """)


@st.cache_data(ttl=REFRESH_SECONDS)
def load_device_map():
    return _sql("""
        SELECT device_id,
               ROUND(AVG(avg_lat), 6)   AS lat,
               ROUND(AVG(avg_long), 6)  AS lon,
               ROUND(AVG(avg_aqi), 1)   AS avg_aqi,
               SUM(event_count)         AS events
        FROM HACKATHON_IOT.ANALYTICS.AGG_DEVICE_DAILY
        GROUP BY device_id
    """)


@st.cache_data(ttl=REFRESH_SECONDS)
def load_aqi_trend():
    return _sql("""
        SELECT device_id, event_date,
               ROUND(avg_aqi, 1) AS avg_aqi,
               ROUND(max_aqi, 1) AS max_aqi
        FROM HACKATHON_IOT.ANALYTICS.AGG_DEVICE_DAILY
        ORDER BY event_date, device_id
    """)


@st.cache_data(ttl=REFRESH_SECONDS)
def load_temp_trend():
    return _sql("""
        SELECT device_id, event_date,
               ROUND(avg_temp, 1) AS avg_temp,
               ROUND(max_temp, 1) AS max_temp
        FROM HACKATHON_IOT.ANALYTICS.AGG_DEVICE_DAILY
        ORDER BY event_date, device_id
    """)


@st.cache_data(ttl=REFRESH_SECONDS)
def load_top_devices():
    return _sql("""
        SELECT device_id,
               SUM(event_count)          AS total_events,
               ROUND(AVG(avg_aqi), 1)    AS avg_aqi,
               ROUND(MAX(max_aqi), 1)    AS peak_aqi,
               ROUND(AVG(avg_temp), 1)   AS avg_temp
        FROM HACKATHON_IOT.ANALYTICS.AGG_DEVICE_DAILY
        GROUP BY device_id
        ORDER BY avg_aqi DESC
    """)


@st.cache_data(ttl=REFRESH_SECONDS)
def load_severity():
    return _sql("""
        SELECT aqi_severity, COUNT(*) AS cnt
        FROM HACKATHON_IOT.CLEAN.STG_IOT_EVENTS
        GROUP BY aqi_severity
        ORDER BY cnt DESC
    """)


@st.cache_data(ttl=REFRESH_SECONDS)
def load_recent():
    return _sql("""
        SELECT device_id,
               TO_CHAR(event_ts, 'YYYY-MM-DD HH24:MI:SS') AS event_ts,
               ROUND(lat, 4)         AS lat,
               ROUND(long, 4)        AS lon,
               ROUND(temperature, 1) AS temp_c,
               ROUND(aqi, 0)         AS aqi,
               aqi_severity
        FROM HACKATHON_IOT.CLEAN.STG_IOT_EVENTS
        ORDER BY event_ts DESC
        LIMIT 20
    """)


# ── Header ──────────────────────────────────────────────────────────────────
st.title("IoT On-Prem to AWS/Snowflake Pipeline")
st.caption(f"Live CDC pipeline: PostgreSQL → Debezium → MSK → Snowflake → dbt | Auto-refreshes every {REFRESH_SECONDS}s")

# ── KPI Row ──────────────────────────────────────────────────────────────────
kpi = load_kpis()
if not kpi.empty:
    r = kpi.iloc[0]
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Total Events",   int(r["total_events"])  if pd.notna(r["total_events"])  else 0)
    k2.metric("Devices",        int(r["total_devices"]) if pd.notna(r["total_devices"]) else 0)
    k3.metric("Avg AQI",        r["overall_avg_aqi"]   if pd.notna(r["overall_avg_aqi"]) else "--")
    k4.metric("Peak AQI",       r["peak_aqi"]          if pd.notna(r["peak_aqi"])        else "--")
    k5.metric("Avg Temp (°C)",  r["avg_temp_c"]        if pd.notna(r["avg_temp_c"])      else "--")
    k6.metric("Days Active",    int(r["days_active"])  if pd.notna(r["days_active"])    else 0)

st.divider()

# ── Row 1: Map + Severity pie + Top devices ───────────────────────────────
c1, c2, c3 = st.columns([2, 1, 1])

with c1:
    st.subheader("Device Location Map")
    df_map = load_device_map()
    if not df_map.empty:
        records = [
            {"device_id": str(r["device_id"]),
             "lat": float(r["lat"]), "lon": float(r["lon"]),
             "avg_aqi": float(r["avg_aqi"]), "events": int(r["events"])}
            for r in df_map.to_dict("records")
        ]
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=records,
            get_position="[lon, lat]",
            get_color="[200, 30, 0, 200]",
            get_radius=8000,
            pickable=True,
        )
        view = pdk.ViewState(
            latitude=float(df_map["lat"].mean()),
            longitude=float(df_map["lon"].mean()),
            zoom=7,
            pitch=0,
        )
        st.pydeck_chart(pdk.Deck(
            layers=[layer],
            initial_view_state=view,
            tooltip={"text": "Device: {device_id}\nAQI: {avg_aqi}\nEvents: {events}"},
            map_style="mapbox://styles/mapbox/dark-v10",
        ))
    else:
        st.info("No location data yet.")

with c2:
    st.subheader("AQI Severity Split")
    df_sev = load_severity()
    if not df_sev.empty:
        color_map = {"good": "#2ecc71", "moderate": "#f39c12", "unhealthy": "#e74c3c"}
        fig = px.pie(df_sev, names="aqi_severity", values="cnt",
                     color="aqi_severity", color_discrete_map=color_map,
                     hole=0.45)
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=320,
                          legend=dict(orientation="h", y=-0.1))
        fig.update_traces(textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No severity data yet.")

with c3:
    st.subheader("Top Devices by AQI")
    df_top = load_top_devices()
    if not df_top.empty:
        fig = px.bar(df_top, x="avg_aqi", y="device_id", orientation="h",
                     color="avg_aqi", color_continuous_scale="Reds",
                     hover_data=["total_events", "peak_aqi", "avg_temp"],
                     text="avg_aqi")
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=320,
                          yaxis=dict(autorange="reversed"),
                          coloraxis_showscale=False)
        fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No device data yet.")

st.divider()

# ── Row 2: AQI trend + Temp trend ────────────────────────────────────────
c4, c5 = st.columns(2)

with c4:
    st.subheader("AQI Trend Over Time")
    df_aqi = load_aqi_trend()
    if not df_aqi.empty:
        fig = px.line(df_aqi, x="event_date", y="avg_aqi", color="device_id",
                      markers=True, title="Average AQI per Device per Day")
        fig.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=300,
                          legend=dict(orientation="h", y=-0.2))
        fig.add_hline(y=100, line_dash="dot", line_color="orange",
                      annotation_text="Moderate threshold")
        fig.add_hline(y=150, line_dash="dot", line_color="red",
                      annotation_text="Unhealthy threshold")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No AQI trend data yet.")

with c5:
    st.subheader("Temperature Trend Over Time")
    df_temp = load_temp_trend()
    if not df_temp.empty:
        fig = px.line(df_temp, x="event_date", y="avg_temp", color="device_id",
                      markers=True, title="Average Temperature (°C) per Device per Day")
        fig.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=300,
                          legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No temperature data yet.")

st.divider()

# ── Row 3: Recent events table ────────────────────────────────────────────
st.subheader("Recent Events (last 20)")
df_recent = load_recent()
if not df_recent.empty:
    def color_severity(val):
        colors = {"good": "background-color:#1e4d2b;color:#2ecc71",
                  "moderate": "background-color:#4d3a00;color:#f39c12",
                  "unhealthy": "background-color:#4d0000;color:#e74c3c"}
        return colors.get(str(val), "")
    styled = df_recent.style.applymap(color_severity, subset=["aqi_severity"])
    st.dataframe(styled, use_container_width=True, height=300)
else:
    st.info("No events yet.")

st.divider()
st.caption(f"Last refreshed: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} UTC  |  Pipeline: IoT Core → MSK → Kafka Connect → PostgreSQL → Debezium CDC → Snowflake → dbt → Streamlit")

time.sleep(REFRESH_SECONDS)
st.rerun()

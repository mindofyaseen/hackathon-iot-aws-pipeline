import time
import streamlit as st
import snowflake.connector
import pandas as pd
import pydeck as pdk
import plotly.express as px

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


@st.cache_data(ttl=REFRESH_SECONDS)
def load_device_map():
    conn = get_connection()
    df = pd.read_sql(
        """
        SELECT device_id, avg_lat AS lat, avg_long AS lon,
               avg_aqi, event_date
        FROM HACKATHON_IOT.ANALYTICS.AGG_DEVICE_DAILY
        WHERE event_date = (SELECT MAX(event_date) FROM HACKATHON_IOT.ANALYTICS.AGG_DEVICE_DAILY)
        """,
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=REFRESH_SECONDS)
def load_aqi_timeseries():
    conn = get_connection()
    df = pd.read_sql(
        """
        SELECT device_id, event_date, avg_aqi
        FROM HACKATHON_IOT.ANALYTICS.AGG_DEVICE_DAILY
        ORDER BY event_date
        """,
        conn,
    )
    conn.close()
    return df


@st.cache_data(ttl=REFRESH_SECONDS)
def load_top_devices():
    conn = get_connection()
    df = pd.read_sql(
        """
        SELECT device_id,
               SUM(event_count)    AS total_events,
               ROUND(AVG(avg_aqi), 2) AS avg_aqi
        FROM HACKATHON_IOT.ANALYTICS.AGG_DEVICE_DAILY
        GROUP BY device_id
        ORDER BY avg_aqi DESC
        LIMIT 10
        """,
        conn,
    )
    conn.close()
    return df


st.title("IoT On-Prem to AWS/Snowflake Pipeline")
st.caption(f"Auto-refreshes every {REFRESH_SECONDS}s")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Device Activity Map")
    df_map = load_device_map()
    if not df_map.empty:
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df_map,
            get_position="[lon, lat]",
            get_color="[200, 30, 0, 160]",
            get_radius=5000,
            pickable=True,
        )
        view = pdk.ViewState(latitude=df_map["lat"].mean(), longitude=df_map["lon"].mean(), zoom=9)
        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, tooltip={"text": "{device_id}\nAQI: {avg_aqi}"}))
    else:
        st.info("No device location data yet.")

with col2:
    st.subheader("AQI Trend by Device")
    df_ts = load_aqi_timeseries()
    if not df_ts.empty:
        fig = px.line(df_ts, x="event_date", y="avg_aqi", color="device_id", markers=True)
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=350)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No time-series data yet.")

with col3:
    st.subheader("Top Devices by Avg AQI")
    df_top = load_top_devices()
    if not df_top.empty:
        fig = px.bar(df_top, x="avg_aqi", y="device_id", orientation="h", color="avg_aqi",
                     color_continuous_scale="Reds")
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=350, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No device ranking data yet.")

st.divider()
st.caption(f"Last loaded: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} UTC")

time.sleep(REFRESH_SECONDS)
st.rerun()

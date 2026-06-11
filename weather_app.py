import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, timedelta
import time

# ======================
# Styling
# ====================== 
st.set_page_config(page_title="Traunsee Wetter", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'IBM Plex Mono', monospace !important;
    letter-spacing: -0.03em;
}

.stApp {
    background: linear-gradient(160deg, #e8f4f8 0%, #f0e9d6 50%, #e8ede0 100%);
    min-height: 100vh;
}

.block-container {
    padding-top: 2rem;
    max-width: 1400px;
}

.metric-card {
    background: rgba(255,255,255,0.75);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(0,0,0,0.08);
    border-radius: 12px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 0.5rem;
}

.metric-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #888;
    font-family: 'IBM Plex Mono', monospace;
    margin-bottom: 0.2rem;
}

.metric-value {
    font-size: 2rem;
    font-weight: 600;
    font-family: 'IBM Plex Mono', monospace;
    color: #1a1a1a;
    line-height: 1;
}

.metric-unit {
    font-size: 0.9rem;
    color: #666;
    margin-left: 4px;
}

.section-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: #888;
    border-top: 1px solid rgba(0,0,0,0.1);
    padding-top: 1rem;
    margin-top: 1.5rem;
    margin-bottom: 0.8rem;
}

.stDateInput > div > div {
    background: rgba(255,255,255,0.7) !important;
    border-color: rgba(0,0,0,0.12) !important;
    border-radius: 8px !important;
}

.stAlert {
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)


# ======================
# Koordinaten
# ======================
COORDS = {
    "Traunkirchen": (47.993, 13.745),
    "Gmunden":      (47.918, 13.799),
    "Bad_Ischl":    (47.714, 13.632),
    "Ried":         (48.198, 13.490),
}

HOURLY_VARS = "pressure_msl,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,wind_speed_10m,wind_direction_10m"


# ======================
# API-Abruf: Archiv + Forecast zusammengeführt
# ======================
def _get(url, params):
    """Single HTTP GET — wartet bei 429 und versucht es erneut."""
    for attempt in range(5):
        r = requests.get(url, params=params, timeout=20)
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1))   # 10s, 20s, 30s, 40s, 50s
            continue
        r.raise_for_status()
        return r.json()
    raise requests.exceptions.HTTPError("Rate limit: zu viele Anfragen an Open-Meteo.")


def fetch_location(start: date, end: date, lat: float, lon: float) -> pd.DataFrame:
    today = date.today()
    yesterday = today - timedelta(days=1)
    base_params = dict(latitude=lat, longitude=lon, hourly=HOURLY_VARS, timezone="Europe/Vienna")

    parts = []

    # Archiv-Teil
    if start <= yesterday:
        p = {**base_params, "start_date": start.isoformat(), "end_date": min(end, yesterday).isoformat()}
        data = _get("https://archive-api.open-meteo.com/v1/archive", p)
        parts.append(pd.DataFrame(data["hourly"]))

    # Forecast-Teil
    if end >= today:
        p = {**base_params, "start_date": max(start, today).isoformat(), "end_date": end.isoformat()}
        data = _get("https://api.open-meteo.com/v1/forecast", p)
        parts.append(pd.DataFrame(data["hourly"]))

    df = pd.concat(parts).drop_duplicates(subset="time").reset_index(drop=True)
    df["time"] = pd.to_datetime(df["time"]).dt.tz_localize("Europe/Vienna")
    df.set_index("time", inplace=True)
    return df


@st.cache_data(ttl=7200, show_spinner=False)
def fetch_all(start: date, end: date) -> dict:
    """Sequenziell mit 2s Pause zwischen Orten — verhindert 429."""
    results = {}
    for name, (lat, lon) in COORDS.items():
        results[name] = fetch_location(start, end, lat, lon)
        time.sleep(2)
    return results


# ======================
# UI
# ======================
st.title("Traunsee — Druckgradient")

col_s, col_e, _ = st.columns([1, 1, 3])
with col_s:
    start_date = st.date_input("Von", date.today())
with col_e:
    end_date = st.date_input("Bis", date.today() + timedelta(days=2))

if end_date < start_date:
    st.error("Enddatum muss nach Startdatum liegen.")
    st.stop()

# Daten laden
with st.spinner("Wetterdaten werden geladen …"):
    try:
        dfs = fetch_all(start_date, end_date)
    except requests.exceptions.RequestException as e:
        st.warning(f"⚠️ API nicht erreichbar — Druckgradient und Wind werden nicht angezeigt.\n\n{e}")
        dfs = None


# ======================
# Datenabhängige Sektionen (nur wenn API erfolgreich)
# ======================
if dfs is not None:

    # DataFrame aufbauen
    df = dfs["Traunkirchen"].copy()
    df = df.rename(columns={"pressure_msl": "P_T"})
    df["P_G"] = dfs["Gmunden"]["pressure_msl"]
    df["P_B"] = dfs["Bad_Ischl"]["pressure_msl"]
    df["P_R"] = dfs["Ried"]["pressure_msl"]
    df["delta_P_TG"] = df["P_T"] - df["P_G"]
    df["delta_P_BR"] = df["P_B"] - df["P_R"]
    df["wind_speed_kt"] = df["wind_speed_10m"] * 1.94384
    df["wind_dir"] = df["wind_direction_10m"]

    # ======================
    # Aktuelle Kennzahlen
    # ======================
    now = pd.Timestamp.now(tz="Europe/Vienna")
    nearest = df.index.get_indexer([now], method="nearest")[0]
    row = df.iloc[nearest]

    st.markdown('<div class="section-title">Aktuelle Werte — Traunkirchen</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)

    def metric_card(label, value, unit, color="#1a1a1a"):
        return f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value" style="color:{color}">{value}<span class="metric-unit">{unit}</span></div>
        </div>"""

    with c1:
        st.markdown(metric_card("ΔP Traunkirchen–Gmunden", f"{row['delta_P_TG']:.2f}", "hPa",
            color="#e05c2a" if row['delta_P_TG'] > 1.5 else "#1a1a1a"), unsafe_allow_html=True)
    with c2:
        st.markdown(metric_card("ΔP Bad Ischl–Ried", f"{row['delta_P_BR']:.2f}", "hPa"), unsafe_allow_html=True)
    with c3:
        st.markdown(metric_card("Wind", f"{row['wind_speed_kt']:.1f}", "kt"), unsafe_allow_html=True)
    with c4:
        st.markdown(metric_card("Windrichtung", f"{row['wind_dir']:.0f}", "°"), unsafe_allow_html=True)

    # ======================
    # Hilfsfunktion: "Jetzt"-Linie + Heute-Markierung
    # ======================
    def add_now_and_today(fig):
        today_ts = pd.Timestamp.now(tz="Europe/Vienna").normalize()
        tomorrow_ts = today_ts + pd.Timedelta(days=1)
        now_ts = pd.Timestamp.now(tz="Europe/Vienna")

        fig.add_vrect(x0=today_ts, x1=tomorrow_ts,
                      fillcolor="#FFE57F", opacity=0.18, layer="below", line_width=0)

        if df.index.min() <= now_ts <= df.index.max():
            fig.add_shape(type="line", x0=now_ts, x1=now_ts, y0=0, y1=1,
                          line=dict(color="darkorange", width=2, dash="dot"),
                          xref="x", yref="paper")
            fig.add_annotation(x=now_ts, y=0.97, text="Jetzt", showarrow=False,
                               xanchor="left", xref="x", yref="paper",
                               font=dict(color="darkorange", size=11))
        return fig

    # ======================
    # Chart 1 — Druckgradient
    # ======================
    st.markdown('<div class="section-title">Druckgradient</div>', unsafe_allow_html=True)

    fig1 = make_subplots(specs=[[{"secondary_y": True}]])

    fig1.add_trace(go.Scatter(
        x=df.index, y=df["delta_P_TG"],
        name="ΔP Traunkirchen–Gmunden",
        line=dict(color="#555", width=2.5)
    ), secondary_y=False)

    fig1.add_trace(go.Scatter(
        x=df.index, y=df["delta_P_BR"],
        name="ΔP Bad Ischl–Ried",
        line=dict(color="#1a9de0", width=2.5)
    ), secondary_y=False)

    fig1.add_trace(go.Scatter(
        x=df.index, y=df["cloud_cover"],
        name="Gesamtbewölkung (%)",
        visible="legendonly",
        line=dict(color="#aaa", dash="dot", width=1.5)
    ), secondary_y=True)

    fig1 = add_now_and_today(fig1)

    fig1.add_hline(y=1.5, line=dict(color="crimson", dash="dash", width=1.5),
                   annotation_text="Oberwind Süd (1.5 hPa)", annotation_position="top right",
                   annotation_font_color="crimson")
    fig1.add_hline(y=0, line=dict(color="#333", dash="dot", width=1))

    fig1.update_layout(
        xaxis_title="Zeit", yaxis_title="ΔP [hPa]",
        legend=dict(orientation="h", y=-0.2),
        margin=dict(t=20, b=50),
        dragmode="zoom",
        plot_bgcolor="rgba(255,255,255,0.5)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans"),
        height=380,
    )
    fig1.update_yaxes(title_text="Bewölkung [%]", secondary_y=True, fixedrange=True, range=[0, 100])
    fig1.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.05)")
    fig1.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.05)", secondary_y=False)

    st.plotly_chart(fig1, use_container_width=True)

    # ======================
    # Chart 2 — Wind
    # ======================
    st.markdown('<div class="section-title">Wind — Traunkirchen</div>', unsafe_allow_html=True)

    fig2 = go.Figure()

    fig2.add_trace(go.Scatter(
        x=df.index, y=df["wind_speed_kt"],
        name="Windstärke (kt)",
        line=dict(color="#e07a2a", width=2.5),
        fill="tozeroy", fillcolor="rgba(224,122,42,0.08)"
    ))

    fig2.add_trace(go.Scatter(
        x=df.index, y=df["wind_dir"],
        name="Windrichtung (°)",
        line=dict(color="#2e9e5b", dash="dot", width=1.5),
        yaxis="y2"
    ))

    fig2 = add_now_and_today(fig2)

    max_kt = df["wind_speed_kt"].max()
    fig2.update_layout(
        xaxis_title="Zeit",
        yaxis=dict(title="Windstärke (kt)", range=[0, max(max_kt * 1.2, 5)], fixedrange=True,
                   showgrid=True, gridcolor="rgba(0,0,0,0.05)"),
        yaxis2=dict(title="Windrichtung (°)", overlaying="y", side="right",
                    range=[0, 360], showgrid=False, fixedrange=True),
        legend=dict(orientation="h", y=-0.2),
        margin=dict(t=20, b=50),
        dragmode="zoom",
        plot_bgcolor="rgba(255,255,255,0.5)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans"),
        height=320,
    )

    st.plotly_chart(fig2, use_container_width=True)

else:
    st.info("Druckgradient und Wind sind nicht verfügbar — die Diagramme werden angezeigt, sobald die API wieder erreichbar ist.")


# ======================
# AROME Bilder (scrollbar)
# — immer anzeigen, unabhängig vom API-Status
# ======================
st.markdown('<div class="section-title">AROME — kitewetter.at</div>', unsafe_allow_html=True)

arome_images = [
    f"https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_{i:02d}.png"
    for i in range(1, 43)
]

html_scroll = """
<div style="display:flex; overflow-x:auto; gap:10px; padding:10px 0 16px 0;
            scrollbar-width:thin; scrollbar-color:#ccc transparent;">
"""
for url in arome_images:
    html_scroll += f'<img src="{url}" style="height:280px; border-radius:8px; flex-shrink:0; box-shadow:0 2px 8px rgba(0,0,0,0.1);">'
html_scroll += "</div>"

st.markdown(html_scroll, unsafe_allow_html=True)


# ======================
# Profiwetter
# — immer anzeigen, unabhängig vom API-Status
# ======================
st.markdown('<div class="section-title">Profiwetter.ch — Traunkirchen</div>', unsafe_allow_html=True)
ts = int(time.time())
st.image(f"https://profiwetter.ch/mos_P0062.svg?t={ts}", use_container_width=True)


# ======================
# Webcam
# — immer anzeigen, unabhängig vom API-Status
# ======================
st.markdown('<div class="section-title">Webcam — Traunsee</div>', unsafe_allow_html=True)
st.components.v1.iframe(
    "https://g0.ipcamlive.com/player/player.php?alias=sctpano180",
    height=500,
    scrolling=False,
)

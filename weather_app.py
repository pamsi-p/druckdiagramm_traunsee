import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, timedelta, datetime
import time
import json
import requests
import re


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
    "Traunkirchen": (47.845583, 13.794628),
    "Gmunden":      (47.906002, 13.797635),
    "Bad_Ischl":    (47.714, 13.632),
    "Ried":         (48.198, 13.490),
}

HOURLY_VARS = "pressure_msl,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,wind_speed_10m,wind_direction_10m"
HOURLY_VARS_LIST = HOURLY_VARS.split(",")

# Modell-Priorität für die Prognose (nur für heute/Zukunft relevant, nicht fürs Archiv):
# 1) GeoSphere AROME Austria — hochauflösendstes Modell für den Alpenraum (2.5 km),
#    liefert aber nur die ersten ~60 Stunden.
# 2) DWD ICON-D2 — nächstbestes hochauflösendes Regionalmodell (2 km, Mitteleuropa).
# 3) DWD ICON-EU — gröberes, aber länger reichendes Regionalmodell (~7 km).
# 4) DWD ICON Seamless — deckt die komplette ICON-Kette (D2+EU+Global) ab.
# 5) best_match — Open-Meteo-Standardauswahl als letzter Fallback, damit auch der
#    Rest des angefragten Zeitraums (z.B. Tag 8-16) garantiert befüllt ist.
FORECAST_MODELS = [
    "geosphere_arome_austria",
    "icon_d2",
    "icon_eu",
    "icon_seamless",
    "best_match",
]
MODELS_PARAM = ",".join(FORECAST_MODELS)

PLOTLY_CONFIG = {
    "scrollZoom": False,
    "displayModeBar": False,
    "doubleClick": "reset",
    "responsive": True,
}


# ======================
# Bild-Wrapper (fängt fehlende/nicht erreichbare Bilder ab)
# ======================
def safe_image(url, caption=None, **kwargs):
    """
    Zeigt ein Bild an, ohne die App bei nicht verfügbaren oder nicht
    erreichbaren Bildquellen (z.B. url=None oder Netzwerkfehler) abstürzen
    zu lassen.
    """
    label = f" ({caption})" if caption else ""
    if not url:
        st.info(f"⚠️ Bild nicht verfügbar{label}.")
        return
    try:
        st.image(url, caption=caption, **kwargs)
    except Exception as e:
        st.info(f"⚠️ Bild nicht verfügbar{label}: {e}")


# ======================
# Open-Meteo API
# ======================
def _get(url, params):
    for attempt in range(5):
        r = requests.get(url, params=params, timeout=20)
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise requests.exceptions.HTTPError("Rate limit: zu viele Anfragen an Open-Meteo.")


def _merge_model_columns(raw: pd.DataFrame, variables: list, models: list) -> pd.DataFrame:
    """
    Wenn mehrere Modelle angefragt werden, liefert Open-Meteo pro Variable eine
    Spalte je Modell (z.B. wind_speed_10m_geosphere_arome_austria,
    wind_speed_10m_icon_d2, ...). Diese Funktion baut daraus wieder die
    ursprünglichen, unpräfigierten Spaltennamen, wobei pro Zeitpunkt der Wert
    des zuerst verfügbaren Modells (in der übergebenen Reihenfolge) genommen
    wird — also AROME so lange wie vorhanden, danach das nächstbeste Modell.
    """
    out = pd.DataFrame(index=raw.index)
    out["time"] = raw["time"]
    for var in variables:
        merged = None
        for model in models:
            col = f"{var}_{model}"
            if col not in raw.columns:
                continue
            merged = raw[col] if merged is None else merged.combine_first(raw[col])
        if merged is None and var in raw.columns:
            # Fallback, falls Open-Meteo (z.B. bei nur einem passenden Modell)
            # doch den unpräfigierten Namen zurückgibt.
            merged = raw[var]
        out[var] = merged
    return out


def fetch_location(start: date, end: date, lat: float, lon: float) -> pd.DataFrame:
    today = date.today()
    yesterday = today - timedelta(days=1)
    base_params = dict(latitude=lat, longitude=lon, hourly=HOURLY_VARS, timezone="Europe/Vienna")
    parts = []
    if start <= yesterday:
        # Vergangenheit: Reanalyse-Archiv, hier gibt es kein Modell zum Wählen.
        p = {**base_params, "start_date": start.isoformat(), "end_date": min(end, yesterday).isoformat()}
        data = _get("https://archive-api.open-meteo.com/v1/archive", p)
        parts.append(pd.DataFrame(data["hourly"]))
    if end >= today:
        # Prognose: AROME zuerst, sonst nächstbestes Regionalmodell für Wind.
        p = {
            **base_params,
            "models": MODELS_PARAM,
            "start_date": max(start, today).isoformat(),
            "end_date": end.isoformat(),
        }
        data = _get("https://api.open-meteo.com/v1/forecast", p)
        raw = pd.DataFrame(data["hourly"])
        parts.append(_merge_model_columns(raw, HOURLY_VARS_LIST, FORECAST_MODELS))
    df = pd.concat(parts).drop_duplicates(subset="time").reset_index(drop=True)
    df["time"] = pd.to_datetime(df["time"]).dt.tz_localize("Europe/Vienna")
    df.set_index("time", inplace=True)
    return df


@st.cache_data(ttl=7200, show_spinner=False)
def fetch_all(start: date, end: date) -> dict:
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

with st.spinner("Wetterdaten werden geladen …"):
    try:
        dfs = fetch_all(start_date, end_date)
    except requests.exceptions.RequestException as e:
        st.warning(f"⚠️ API nicht erreichbar — Druckgradient und Wind werden nicht angezeigt.\n\n{e}")
        dfs = None


# ======================
# Datenabhängige Sektionen
# ======================
if dfs is not None:

    df = dfs["Traunkirchen"].copy()
    df = df.rename(columns={"pressure_msl": "P_T"})
    df["P_G"] = dfs["Gmunden"]["pressure_msl"]
    df["P_B"] = dfs["Bad_Ischl"]["pressure_msl"]
    df["P_R"] = dfs["Ried"]["pressure_msl"]
    df["delta_P_TG"] = df["P_T"] - df["P_G"]
    df["delta_P_BR"] = df["P_B"] - df["P_R"]
    df["wind_speed_kt"] = (df["wind_speed_10m"] / 1.852).round(2)
    df["wind_dir"] = df["wind_direction_10m"]
    df["G_wind_speed_kt"] = (dfs["Gmunden"]["wind_speed_10m"] / 1.852).round(2)
    df["G_wind_dir"] = dfs["Gmunden"]["wind_direction_10m"]

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

    # Chart 1 — Druckgradient
    st.markdown('<div class="section-title">Druckgradient Traunsee</div>', unsafe_allow_html=True)
    fig1 = make_subplots(specs=[[{"secondary_y": True}]])
    fig1.add_trace(go.Scatter(x=df.index, y=df["delta_P_TG"], name="ΔP Traunkirchen–Gmunden",
                              line=dict(color="#555", width=2.5)), secondary_y=False)
    fig1.add_trace(go.Scatter(x=df.index, y=df["delta_P_BR"], name="ΔP Bad Ischl–Ried",
                              line=dict(color="#1a9de0", width=2.5)), secondary_y=False)
    fig1.add_trace(go.Scatter(x=df.index, y=df["cloud_cover"], name="Gesamtbewölkung (%)",
                              visible="legendonly", line=dict(color="#aaa", dash="dot", width=1.5)),
                              secondary_y=True)
    fig1 = add_now_and_today(fig1)
    fig1.add_hline(y=1.5, line=dict(color="crimson", dash="dash", width=1.5),
                   annotation_text="Oberwind Süd (1.5 hPa)", annotation_position="top right",
                   annotation_font_color="crimson")
    fig1.add_hline(y=0, line=dict(color="#333", dash="dot", width=1))
    fig1.update_layout(xaxis_title="Zeit", yaxis_title="ΔP [hPa]",
                       legend=dict(orientation="h", y=-0.2), margin=dict(t=20, b=50),
                       dragmode="zoom", plot_bgcolor="rgba(255,255,255,0.5)",
                       paper_bgcolor="rgba(0,0,0,0)", font=dict(family="IBM Plex Sans"), height=380)
    fig1.update_yaxes(title_text="Bewölkung [%]", secondary_y=True, fixedrange=True, range=[0, 100])
    fig1.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.05)")
    fig1.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.05)", fixedrange=True, secondary_y=False)
    st.plotly_chart(fig1, use_container_width=True, config=PLOTLY_CONFIG)

    # Chart 2 — Wind (Traunkirchen, dann Gmunden)
    def wind_chart(speed_col, dir_col, label):
        st.markdown(f'<div class="section-title">Wind — {label}</div>', unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df[speed_col], name="Windstärke (kt)",
                                  line=dict(color="#e07a2a", width=2.5),
                                  fill="tozeroy", fillcolor="rgba(224,122,42,0.08)"))
        fig.add_trace(go.Scatter(x=df.index, y=df[dir_col], name="Windrichtung (°)",
                                  line=dict(color="#2e9e5b", dash="dot", width=1.5), yaxis="y2"))
        fig = add_now_and_today(fig)
        max_kt = df[speed_col].max()
        fig.update_layout(
            xaxis_title="Zeit",
            yaxis=dict(title="Windstärke (kt)", range=[0, max(max_kt * 1.2, 5)], fixedrange=True,
                       showgrid=True, gridcolor="rgba(0,0,0,0.05)"),
            yaxis2=dict(title="Windrichtung (°)", overlaying="y", side="right",
                        range=[0, 360], showgrid=False, fixedrange=True),
            legend=dict(orientation="h", y=-0.2), margin=dict(t=20, b=50), dragmode="zoom",
            plot_bgcolor="rgba(255,255,255,0.5)", paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="IBM Plex Sans"), height=320)
        fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.05)")
        st.plotly_chart(fig, use_container_width=True)

    wind_chart("wind_speed_kt", "wind_dir", "Traunkirchen")
    wind_chart("G_wind_speed_kt", "G_wind_dir", "Gmunden")

else:
    st.info("Druckgradient und Wind sind nicht verfügbar — die Diagramme werden angezeigt, sobald die API wieder erreichbar ist.")


# ======================
# AROME Bilder
# ======================
st.markdown('<div class="section-title">AROME — kitewetter.at</div>', unsafe_allow_html=True)
arome_images = [
    f"https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_{i:02d}.png"
    for i in range(1, 43)
]
html_scroll = '<div style="display:flex; overflow-x:auto; gap:10px; padding:10px 0 16px 0; scrollbar-width:thin; scrollbar-color:#ccc transparent;">'
for url in arome_images:
    html_scroll += f'<img src="{url}" style="height:280px; border-radius:8px; flex-shrink:0; box-shadow:0 2px 8px rgba(0,0,0,0.1);">'
html_scroll += "</div>"
st.markdown(html_scroll, unsafe_allow_html=True)


# ======================
# AGS — Wind
# ======================
st.markdown('<div class="section-title">Klimaboje AGS — Wind</div>', unsafe_allow_html=True)

BOJE_HEADERS = {
    "Referer": "https://www.klimaboje.at/?page_id=1481",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0",
}

@st.cache_data(ttl=60, show_spinner=False)
def fetch_boje_act():
    r = requests.post(
        "https://www.klimaboje.at/my_Weather_boje.php?what=meas_act_mysql&station=ags",
        headers=BOJE_HEADERS, timeout=10
    )
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_boje_trend():
    r = requests.post(
        "https://www.klimaboje.at/my_Weather_boje.php?what=meas_trend_mysql&period=2&station=ags",
        headers=BOJE_HEADERS,
        timeout=10
    )
    r.raise_for_status()
    return r.text

try:
    with st.spinner("Klimaboje …"):
        act = fetch_boje_act()
        trend_raw = fetch_boje_trend()

    act_json = json.dumps(act)

    boje_html = (
        """<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: transparent; font-family: 'IBM Plex Sans', Arial, sans-serif; color: #1a1a1a; }

.row { display: flex; gap: 10px; margin-bottom: 8px; }
.cell {
  flex: 1; min-width: 0;
  background: rgba(255,255,255,0.75);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 12px;
  padding: 8px;
  text-align: center;
}

.addon { font-size: 11px; text-align: left; padding: 4px 8px; color: #555; font-family: monospace; }
.trend-row { font-size: 11px; display: flex; gap: 6px; justify-content: center; padding: 4px 0; font-family: monospace; color: #555; flex-wrap: wrap; }
select { background: rgba(255,255,255,0.7); border: 1px solid rgba(0,0,0,0.12); border-radius: 6px; padding: 2px 6px; font-size: 11px; margin: 4px 0; }
@media (max-width: 1000px) { .row { flex-direction: column; } }

</style>
<script src="https://cdn.plot.ly/plotly-3.0.0.min.js"></script>
</head>
<body>
<div class="row">
  <div class="cell">
    <div id="chart_wind"></div>
    <div id="wind_max" class="addon"></div>
    <div class="trend-row">
      <span style="color:#888;">Trend:</span>
      <span id="wind_1h"></span>
      <span id="wind_3h"></span>
      <span id="wind_24h"></span>
    </div>
    <select id="wind_unit" onchange="updateUnit()">
      <option value="1">m/s</option>
      <option value="1.944" selected>kn</option>
      <option value="3.6">km/h</option>

    </select>
  </div>
  <div class="cell">
    <div id="chart_dir"></div>
    <div id="wind_dirvar" class="addon"></div>
  </div>
  <div class="cell">
    <div id="chart_rose"></div>
  </div>
</div>
<script>
var m = """
        + act_json +
        """;
var cfg = {displaylogo:false, displayModeBar:false, responsive:true};
var bgr = "rgba(255,255,255,0.55)";
var fc  = "#1a1a1a";
var col_green  = "#33f9ff";
var col_yellow = "#f6fc18";
var col_red    = "LightSalmon";
var col_bar    = "darkblue";
var mg = {t:40, r:20, l:20, b:30};

var cur   = Number(m.windspeed_ms);
var old   = Number(m.wind_speed_old);
var max24 = Number(m.wind_speed_max_24);
var min24 = Number(m.wind_speed_min_24);
var t1    = Math.round((cur - Number(m.wind_speed_1h))  * 100)/100;
var t3    = Math.round((cur - Number(m.wind_speed_3h))  * 100)/100;
var t24   = Math.round((cur - Number(m.wind_speed_24h)) * 100)/100;
var raw   = {cur:cur, old:old, max24:max24, min24:min24, t1:t1, t3:t3, t24:t24};

function trend_span(val, fact) {
  var col = val >= 0 ? "#2e9e5b" : "#e05c2a";
  return '<span style="color:'+col+';">' + Math.round(val*fact*10)/10 + '</span>';
}

function makeGauge(val, ref, suffix, fact) {
  return [{
    type:"indicator", mode:"gauge+number+delta",
    value: Math.round(val*fact*10)/10,
    number:{suffix:suffix, font:{size:28}},
    title:{text:"Wind AGS", font:{size:14, color:fc}},
    delta:{reference: Math.round(ref*fact*10)/10,
           increasing:{color:"#2e9e5b"}, decreasing:{color:"#e05c2a"}},
    gauge:{
      axis:{range:[0, 30*fact], tickwidth:1, tickcolor:col_bar},
      bar:{color:col_bar},
      bgcolor:"white", borderwidth:2, bordercolor:"#ccc",
      steps:[{range:[0,       2*fact], color:col_green},
             {range:[2*fact, 18*fact], color:col_yellow},
             {range:[18*fact,30*fact], color:col_red}]
    }
  }];
}

function updateUnit() {
  var fact = parseFloat(document.getElementById("wind_unit").value);
  var ustr = document.getElementById("wind_unit").options[document.getElementById("wind_unit").selectedIndex].text;
  document.getElementById("wind_max").innerHTML =
    'max: <b>' + Math.round(raw.max24*fact*10)/10 + '</b> &nbsp; min: <b>' + Math.round(raw.min24*fact*10)/10 + '</b>';
  document.getElementById("wind_1h").innerHTML  = '-1h: '  + trend_span(raw.t1,  fact);
  document.getElementById("wind_3h").innerHTML  = '-3h: '  + trend_span(raw.t3,  fact);
  document.getElementById("wind_24h").innerHTML = '-24h: ' + trend_span(raw.t24, fact);
  Plotly.react("chart_wind", makeGauge(raw.cur, raw.old, ustr, fact),
    {margin:mg, paper_bgcolor:bgr, font:{color:fc, family:"IBM Plex Sans"}, height:200}, cfg);
}

// Wind Gauge
Plotly.newPlot("chart_wind", makeGauge(cur, old, "m/s", 1),
  {margin:mg, paper_bgcolor:bgr, font:{color:fc, family:"IBM Plex Sans"}, height:240}, cfg);

// Wind Richtung
var dir_avg = Number(m.wind_dir_avg);
var dir_max = Number(m.wind_dir_max);
var delta = dir_max > dir_avg ? (dir_max-dir_avg)/2 : (360+dir_max-dir_avg)/2;
if (delta < 10) delta = 10;
document.getElementById("wind_dirvar").innerHTML =
  'Dir: <b>' + dir_avg + '&deg;</b> &nbsp; Var: <b>' + Math.round(delta*10)/10 + '&deg;</b>';
Plotly.newPlot("chart_dir", [{
  type:"barpolar", r:[1], theta:[dir_avg], width:[delta],
  marker:{color:['#fc0435']}, showlegend:false
}], {
  margin:mg, paper_bgcolor:bgr, height:240,
  font:{color:fc, family:"IBM Plex Sans"},
  title:{text:"Mittl. Windrichtung", font:{size:13, color:fc}},
  polar:{
    bgcolor:'#7ed3f5', radialaxis:{visible:false},
    angularaxis:{
      direction:"clockwise", tickmode:"array",
      tickvals:[0,22.5,45,67.5,90,112.5,135,157.5,180,202.5,225,247.5,270,292.5,315,337.5],
      ticktext:["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"],
      ticks:"", tickfont:{size:9}, showline:true
    }
  }
}, cfg);

// Windrose
var theta = ['N','NNO','NO','ONO','O','OSO','SO','SSO','S','SSW','SW','WSW','W','WNW','NW','NNW'];
var colors = ['rgb(41,231,243)','rgb(41,136,243)','rgb(44,243,41)','rgb(92,247,15)',
              'rgb(247,244,15)','rgb(247,89,15)','rgb(247,15,54)','rgb(245,20,242)'];
var idx_labels = ['0-1.5kn','1.5-3.3kn','3.3-5.5kn','5.5-7.9kn',
                  '7.9-10.7kn','10.7-13.8kn','13.8-17.1kn','>17.1kn'];
var rose_data = []; var cur_ws = ''; var rv = new Array(16).fill(0);
for (var x in m.wind_trend) {
  var line = m.wind_trend[x];
  if (line.wind_speed != cur_ws && cur_ws != '') {
    rose_data.push({r:rv.slice(), theta:theta, name:cur_ws,
                    marker:{color:colors[idx_labels.indexOf(cur_ws)]}, type:"barpolar"});
    rv = new Array(16).fill(0);
  }
  var ti = theta.indexOf(line.wind_dir);
  if (ti >= 0) rv[ti] = Number(line.occur);
  cur_ws = line.wind_speed;
}
if (cur_ws) rose_data.push({r:rv.slice(), theta:theta, name:cur_ws,
                             marker:{color:colors[idx_labels.indexOf(cur_ws)]}, type:"barpolar"});
Plotly.newPlot("chart_rose", rose_data, {
  title:{text:"Wind letzte Stunde", font:{size:13, color:fc}},
  margin:mg, paper_bgcolor:bgr, height:240,
  font:{color:fc, family:"IBM Plex Sans"},
  polar:{barmode:"overlay", bargap:0,
         radialaxis:{ticksuffix:"%", angle:0, dtick:20},
         angularaxis:{direction:"clockwise"}}
}, cfg);

updateUnit();
</script>
</body>
</html>"""
    )

    st.components.v1.html(boje_html, height=300, scrolling=True)

    # ----------------------
    # Historischer Verlauf
    # ----------------------
    
    blocks = trend_raw.split("||xx||")
    names = blocks[0].split(",")
    times = pd.to_datetime(blocks[1].split(","))
    
    def get_series(key):
        idx = names.index(key)
        return [
            float(v) if v not in ("", "None") else None
            for v in blocks[idx + 1].split(",")
        ]
    
    ws_max = get_series("wind_speed_max")
    ws_avg = get_series("wind_speed_avg")
    wd_avg = get_series("wind_dir_avg")
    
    ws_max_kt = [
        v * 1.944 if v is not None else None
        for v in ws_max
    ]
    
    ws_avg_kt = [
        v * 1.944 if v is not None else None
        for v in ws_avg
    ]
    
    st.markdown(
        '<div class="section-title">AGS — Verlauf letzte 48h</div>',
        unsafe_allow_html=True
    )
    
    fig_boje = make_subplots(
        specs=[[{"secondary_y": True}]]
    )
    
    fig_boje.add_trace(
        go.Scatter(
            x=times,
            y=ws_avg_kt,
            name="Ø Wind",
            line=dict(color="#e07a2a", width=2.5)
        ),
        secondary_y=False
    )
    
    fig_boje.add_trace(
        go.Scatter(
            x=times,
            y=ws_max_kt,
            name="Böen",
            line=dict(color="#c43d1a", width=1.8)
        ),
        secondary_y=False
    )
    
    fig_boje.add_trace(
        go.Scatter(
            x=times,
            y=wd_avg,
            name="Richtung",
            line=dict(
                color="#2e9e5b",
                width=1.5,
                dash="dot"
            )
        ),
        secondary_y=True
    )
    
    fig_boje = add_now_and_today(fig_boje)
    
    fig_boje.update_layout(
        xaxis_title="Zeit",
        yaxis_title="Wind (kt)",
        legend=dict(
            orientation="h",
            y=-0.2
        ),
        margin=dict(t=20, b=50),
        plot_bgcolor="rgba(255,255,255,0.5)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans"),
        height=320,
        dragmode="zoom"
    )
    
    fig_boje.update_yaxes(
        title_text="Wind (kt)",
        secondary_y=False,
        fixedrange=True
    )
    
    fig_boje.update_yaxes(
        title_text="Richtung (°)",
        range=[0, 360],
        secondary_y=True,
        fixedrange=True,
        showgrid=False
    )
    
    fig_boje.update_xaxes(
        showgrid=True,
        gridcolor="rgba(0,0,0,0.05)"
    )
    
    st.plotly_chart(
        fig_boje,
        use_container_width=True,
        config=PLOTLY_CONFIG
    )

except Exception as e:
    st.warning(f"⚠️ Klimaboje nicht erreichbar: {e}")


# ======================
# Profiwetter
# ======================
st.markdown('<div class="section-title">Profiwetter.ch — Traunkirchen</div>', unsafe_allow_html=True)
ts = int(time.time())
safe_image(f"https://profiwetter.ch/mos_P0062.svg?t={ts}", use_container_width=True)


# ======================
# Webcam
# ======================
# ======================

def get_uyc_cam():
    try:
        url = f"https://uyct.at/webcam/UYCT.jpg?t={int(time.time())}"
        r = requests.head(url, timeout=10)
        if r.status_code == 200:
            return url
    except requests.exceptions.RequestException:
        pass
    return None


st.markdown('<div class="section-title">Webcam — Traunkirchen (SCT)</div>', unsafe_allow_html=True)
st.components.v1.iframe(
    "https://g0.ipcamlive.com/player/player.php?alias=sctpano180",
    height=500,
    scrolling=False,
)

def panomax_url(dt):
    return "https://traunkirchen.panomax.com/panorama/current.jpg" #"https://traunkirchen.panomax.com/panorama/?t=" + dt.strftime("%Y-%m-%d+%H-%M-%S")
st.markdown('<div class="section-title">Webcam - Traunkirchen (Panomax)</div>', unsafe_allow_html=True)
now = datetime.now()
url = panomax_url(now)
st.components.v1.iframe(
    url,
    height=600
)

st.markdown(
    '<div class="section-title">Webcam — Gmunden (UYC)</div>',
    unsafe_allow_html=True
)

cam = get_uyc_cam()
safe_image(cam, use_container_width=True)

st.markdown(
    '<div class="section-title">Webcam — Gmunden (Stadtplatz)</div>',
    unsafe_allow_html=True
)

safe_image(
    "https://www.salzi.at/webcam/INTERVAL_FTP/rathausplatz.jpg",
    use_container_width=True
)

def panomax_url_gm(dt):
    return "https://traunsee.panomax.com/gmundnerberg/current.jpeg" #"https://traunkirchen.panomax.com/panorama/?t=" + dt.strftime("%Y-%m-%d+%H-%M-%S")
st.markdown('<div class="section-title">Webcam - Gmundnerberg (Panomax)</div>', unsafe_allow_html=True)
now = datetime.now()
url = panomax_url_gm(now)
st.components.v1.iframe(
    url,
    height=600
)


# ======================
# AROME — Wind & Böen — Gmunden
# ======================
# Weg 3 aus der Recherche: Vorhersagedaten des AROME-Modells (GeoSphere Austria)
# direkt aus Open-Meteo holen. Kostenlos, kein API-Key nötig.
# Hinweis: der Pfeil-Marker "arrow" braucht plotly>=5.15.
 
st.markdown('<div class="section-title">AROME — Wind &amp; Böen — Gmunden</div>', unsafe_allow_html=True)
 
AROME_MODEL_ID = "geosphere_arome_austria"
AROME_FARBE_WIND = "#e07a2a"
AROME_FARBE_BOEN = "#c43d1a"
PFEIL_INTERVALL = 1  # Stunden, fix
 
GMUNDEN_LAT, GMUNDEN_LON = COORDS["Gmunden"]
 
 
@st.cache_data(ttl=1800, show_spinner=False)
def hole_arome_wind(lat: float, lon: float, start: date, end: date):
    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "hourly": "wind_speed_10m,wind_gusts_10m,wind_direction_10m",
            "models": AROME_MODEL_ID,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "timezone": "Europe/Vienna",
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json()
 
 
try:
    # Nutzt denselben Zeitraum (start_date/end_date), der ganz oben auf der
    # Seite eingestellt wurde.
    arome_data = hole_arome_wind(GMUNDEN_LAT, GMUNDEN_LON, start_date, end_date)
    arome_zeit = pd.to_datetime(arome_data["hourly"]["time"]).tz_localize("Europe/Vienna")
 
    speed = arome_data["hourly"].get("wind_speed_10m")
    boen = arome_data["hourly"].get("wind_gusts_10m")
    richtung = arome_data["hourly"].get("wind_direction_10m")
 
    if speed is None or boen is None or richtung is None:
        st.info("Keine AROME-Winddaten für diesen Zeitraum verfügbar.")
    else:
        speed_kt = [v / 1.852 if v is not None else None for v in speed]
        boen_kt = [v / 1.852 if v is not None else None for v in boen]
 
        # Heute-Markierung + "Jetzt"-Linie, exakt wie bei Druckgradient und
        # den beiden Windcharts oben (add_now_and_today), nur bezogen auf
        # den AROME-Zeitindex statt auf df.
        def add_now_and_today_arome(fig):
            today_ts = pd.Timestamp.now(tz="Europe/Vienna").normalize()
            tomorrow_ts = today_ts + pd.Timedelta(days=1)
            now_ts = pd.Timestamp.now(tz="Europe/Vienna")
            fig.add_vrect(x0=today_ts, x1=tomorrow_ts,
                          fillcolor="#FFE57F", opacity=0.18, layer="below", line_width=0)
            if arome_zeit.min() <= now_ts <= arome_zeit.max():
                fig.add_shape(type="line", x0=now_ts, x1=now_ts, y0=0, y1=1,
                              line=dict(color="darkorange", width=2, dash="dot"),
                              xref="x", yref="paper")
                fig.add_annotation(x=now_ts, y=0.97, text="Jetzt", showarrow=False,
                                   xanchor="left", xref="x", yref="paper",
                                   font=dict(color="darkorange", size=11))
            return fig
 
        fig_arome = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            row_heights=[0.7, 0.3], vertical_spacing=0.08,
        )
 
        fig_arome.add_trace(
            go.Scatter(x=arome_zeit, y=speed_kt, mode="lines", name="Wind",
                       line=dict(color=AROME_FARBE_WIND, width=2.5),
                       fill="tozeroy", fillcolor="rgba(224,122,42,0.08)"),
            row=1, col=1,
        )
        fig_arome.add_trace(
            go.Scatter(x=arome_zeit, y=boen_kt, mode="lines", name="Böen",
                       line=dict(color=AROME_FARBE_BOEN, width=1.8, dash="dot")),
            row=1, col=1,
        )
 
        # Windrichtung als Pfeile. Der Pfeil zeigt in die Richtung, in die
        # der Wind weht — daher +180° gegenüber der meteorologischen
        # "kommt von"-Richtung von Open-Meteo.
        idx = [
            j for j in range(0, len(arome_zeit), PFEIL_INTERVALL)
            if speed[j] is not None and richtung[j] is not None
        ]
        pfeil_zeit = [arome_zeit[j] for j in idx]
        pfeil_winkel = [(richtung[j] + 180) % 360 for j in idx]
        pfeil_text = [
            f"{arome_zeit[j]:%d.%m. %H:%M}<br>{speed_kt[j]:.1f} kt aus {richtung[j]:.0f}°"
            for j in idx
        ]
 
        fig_arome.add_trace(
            go.Scatter(
                x=pfeil_zeit, y=[1] * len(idx), mode="markers", name="Richtung", showlegend=False,
                marker=dict(symbol="arrow", size=13, angle=pfeil_winkel,
                           color=AROME_FARBE_WIND, line=dict(width=0)),
                hoverinfo="text", text=pfeil_text,
            ),
            row=2, col=1,
        )
 
        fig_arome = add_now_and_today_arome(fig_arome)
 
        fig_arome.update_yaxes(
            title_text="Wind (kt)", row=1, col=1,
            showgrid=True, gridcolor="rgba(0,0,0,0.05)", fixedrange=True,
        )
        fig_arome.update_yaxes(
            row=2, col=1, showticklabels=False, range=[0.5, 1.5],
            showgrid=False, fixedrange=True,
        )
        fig_arome.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.05)", row=1, col=1)
        fig_arome.update_xaxes(title_text="Zeit", showgrid=True, gridcolor="rgba(0,0,0,0.05)", row=2, col=1)
        fig_arome.update_layout(
            legend=dict(orientation="h", y=-0.15),
            margin=dict(t=20, b=50),
            plot_bgcolor="rgba(255,255,255,0.5)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="IBM Plex Sans"),
            height=420,
            hovermode="closest",
            dragmode="zoom",
        )
        st.plotly_chart(fig_arome, use_container_width=True, config=PLOTLY_CONFIG)
 
except requests.exceptions.RequestException as e:
    st.warning(f"⚠️ AROME-Winddaten nicht erreichbar: {e}")


# ============================================================
# TRAUNSEE LIVE WINDMODELL
# ============================================================
#
# Modi:
#   1) Nur Messdaten
#   2) AROME
#   3) AROME + Messdaten
#
# Nur:
#   - Grundwind
#   - Böen
#   - Windrichtung
#
# Das Windfeld wird intern als U/V-Komponenten verarbeitet.
# Dadurch können Richtung und Geschwindigkeit korrekt
# kombiniert/interpoliert werden.
#
# ============================================================

import numpy as np
import math
import branca.colormap as bcm
import folium
from folium.plugins import HeatMap
import streamlit.components.v1 as components


# ------------------------------------------------------------
# KONFIGURATION
# ------------------------------------------------------------

TRAUNSEE_BOUNDS = {
    "lat_min": 47.80,
    "lat_max": 47.93,
    "lon_min": 13.68,
    "lon_max": 13.87,
}

TRAUNSEE_CENTER = [47.865, 13.805]

# Raster des eigenen Windmodells.
# 25 x 35 ist für einen ersten Live-Betrieb ausreichend.
GRID_N_LAT = 25
GRID_N_LON = 35

AROME_MODEL_ID = "geosphere_arome_austria"

# Aktualisierung der Live-Karte
LIVE_REFRESH_SECONDS = 60


# ------------------------------------------------------------
# STATIONEN
# ------------------------------------------------------------
#
# Die Koordinaten werden hier bewusst separat gepflegt.
# Dadurch kann die Datenquelle später ausgetauscht werden,
# ohne das Windmodell zu verändern.
#
# Quellen:
#   SALT Ebensee
#   SC Traunkirchen
#   AGS Gmunden
#   Bräuwiese
#   Altmünster / Nachdemsee
#   Traunkirchen Ort
#
# ------------------------------------------------------------

TRAUNSEE_STATIONS = {

    "SALT Ebensee": {
        "lat": 47.8110,
        "lon": 13.7800,
        "source": "SALT",
        "source_url": "https://salt.co.at/wetter",
    },

    "SC Traunkirchen": {
        "lat": 47.8540,
        "lon": 13.7890,
        "source": "SCT",
        "source_url":
            "https://www.sc-traunkirchen.at/webcam-wetter/",
    },

    "AGS Gmunden": {
        "lat": 47.9060,
        "lon": 13.7976,
        "source": "Klimaboje AGS",
        "source_url":
            "https://www.klimaboje.at/?page_id=1481",
    },

    "Bräuwiese": {
        "lat": 47.8750,
        "lon": 13.7890,
        "source": "AWEKAS",
        "source_url":
            "https://stationsweb.awekas.at/index-tab?id=23403",
        "awekas_id": 23403,
    },

    "Altmünster / Nachdemsee": {
        "lat": 47.899098,
        "lon": 13.783492,
        "source": "AWEKAS",
        "source_url":
            "https://www.awekas.at/map/de/?lon=13.783492&lat=47.899098",
        "awekas_id": None,
    },

    "Traunkirchen Ort": {
        "lat": 47.871695,
        "lon": 13.780628,
        "source": "AWEKAS",
        "source_url":
            "https://www.awekas.at/map/de/?lon=13.780628&lat=47.871695",
        "awekas_id": None,
    },
}


# ------------------------------------------------------------
# EINHEITEN
# ------------------------------------------------------------

def kmh_to_kt(value):
    if value is None or pd.isna(value):
        return np.nan
    return float(value) / 1.852


def ms_to_kt(value):
    if value is None or pd.isna(value):
        return np.nan
    return float(value) / 1.852


# ------------------------------------------------------------
# WIND -> U/V
# ------------------------------------------------------------
#
# Meteorologische Richtung:
#   0°   = Wind kommt aus Norden
#   90°  = Osten
#   180° = Süden
#   270° = Westen
#
# U/V wird so gerechnet, dass ein Rückweg zu
# Geschwindigkeit + meteorologischer Richtung
# möglich ist.
# ------------------------------------------------------------

def wind_to_uv(speed, direction_deg):

    direction_rad = np.radians(direction_deg)

    u = -speed * np.sin(direction_rad)
    v = -speed * np.cos(direction_rad)

    return u, v


def uv_to_wind(u, v):

    speed = np.sqrt(u ** 2 + v ** 2)

    direction = (
        np.degrees(np.arctan2(-u, -v)) + 360
    ) % 360

    return speed, direction


# ------------------------------------------------------------
# RASTER
# ------------------------------------------------------------

def create_grid():

    lats = np.linspace(
        TRAUNSEE_BOUNDS["lat_min"],
        TRAUNSEE_BOUNDS["lat_max"],
        GRID_N_LAT
    )

    lons = np.linspace(
        TRAUNSEE_BOUNDS["lon_min"],
        TRAUNSEE_BOUNDS["lon_max"],
        GRID_N_LON
    )

    lon_grid, lat_grid = np.meshgrid(lons, lats)

    return lat_grid, lon_grid


# ------------------------------------------------------------
# AROME
# ------------------------------------------------------------

@st.cache_data(ttl=900, show_spinner=False)
def fetch_arome_grid():

    lat_grid, lon_grid = create_grid()

    flat_lat = lat_grid.flatten()
    flat_lon = lon_grid.flatten()

    params = {
        "latitude": ",".join(
            f"{x:.5f}" for x in flat_lat
        ),

        "longitude": ",".join(
            f"{x:.5f}" for x in flat_lon
        ),

        "hourly":
            "wind_speed_10m,"
            "wind_gusts_10m,"
            "wind_direction_10m",

        "models": AROME_MODEL_ID,

        "forecast_days": 1,

        "timezone": "Europe/Vienna",
    }

    r = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params=params,
        timeout=30,
    )

    r.raise_for_status()

    data = r.json()

    # Bei mehreren Koordinaten kommt eine Liste zurück.
    if isinstance(data, dict):
        data = [data]

    rows = []

    for i, item in enumerate(data):

        hourly = item["hourly"]

        speed = hourly["wind_speed_10m"][0]
        gust = hourly["wind_gusts_10m"][0]
        direction = hourly["wind_direction_10m"][0]

        rows.append({
            "lat": flat_lat[i],
            "lon": flat_lon[i],
            "speed": kmh_to_kt(speed),
            "gust": kmh_to_kt(gust),
            "direction": direction,
            "source": "AROME",
        })

    return pd.DataFrame(rows)


# ------------------------------------------------------------
# AWEKAS
# ------------------------------------------------------------
#
# AWEKAS benötigt einen API-Key.
#
# In Streamlit:
#
# .streamlit/secrets.toml
#
# [awekas]
# api_key = "DEIN_KEY"
#
# ------------------------------------------------------------

def get_awekas_api_key():

    try:
        return st.secrets["awekas"]["api_key"]
    except Exception:
        return None


@st.cache_data(ttl=60, show_spinner=False)
def fetch_awekas_station(station_id):

    api_key = get_awekas_api_key()

    if not api_key:
        return None

    # Die AWEKAS Current API liefert die aktuellen
    # Werte für den Account/API-Key.
    #
    # Für den finalen Betrieb müssen die drei
    # gewünschten AWEKAS-Stationen ihrem jeweiligen
    # Datenzugang zugeordnet werden.

    r = requests.get(
        "https://api.awekas.at/current.php",
        params={
            "key": api_key,
            "lng": "de",
        },
        timeout=15,
    )

    r.raise_for_status()

    data = r.json()

    if data.get("error"):
        return None

    current = data.get("current", {})

    if not current:
        return None

    return {
        "windspeed": current.get("windspeed"),
        "gustspeed": current.get("gustspeed"),
        "winddirection": current.get("winddirection"),
        "timestamp": current.get("datatimestamp"),
    }


# ------------------------------------------------------------
# AGS / KLIMABOJE
# ------------------------------------------------------------

def fetch_ags_station():

    try:

        act = fetch_boje_act()

        if not act:
            return None

        speed_ms = act.get("windspeed_ms")
        gust_ms = act.get("wind_speed_max")
        direction = act.get("wind_dir_avg")

        if speed_ms is None:
            speed_ms = act.get("windspeed")

        if gust_ms is None:
            gust_ms = act.get("gustspeed")

        if direction is None:
            direction = act.get("wind_dir")

        if speed_ms is None:
            return None

        return {
            "speed": ms_to_kt(speed_ms),
            "gust": ms_to_kt(gust_ms),
            "direction": direction,
            "timestamp": time.time(),
        }

    except Exception:

        return None


# ------------------------------------------------------------
# LIVE-STATIONSDATEN
# ------------------------------------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def fetch_live_stations():

    rows = []

    # ----------------------------------------
    # AGS
    # ----------------------------------------

    ags = fetch_ags_station()

    if ags:

        station = TRAUNSEE_STATIONS["AGS Gmunden"]

        rows.append({
            "station": "AGS Gmunden",
            "lat": station["lat"],
            "lon": station["lon"],
            "speed": ags["speed"],
            "gust": ags["gust"],
            "direction": ags["direction"],
            "timestamp": ags["timestamp"],
            "source": "Klimaboje",
        })


    # ----------------------------------------
    # AWEKAS
    # ----------------------------------------

    for station_name in [
        "Bräuwiese",
        "Altmünster / Nachdemsee",
        "Traunkirchen Ort",
    ]:

        station = TRAUNSEE_STATIONS[station_name]

        station_id = station.get("awekas_id")

        if not station_id:
            continue

        try:

            data = fetch_awekas_station(
                station_id
            )

            if not data:
                continue

            rows.append({
                "station": station_name,
                "lat": station["lat"],
                "lon": station["lon"],
                "speed": kmh_to_kt(
                    data["windspeed"]
                ),
                "gust": kmh_to_kt(
                    data["gustspeed"]
                ),
                "direction":
                    data["winddirection"],
                "timestamp":
                    data["timestamp"],
                "source": "AWEKAS",
            })

        except Exception:
            pass


    # --------------------------------------------------------
    # WICHTIG:
    #
    # SALT + SCT werden bewusst als eigene Adapter vorbereitet.
    # Sobald deren direkte Live-JSON/API-Endpunkte identifiziert
    # sind, werden hier dieselben drei Werte eingesetzt:
    #
    # speed
    # gust
    # direction
    #
    # Dadurch muss am eigentlichen Windmodell nichts geändert
    # werden.
    # --------------------------------------------------------

    return pd.DataFrame(rows)


# ------------------------------------------------------------
# IDW INTERPOLATION
# ------------------------------------------------------------
#
# Für die reine Messdatenkarte.
#
# Wir interpolieren U/V und nicht Richtung/Geschwindigkeit
# separat.
# ------------------------------------------------------------

def idw_interpolate(
    station_df,
    grid_lat,
    grid_lon,
    value_columns=("u", "v"),
    power=2.0,
):

    result = {}

    for value_col in value_columns:

        values = []

        for lat, lon in zip(
            grid_lat.flatten(),
            grid_lon.flatten()
        ):

            distances = []

            for _, row in station_df.iterrows():

                # einfache lokale Distanzmetrik
                dx = (
                    (lon - row["lon"]) *
                    np.cos(np.radians(lat))
                )

                dy = lat - row["lat"]

                d = np.sqrt(
                    dx ** 2 +
                    dy ** 2
                )

                distances.append(
                    max(d, 0.0001)
                )

            distances = np.array(distances)

            weights = 1 / (
                distances ** power
            )

            vals = station_df[value_col].values

            values.append(
                np.sum(weights * vals) /
                np.sum(weights)
            )

        result[value_col] = np.array(values)

    return result


# ------------------------------------------------------------
# MESSDATEN -> U/V
# ------------------------------------------------------------

def prepare_station_vectors(stations_df):

    df = stations_df.copy()

    df = df.dropna(
        subset=["speed", "direction"]
    )

    if df.empty:
        return df

    u, v = wind_to_uv(
        df["speed"].values,
        df["direction"].values
    )

    df["u"] = u
    df["v"] = v

    # Für die Böen verwenden wir keine Richtungsinterpolation.
    # Stattdessen wird die Böe räumlich interpoliert.
    df["gust"] = df["gust"].fillna(
        df["speed"]
    )

    return df


# ------------------------------------------------------------
# AROME-REFERENZ AN STATIONSPUNKTEN
# ------------------------------------------------------------

@st.cache_data(ttl=900, show_spinner=False)
def fetch_arome_at_points(points):

    rows = []

    for point in points:

        try:

            r = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": point["lat"],
                    "longitude": point["lon"],
                    "hourly":
                        "wind_speed_10m,"
                        "wind_gusts_10m,"
                        "wind_direction_10m",
                    "models": AROME_MODEL_ID,
                    "forecast_days": 1,
                    "timezone": "Europe/Vienna",
                },
                timeout=15,
            )

            r.raise_for_status()

            data = r.json()["hourly"]

            speed = data["wind_speed_10m"][0]
            gust = data["wind_gusts_10m"][0]
            direction = data["wind_direction_10m"][0]

            u, v = wind_to_uv(
                kmh_to_kt(speed),
                direction
            )

            rows.append({
                "station": point["station"],
                "lat": point["lat"],
                "lon": point["lon"],
                "arome_speed": kmh_to_kt(speed),
                "arome_gust": kmh_to_kt(gust),
                "arome_direction": direction,
                "arome_u": u,
                "arome_v": v,
            })

        except Exception:

            rows.append({
                "station": point["station"],
                "lat": point["lat"],
                "lon": point["lon"],
                "arome_speed": np.nan,
                "arome_gust": np.nan,
                "arome_direction": np.nan,
                "arome_u": np.nan,
                "arome_v": np.nan,
            })

    return pd.DataFrame(rows)


# ------------------------------------------------------------
# WINDMODELL
# ------------------------------------------------------------

def build_wind_model(
    live_df,
    arome_df,
    mode
):

    grid_lat, grid_lon = create_grid()

    # --------------------------------------------------------
    # MODELL: AROME
    # --------------------------------------------------------

    if mode == "AROME":

        out = arome_df.copy()

        out["u"], out["v"] = wind_to_uv(
            out["speed"],
            out["direction"]
        )

        return out, grid_lat, grid_lon


    # --------------------------------------------------------
    # MESSDATEN
    # --------------------------------------------------------

    stations = prepare_station_vectors(
        live_df
    )

    if stations.empty:

        return (
            pd.DataFrame(),
            grid_lat,
            grid_lon
        )


    interp = idw_interpolate(
        stations,
        grid_lat,
        grid_lon,
        value_columns=("u", "v", "gust")
    )

    u = interp["u"]
    v = interp["v"]
    gust = interp["gust"]


    # --------------------------------------------------------
    # NUR MESSDATEN
    # --------------------------------------------------------

    if mode == "Nur Messdaten":

        speed, direction = uv_to_wind(
            u,
            v
        )

        out = pd.DataFrame({
            "lat": grid_lat.flatten(),
            "lon": grid_lon.flatten(),
            "speed": speed,
            "gust": gust,
            "direction": direction,
        })

        return out, grid_lat, grid_lon


    # --------------------------------------------------------
    # AROME + MESSDATEN
    # --------------------------------------------------------

    # AROME an den Stationspunkten
    arome_station = fetch_arome_at_points(
        stations[
            ["station", "lat", "lon"]
        ].to_dict("records")
    )

    merged = stations.merge(
        arome_station,
        on=["station", "lat", "lon"],
        how="left"
    )

    merged = merged.dropna(
        subset=[
            "arome_u",
            "arome_v"
        ]
    )

    if merged.empty:

        speed, direction = uv_to_wind(
            u,
            v
        )

        out = pd.DataFrame({
            "lat": grid_lat.flatten(),
            "lon": grid_lon.flatten(),
            "speed": speed,
            "gust": gust,
            "direction": direction,
        })

        return out, grid_lat, grid_lon


    # --------------------------------------------------------
    # RESIDUAL
    # --------------------------------------------------------

    # Beobachtung - AROME
    merged["du"] = (
        merged["u"] -
        merged["arome_u"]
    )

    merged["dv"] = (
        merged["v"] -
        merged["arome_v"]
    )

    merged["dgust"] = (
        merged["gust"] -
        merged["arome_gust"]
    )


    # Residual-Feld interpolieren
    residual = idw_interpolate(
        merged,
        grid_lat,
        grid_lon,
        value_columns=(
            "du",
            "dv",
            "dgust"
        )
    )


    # AROME-Grid in DataFrame
    ar = arome_df.copy()

    ar["u"], ar["v"] = wind_to_uv(
        ar["speed"],
        ar["direction"]
    )


    # korrigiertes AROME-Feld
    final_u = (
        ar["u"].values +
        residual["du"]
    )

    final_v = (
        ar["v"].values +
        residual["dv"]
    )

    final_gust = (
        ar["gust"].values +
        residual["dgust"]
    )

    final_gust = np.maximum(
        final_gust,
        0
    )

    final_speed, final_direction = uv_to_wind(
        final_u,
        final_v
    )

    out = pd.DataFrame({
        "lat": ar["lat"].values,
        "lon": ar["lon"].values,
        "speed": final_speed,
        "gust": final_gust,
        "direction": final_direction,
    })

    return (
        out,
        grid_lat,
        grid_lon
    )


# ------------------------------------------------------------
# WIND-FARBSCALA
# ------------------------------------------------------------

def wind_color(speed):

    if speed < 2:
        return "#d7f7ff"

    if speed < 5:
        return "#7dd3fc"

    if speed < 8:
        return "#38bdf8"

    if speed < 12:
        return "#22c55e"

    if speed < 16:
        return "#facc15"

    if speed < 20:
        return "#fb923c"

    if speed < 25:
        return "#ef4444"

    return "#b91c1c"


# ------------------------------------------------------------
# WINDPARTIKEL ALS SVG
# ------------------------------------------------------------

def arrow_svg(direction, speed):

    # Kartenpfeil zeigt in die Bewegungsrichtung.
    # Meteorologische Richtung = kommt AUS dieser Richtung.
    angle = (direction + 180) % 360

    length = 18 + min(speed, 30) * 0.8

    x2 = 25 + length * np.sin(
        np.radians(angle)
    )

    y2 = 25 - length * np.cos(
        np.radians(angle)
    )

    return f"""
    <svg width="50" height="50"
         viewBox="0 0 50 50"
         xmlns="http://www.w3.org/2000/svg">

        <line
            x1="25"
            y1="25"
            x2="{x2:.1f}"
            y2="{y2:.1f}"
            stroke="{wind_color(speed)}"
            stroke-width="3"
            stroke-linecap="round"
        />

        <circle
            cx="25"
            cy="25"
            r="3.5"
            fill="{wind_color(speed)}"
        />

    </svg>
    """


# ------------------------------------------------------------
# FOLIUM-KARTE
# ------------------------------------------------------------

def render_wind_map(
    wind_df,
    live_df,
    mode
):

    m = folium.Map(
        location=TRAUNSEE_CENTER,
        zoom_start=12,
        tiles="CartoDB positron",
        control_scale=True,
    )


    # --------------------------------------------------------
    # WIND-FELD
    # --------------------------------------------------------

    if not wind_df.empty:

        # jedes Rasterfeld als Kreis
        # Farbe = Grundwind
        # Popup = Geschwindigkeit/Böe/Richtung

        for _, row in wind_df.iterrows():

            speed = row["speed"]

            if pd.isna(speed):
                continue

            folium.CircleMarker(
                location=[
                    row["lat"],
                    row["lon"]
                ],

                radius=8,

                color=wind_color(speed),

                fill=True,

                fill_color=wind_color(speed),

                fill_opacity=0.25,

                opacity=0.0,

                tooltip=(
                    f"{speed:.1f} kt"
                    f" · Böe {row['gust']:.1f} kt"
                    f" · {row['direction']:.0f}°"
                ),
            ).add_to(m)


    # --------------------------------------------------------
    # WINDPFEILE
    # --------------------------------------------------------

    if not wind_df.empty:

        arrow_step = max(
            1,
            int(len(wind_df) / 80)
        )

        for _, row in wind_df.iloc[
            ::arrow_step
        ].iterrows():

            speed = row["speed"]

            if pd.isna(speed):
                continue

            html = arrow_svg(
                row["direction"],
                speed
            )

            folium.Marker(
                location=[
                    row["lat"],
                    row["lon"]
                ],

                icon=folium.DivIcon(
                    html=html,
                    icon_size=(50, 50),
                    icon_anchor=(25, 25),
                ),

                tooltip=(
                    f"Wind {speed:.1f} kt"
                    f" · Böe {row['gust']:.1f} kt"
                    f" · {row['direction']:.0f}°"
                ),

            ).add_to(m)


    # --------------------------------------------------------
    # MESSSTATIONEN
    # --------------------------------------------------------

    if not live_df.empty:

        for _, row in live_df.iterrows():

            speed_text = (
                f"{row['speed']:.1f} kt"
                if pd.notna(row["speed"])
                else "—"
            )

            gust_text = (
                f"{row['gust']:.1f} kt"
                if pd.notna(row["gust"])
                else "—"
            )

            dir_text = (
                f"{row['direction']:.0f}°"
                if pd.notna(row["direction"])
                else "—"
            )

            popup_html = f"""
            <div style="
                font-family:Arial;
                min-width:190px;
            ">

                <b>{row['station']}</b><br><br>

                Grundwind:
                <b>{speed_text}</b><br>

                Böe:
                <b>{gust_text}</b><br>

                Richtung:
                <b>{dir_text}</b><br>

                Quelle:
                {row['source']}

            </div>
            """

            folium.CircleMarker(
                location=[
                    row["lat"],
                    row["lon"]
                ],

                radius=6,

                color="#111827",

                weight=2,

                fill=True,

                fill_color=(
                    wind_color(
                        row["speed"]
                    )
                    if pd.notna(row["speed"])
                    else "#ffffff"
                ),

                fill_opacity=1,

                popup=folium.Popup(
                    popup_html,
                    max_width=260
                ),

                tooltip=row["station"],

            ).add_to(m)


    # --------------------------------------------------------
    # TRAUNSEE MARKIEREN
    # --------------------------------------------------------

    folium.GeoJson(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [13.67, 47.80],
                            [13.88, 47.80],
                            [13.88, 47.93],
                            [13.67, 47.93],
                            [13.67, 47.80],
                        ]]
                    },
                    "properties": {},
                }
            ]
        },

        style_function=lambda feature: {
            "fillOpacity": 0,
            "color": "#334155",
            "weight": 1,
        },

    ).add_to(m)


    # --------------------------------------------------------
    # LEGENDE
    # --------------------------------------------------------

    legend = """
    <div style="
        position: fixed;
        bottom: 30px;
        left: 30px;
        z-index:9999;

        background:white;

        padding:10px 14px;

        border-radius:8px;

        box-shadow:
            0 2px 12px rgba(0,0,0,.18);

        font-family:Arial;
        font-size:12px;
    ">

        <b>Wind [kt]</b><br>

        <span style="color:#38bdf8">●</span>
        5–8<br>

        <span style="color:#22c55e">●</span>
        8–12<br>

        <span style="color:#facc15">●</span>
        12–16<br>

        <span style="color:#fb923c">●</span>
        16–20<br>

        <span style="color:#ef4444">●</span>
        20–25<br>

        <span style="color:#b91c1c">●</span>
        >25

    </div>
    """

    m.get_root().html.add_child(
        folium.Element(legend)
    )

    return m


# ============================================================
# UI
# ============================================================

st.markdown(
    '<div class="section-title">'
    'Traunsee — LIVE WINDMODELL'
    '</div>',
    unsafe_allow_html=True
)


map_col, info_col = st.columns(
    [5, 1]
)


with map_col:

    model_mode = st.radio(
        "Windmodell",
        [
            "Nur Messdaten",
            "AROME",
            "AROME + Messdaten",
        ],
        horizontal=True,
    )


with info_col:

    st.caption(
        "Live-Update"
    )

    st.metric(
        "Intervall",
        f"{LIVE_REFRESH_SECONDS} s"
    )


# ------------------------------------------------------------
# DATEN HOLEN
# ------------------------------------------------------------

try:

    with st.spinner(
        "Windmodell wird berechnet …"
    ):

        live_stations = (
            fetch_live_stations()
        )

        if model_mode == "AROME":

            arome_grid_raw = (
                fetch_arome_grid()
            )

            wind_model = (
                arome_grid_raw.copy()
            )

        else:

            arome_grid_raw = (
                fetch_arome_grid()
            )

            wind_model, _, _ = (
                build_wind_model(
                    live_stations,
                    arome_grid_raw,
                    model_mode
                )
            )


    # --------------------------------------------------------
    # KARTE
    # --------------------------------------------------------

    wind_map = render_wind_map(
        wind_model,
        live_stations,
        model_mode
    )

    st.components.v1.html(
        wind_map.get_root().render(),
        height=760,
        scrolling=False,
    )


except Exception as e:

    st.error(
        f"Windmodell konnte nicht "
        f"berechnet werden: {e}"
    )


# ------------------------------------------------------------
# AKTUELLE STATIONSWERTE
# ------------------------------------------------------------

if (
    'live_stations' in locals()
    and not live_stations.empty
):

    st.markdown(
        '<div class="section-title">'
        'Aktuelle Messstationen'
        '</div>',
        unsafe_allow_html=True
    )

    display_df = (
        live_stations[
            [
                "station",
                "source",
                "speed",
                "gust",
                "direction",
            ]
        ]
        .copy()
    )

    display_df = display_df.rename(
        columns={
            "station": "Station",
            "source": "Quelle",
            "speed": "Grundwind [kt]",
            "gust": "Böe [kt]",
            "direction": "Richtung [°]",
        }
    )

    display_df["Grundwind [kt]"] = (
        display_df["Grundwind [kt]"]
        .round(1)
    )

    display_df["Böe [kt]"] = (
        display_df["Böe [kt]"]
        .round(1)
    )

    display_df["Richtung [°]"] = (
        display_df["Richtung [°]"]
        .round(0)
    )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )


# ------------------------------------------------------------
# AUTO REFRESH
# ------------------------------------------------------------

st.markdown(
    f"""
    <script>
        setTimeout(function() {{
            window.parent.location.reload();
        }}, {LIVE_REFRESH_SECONDS * 1000});
    </script>
    """,
    unsafe_allow_html=True
)
 

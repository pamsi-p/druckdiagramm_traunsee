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

# Plotly-Konfiguration: touch-freundlich, Toolbar ausgeblendet
PLOTLY_CONFIG = {
    "scrollZoom": False,
    "displayModeBar": False,   # Toolbar komplett ausblenden (zu klein auf Mobile)
    "doubleClick": "reset",
    "responsive": True,
}

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
    df["wind_speed_kt"] = (df["wind_speed_10m"] / 1.852).round(2)
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
    fig1.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.05)",  fixedrange=True, secondary_y=False)

    st.plotly_chart(fig1, use_container_width=True, config=PLOTLY_CONFIG)

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
    fig2.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.05)")

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

BOJE_HTML = f"""
<!DOCTYPE html>
<html>
<head>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background: transparent; font-family: 'IBM Plex Sans', Arial, sans-serif; color: #1a1a1a; }}

.row {{
  display: flex;
  gap: 10px;
  margin-bottom: 8px;
}}

.cell {{
  flex: 1;
  background: rgba(255,255,255,0.75);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(0,0,0,0.08);
  border-radius: 12px;
  padding: 8px;
  text-align: center;
  min-width: 0;
}}

.addon {{
  font-size: 11px;
  text-align: left;
  padding: 4px 8px;
  color: #555;
  font-family: 'IBM Plex Mono', monospace;
}}

.trend-row {{
  font-size: 11px;
  display: flex;
  gap: 6px;
  justify-content: center;
  padding: 4px 0;
  font-family: 'IBM Plex Mono', monospace;
  color: #555;
  flex-wrap: wrap;
}}

select {{
  background: rgba(255,255,255,0.7);
  border: 1px solid rgba(0,0,0,0.12);
  border-radius: 6px;
  padding: 2px 6px;
  font-size: 11px;
  margin: 4px 0;
  font-family: 'IBM Plex Mono', monospace;
}}

/* Mobile: untereinander */
@media (max-width: 600px) {{
  .row {{ flex-direction: column; }}
}}
</style>
<script src="https://cdn.plot.ly/plotly-3.0.0.min.js"></script>
</head>
<body>

<div class="row">
  <!-- Wind Gauge -->
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
      <option value="1.944">kn</option>
      <option value="3.6">km/h</option>
    </select>
  </div>

  <!-- Windrichtung -->
  <div class="cell">
    <div id="chart_dir"></div>
    <div id="wind_dirvar" class="addon"></div>
  </div>

  <!-- Windrose -->
  <div class="cell">
    <div id="chart_rose"></div>
  </div>
</div>

<script>
var m = {act_json};

var cfg = {{displaylogo:false, displayModeBar:false, responsive:true}};
var bgr = "rgba(0,0,0,0)";
var fc  = "#1a1a1a";
var col_green  = "#33f9ff";
var col_yellow = "#f6fc18";
var col_red    = "LightSalmon";
var col_bar    = "darkblue";
var margin_g   = {{t:40, r:20, l:20, b:10}};

var cur   = Number(m.windspeed_ms);
var old   = Number(m.wind_speed_old);
var max24 = Number(m.wind_speed_max_24);
var min24 = Number(m.wind_speed_min_24);
var t1    = Math.round((cur - Number(m.wind_speed_1h))  * 100)/100;
var t3    = Math.round((cur - Number(m.wind_speed_3h))  * 100)/100;
var t24   = Math.round((cur - Number(m.wind_speed_24h)) * 100)/100;
var raw   = {{cur:cur, old:old, max24:max24, min24:min24, t1:t1, t3:t3, t24:t24}};

function trend_span(val, fact) {{
  var col = val >= 0 ? "#2e9e5b" : "#e05c2a";
  return '<span style="color:'+col+';">' + Math.round(val*fact*10)/10 + '</span>';
}}

function updateUnit() {{
  var fact = parseFloat(document.getElementById("wind_unit").value);
  var ustr = document.getElementById("wind_unit").options[document.getElementById("wind_unit").selectedIndex].text;
  document.getElementById("wind_max").innerHTML =
    'max: <b>' + Math.round(raw.max24*fact*10)/10 + '</b> &nbsp; min: <b>' + Math.round(raw.min24*fact*10)/10 + '</b>';
  document.getElementById("wind_1h").innerHTML  = '-1h: '  + trend_span(raw.t1,  fact);
  document.getElementById("wind_3h").innerHTML  = '-3h: '  + trend_span(raw.t3,  fact);
  document.getElementById("wind_24h").innerHTML = '-24h: ' + trend_span(raw.t24, fact);
  var fg = {{
    axis:  {{range:[0, 30*fact], tickwidth:1, tickcolor:col_bar}},
    bar:   {{color:col_bar}},
    bgcolor:"white", borderwidth:2, bordercolor:"#ccc",
    steps: [{{range:[0,       2*fact], color:col_green}},
            {{range:[2*fact, 18*fact], color:col_yellow}},
            {{range:[18*fact,30*fact], color:col_red}}]
  }};
  Plotly.react("chart_wind", [{{
    type:"indicator", mode:"gauge+number+delta",
    value: Math.round(raw.cur*fact*10)/10,
    number:{{suffix:ustr, font:{{size:28}}}},
    title:{{text:"Wind", font:{{size:16, color:fc}}}},
    delta:{{reference: Math.round(raw.old*fact*10)/10,
            increasing:{{color:"#2e9e5b"}}, decreasing:{{color:"#e05c2a"}}}},
    gauge: fg
  }}], {{margin:margin_g, paper_bgcolor:bgr, font:{{color:fc, family:"IBM Plex Sans"}}, height:200}}, cfg);
}}

// --- Wind Gauge ---
Plotly.newPlot("chart_wind", [{{
  type:"indicator", mode:"gauge+number+delta",
  value: cur, number:{{suffix:"m/s", font:{{size:28}}}},
  title:{{text:"Wind", font:{{size:16, color:fc}}}},
  delta:{{reference:old, increasing:{{color:"#2e9e5b"}}, decreasing:{{color:"#e05c2a"}}}},
  gauge:{{
    axis:  {{range:[0,30], tickwidth:1, tickcolor:col_bar}},
    bar:   {{color:col_bar}},
    bgcolor:"white", borderwidth:2, bordercolor:"#ccc",
    steps: [{{range:[0,2],  color:col_green}},
            {{range:[2,18], color:col_yellow}},
            {{range:[18,30],color:col_red}}]
  }}
}}], {{margin:margin_g, paper_bgcolor:bgr, font:{{color:fc,family:"IBM Plex Sans"}}, height:200}}, cfg);

// --- Wind Richtung ---
var dir_avg = Number(m.wind_dir_avg);
var dir_max = Number(m.wind_dir_max);
var delta = dir_max > dir_avg ? (dir_max-dir_avg)/2 : (360+dir_max-dir_avg)/2;
if (delta < 10) delta = 10;
document.getElementById("wind_dirvar").innerHTML =
  'Dir: <b>' + dir_avg + '°</b> &nbsp; Var: <b>' + Math.round(delta*10)/10 + '°</b>';

Plotly.newPlot("chart_dir", [{{
  type:"barpolar", r:[1], theta:[dir_avg], width:[delta],
  marker:{{color:['#fc0435']}}, showlegend:false
}}], {{
  margin:margin_g, paper_bgcolor:bgr, height:200,
  font:{{color:fc, family:"IBM Plex Sans"}},
  title:{{text:"Mittl. Windrichtung", font:{{size:16, color:fc}}}},
  polar:{{
    bgcolor:'#7ed3f5', radialaxis:{{visible:false}},
    angularaxis:{{
      direction:"clockwise", tickmode:"array",
      tickvals:[0,22.5,45,67.5,90,112.5,135,157.5,180,202.5,225,247.5,270,292.5,315,337.5],
      ticktext:["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"],
      ticks:"", tickfont:{{size:9}}, showline:true
    }}
  }}
}}, cfg);

// --- Windrose ---
var theta = ['N','NNO','NO','ONO','O','OSO','SO','SSO','S','SSW','SW','WSW','W','WNW','NW','NNW'];
var colors = ['rgb(41,231,243)','rgb(41,136,243)','rgb(44,243,41)','rgb(92,247,15)',
              'rgb(247,244,15)','rgb(247,89,15)','rgb(247,15,54)','rgb(245,20,242)'];
var idx_labels = ['0-1.5kn','1.5-3.3kn','3.3-5.5kn','5.5-7.9kn',
                  '7.9-10.7kn','10.7-13.8kn','13.8-17.1kn','>17.1kn'];
var rose_data = []; var cur_ws = ''; var rv = new Array(16).fill(0);
for (var x in m.wind_trend) {{
  var line = m.wind_trend[x];
  if (line.wind_speed != cur_ws && cur_ws != '') {{
    rose_data.push({{r:rv.slice(), theta:theta, name:cur_ws,
                    marker:{{color:colors[idx_labels.indexOf(cur_ws)]}}, type:"barpolar"}});
    rv = new Array(16).fill(0);
  }}
  var ti = theta.indexOf(line.wind_dir);
  if (ti >= 0) rv[ti] = Number(line.occur);
  cur_ws = line.wind_speed;
}}
if (cur_ws) rose_data.push({{r:rv.slice(), theta:theta, name:cur_ws,
                              marker:{{color:colors[idx_labels.indexOf(cur_ws)]}}, type:"barpolar"}});

Plotly.newPlot("chart_rose", rose_data, {{
  title:{{text:"Wind letzte Stunde", font:{{size:16, color:fc}}}},
  margin:margin_g, paper_bgcolor:bgr, height:200,
  font:{{color:fc, family:"IBM Plex Sans"}},
  polar:{{barmode:"overlay", bargap:0,
          radialaxis:{{ticksuffix:"%", angle:0, dtick:20}},
          angularaxis:{{direction:"clockwise"}}}}
}}, cfg);

updateUnit();
</script>
</body>
</html>
"""

    st.components.v1.html(BOJE_HTML, height=380, scrolling=False)

# ======================
# Klimaboje AGS — Wind
# ======================
st.markdown('<div class="section-title">Klimaboje AGS — Wind (Traunkirchen)</div>', unsafe_allow_html=True)

BOJE_BASE = "https://www.klimaboje.at/my_Weather_boje.php"
BOJE_HEADERS = {
    "Referer": "https://www.klimaboje.at/?page_id=1481",
    "X-Requested-With": "XMLHttpRequest",
    "User-Agent": "Mozilla/5.0",
}

@st.cache_data(ttl=60, show_spinner=False)
def fetch_boje_act():
    r = requests.post(
        f"{BOJE_BASE}?what=meas_act_mysql&station=ags",
        headers=BOJE_HEADERS, timeout=10
    )
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_boje_trend():
    r = requests.post(
        f"{BOJE_BASE}?what=meas_trend_mysql&period=2&station=ags",
        headers=BOJE_HEADERS, timeout=10
    )
    r.raise_for_status()
    return r.text  # kein JSON — pipe-delimited String

try:
    with st.spinner("Klimaboje-Daten …"):
        act = fetch_boje_act()
        trend_raw = fetch_boje_trend()

    # --- Aktuelle Kennzahlen ---
    wind_ms   = float(act.get("windspeed_ms", 0))
    wind_kt   = round(wind_ms * 1.944, 1)
    wind_dir  = float(act.get("wind_dir_avg", 0))
    wind_max  = round(float(act.get("wind_speed_max", 0)) * 1.944, 1)

    ca, cb, cc = st.columns(3)
    with ca:
        st.markdown(metric_card("AGS Wind", f"{wind_kt:.1f}", "kt"), unsafe_allow_html=True)
    with cb:
        st.markdown(metric_card("AGS Böe (max)", f"{wind_max:.1f}", "kt"), unsafe_allow_html=True)
    with cc:
        st.markdown(metric_card("AGS Richtung", f"{wind_dir:.0f}", "°"), unsafe_allow_html=True)

    # --- Zeitreihe parsen ---
    blocks = trend_raw.split("||xx||")
    names  = blocks[0].split(",")
    times  = blocks[1].split(",")

    def get_series(key):
        idx = names.index(key)
        return [float(v) if v not in ("", "None") else None
                for v in blocks[idx + 1].split(",")]

    ws_max = get_series("wind_speed_max")
    ws_avg = get_series("wind_speed_avg")
    wd_avg = get_series("wind_dir_avg")

    # m/s → kt
    ws_max_kt = [round(v * 1.944, 1) if v is not None else None for v in ws_max]
    ws_avg_kt = [round(v * 1.944, 1) if v is not None else None for v in ws_avg]

    # --- Windgeschwindigkeit Chart ---
    fig_boje = make_subplots(specs=[[{"secondary_y": True}]])

    fig_boje = add_now_and_today(fig_boje)

    fig_boje.update_layout(
        yaxis_title="Wind (kt)",
        legend=dict(orientation="h", y=-0.2),
        margin=dict(t=20, b=50),
        plot_bgcolor="rgba(255,255,255,0.5)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans"),
        height=320,
        dragmode="zoom",
    )
    fig_boje.update_yaxes(
        title_text="Richtung (°)", secondary_y=True,
        range=[0, 360], fixedrange=True, showgrid=False
    )
    fig_boje.update_yaxes(fixedrange=True, secondary_y=False)
    fig_boje.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.05)", type="date")

    st.plotly_chart(fig_boje, use_container_width=True, config=PLOTLY_CONFIG)

except Exception as e:
    st.warning(f"⚠️ Klimaboje nicht erreichbar: {e}")


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
st.markdown('<div class="section-title">Webcam — Traunkirchen (SCT)</div>', unsafe_allow_html=True)
st.components.v1.iframe(
    "https://g0.ipcamlive.com/player/player.php?alias=sctpano180",
    height=500,
    scrolling=False,
)

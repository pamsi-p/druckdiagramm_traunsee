# app.py
import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, timedelta

# ======================
# Orte & Koordinaten
# ======================
coords = {
    "Traunkirchen": (47.993, 13.745),
    "Gmunden": (47.918, 13.799),
    "Bad_Ischl": (47.714, 13.632),
    "Ried": (48.198, 13.490)
}

# ======================
# Wetterdaten abrufen
# ======================
def fetch_openmeteo(start, end, lat, lon):
    url = "https://archive-api.open-meteo.com/v1/archive" if end <= date.today() else "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "hourly": "pressure_msl,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,wind_speed_10m,wind_direction_10m",
        "timezone": "Europe/Vienna"
    }
    r = requests.get(url, params=params)
    r.raise_for_status()
    df = pd.DataFrame(r.json()["hourly"])
    df["time"] = pd.to_datetime(df["time"]).dt.tz_localize("Europe/Vienna")
    df.set_index("time", inplace=True)
    return df

# ======================
# UI & Datenvorbereitung
# ======================
st.title("Traunsee Druckgradient")

# Standard-Zeitraum: Heute + 2 Tage
default_start = date.today()
default_end = date.today() + timedelta(days=2)

start_date = st.date_input("Startdatum", default_start)
end_date = st.date_input("Enddatum", default_end)

if end_date < start_date:
    st.error("Enddatum muss nach Startdatum sein")
    st.stop()

# Daten abrufen
dfs = {name: fetch_openmeteo(start_date, end_date, lat, lon) for name, (lat, lon) in coords.items()}

# Druckdifferenzen & Zusatzdaten
df = dfs["Traunkirchen"].rename(columns={"pressure_msl": "P_T"})
df["P_G"] = dfs["Gmunden"]["pressure_msl"]
df["P_B"] = dfs["Bad_Ischl"]["pressure_msl"]
df["P_R"] = dfs["Ried"]["pressure_msl"]
df["delta_P_TG"] = df["P_T"] - df["P_G"]
df["delta_P_BR"] = df["P_B"] - df["P_R"]
df["wind_speed_kt"] = dfs["Traunkirchen"]["wind_speed_10m"] * 1.94384
df["wind_dir"] = dfs["Traunkirchen"]["wind_direction_10m"]

# ======================
# 1. ΔP & Gesamtbewölkung
# ======================
fig = make_subplots(specs=[[{"secondary_y": True}]])

fig.add_trace(go.Scatter(x=df.index, y=df["delta_P_TG"], name="ΔP Traunkirchen–Gmunden", line=dict(color="grey")), secondary_y=False)
fig.add_trace(go.Scatter(x=df.index, y=df["delta_P_BR"], name="ΔP Bad Ischl–Ried", line=dict(color="deepskyblue")), secondary_y=False)
fig.add_trace(go.Scatter(x=df.index, y=df["cloud_cover"], name="clouds total [Okta]", visible="legendonly", line=dict(color="black")), secondary_y=True)

# --- Markierung heutiger Tag ---
today = pd.Timestamp.now(tz="Europe/Vienna").normalize()
tomorrow = today + pd.Timedelta(days=1)
fig.add_vrect(
    x0=today, x1=tomorrow,
    fillcolor="yellow", opacity=0.2,
    layer="below", line_width=0
)

# --- Linie für "Jetzt" ---
now = pd.Timestamp.now(tz="Europe/Vienna")
if df.index.min() <= now <= df.index.max():
    fig.add_shape(type="line", x0=now, x1=now, y0=0, y1=1, line=dict(color="orange", width=3, dash="dot"), xref="x", yref="paper")
    fig.add_annotation(x=now, y=1, text="Jetzt", showarrow=False, xanchor="left", xref="x", yref="paper", font=dict(color="orange"))


# --- Horizontale Linie bei 1.5 hPa ---
fig.add_hline(
    y=1.5,
    line=dict(color="red", dash="dash"),
    annotation_text="Oberwind Süd",
    annotation_position="top right"
)


# --- Layout ---
fig.update_layout(
    title="Druckdifferenz und Gesamtbewölkung",
    xaxis_title="Datum",
    yaxis_title="ΔP [hPa]",
    legend=dict(orientation="h", y=-0.25),
    margin=dict(t=50, b=60),
    dragmode="zoom"
)
fig.update_yaxes(title_text="clouds [Okta]", secondary_y=True, fixedrange=True)

st.plotly_chart(fig, use_container_width=True)

# ======================
# 2. Profiwetter Bild
# ======================
st.header("Profiwetter MOS - Traunkirchen")

st.image("https://profiwetter.ch/mos_P0062.svg?t=1756145032", caption="Profiwetter MOS", use_container_width=True)


# ======================
# 3. AROME Slider (Karussell)
# ======================
import streamlit as st

# --- AROME Slider Bilderliste ---
arome_images = [
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_01.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_02.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_03.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_04.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_05.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_06.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_07.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_08.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_09.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_10.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_11.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_12.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_13.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_14.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_15.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_16.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_17.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_18.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_19.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_20.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_21.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_22.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_23.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_24.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_25.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_26.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_27.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_28.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_29.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_30.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_31.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_32.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_33.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_34.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_35.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_36.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_37.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_38.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_39.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_40.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_41.png",
    "https://kitewetter.at/wp-content/arome/arome_tr_run_00_ID_42.png"
]

# --- Streamlit Karussell ---
st.markdown("## AROME Prognose (von kitewetter.at)")

selected_index = st.slider(
    "Wähle ein Bild",
    min_value=0,
    max_value=len(arome_images)-1,
    value=0,
    step=1
)
st.image(arome_images[selected_index], use_container_width=True)
st.caption(f"Bild {selected_index + 1} von {len(arome_images)}")

# --- Miniaturbild-Galerie zum Scrollen ---
st.markdown("### Miniaturansicht (klickbar)")
cols = st.columns(6)
for i, img_url in enumerate(arome_images):
    with cols[i % 6]:
        if st.button(f"", key=f"thumb_{i}"):
            selected_index = i
        st.image(img_url, width=80)

# # ======================
# # 2. Wolken-Schichtplot
# # ======================
# fig_clouds = go.Figure()
# for col, name, color in [
#     ("cloud_cover_low", "Wolken unten", "lightblue"),
#     ("cloud_cover_mid", "Wolken Mitte", "deepskyblue"),
#     ("cloud_cover_high", "Wolken oben", "dodgerblue")
# ]:
#     fig_clouds.add_trace(go.Scatter(x=df.index, y=df[col], mode='lines', name=name, stackgroup='cloud', line=dict(width=0.5, color=color)))

# fig_clouds.update_layout(
#     title='Wolkenbedeckung (Traunkirchen)',
#     xaxis_title='Zeit',
#     yaxis_title='Wolkenbedeckung (Anteil)',
#     yaxis=dict(range=[0, 4], fixedrange=True),
#     legend=dict(orientation='h', y=1.1),
#     margin=dict(t=50, b=60),
#     dragmode="zoom"
# )
# st.plotly_chart(fig_clouds, use_container_width=True)

# # ======================
# # 3. Winddiagramm
# # ======================
# fig_wind = go.Figure()

# fig_wind.add_trace(go.Scatter(
#     x=df.index, y=df["wind_speed_kt"], mode='lines+markers',
#     name='Windstärke (kt)', line=dict(color='orange'), yaxis='y1'))

# fig_wind.add_trace(go.Scatter(
#     x=df.index, y=df["wind_dir"], mode='lines',
#     name='Windrichtung (°)', line=dict(color='green', dash='dot'), yaxis='y2'))

# fig_wind.update_layout(
#     title='Windstärke & Windrichtung (Traunkirchen)',
#     xaxis_title='Zeit',
#     yaxis=dict(title='Windstärke (kt)', range=[0, df["wind_speed_kt"].max() * 1.2], fixedrange=True),
#     yaxis2=dict(title='Windrichtung (°)', overlaying='y', side='right', range=[0, 360], showgrid=False, fixedrange=True),
#     legend=dict(orientation='h', y=1.1),
#     margin=dict(t=50, b=60),
#     dragmode="zoom"
# )
# st.plotly_chart(fig_wind, use_container_width=True)

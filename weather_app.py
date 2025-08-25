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
fig.add_trace(go.Scatter(x=df.index, y=df["cloud_cover"], name="clouds total [Okta]", line=dict(color="black")), secondary_y=True)

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

st.image("https://profiwetter.ch/mos_P0062.svg?t=1756145032", caption="Profiwetter MOS", use_container_width=True)


# ======================
# 2. Wolken-Schichtplot
# ======================
fig_clouds = go.Figure()
for col, name, color in [
    ("cloud_cover_low", "Wolken unten", "lightblue"),
    ("cloud_cover_mid", "Wolken Mitte", "deepskyblue"),
    ("cloud_cover_high", "Wolken oben", "dodgerblue")
]:
    fig_clouds.add_trace(go.Scatter(x=df.index, y=df[col], mode='lines', name=name, stackgroup='cloud', line=dict(width=0.5, color=color)))

fig_clouds.update_layout(
    title='Wolkenbedeckung (Traunkirchen)',
    xaxis_title='Zeit',
    yaxis_title='Wolkenbedeckung (Anteil)',
    yaxis=dict(range=[0, 4], fixedrange=True),
    legend=dict(orientation='h', y=1.1),
    margin=dict(t=50, b=60),
    dragmode="zoom"
)
st.plotly_chart(fig_clouds, use_container_width=True)

# ======================
# 3. Winddiagramm
# ======================
fig_wind = go.Figure()

fig_wind.add_trace(go.Scatter(
    x=df.index, y=df["wind_speed_kt"], mode='lines+markers',
    name='Windstärke (kt)', line=dict(color='orange'), yaxis='y1'))

fig_wind.add_trace(go.Scatter(
    x=df.index, y=df["wind_dir"], mode='lines',
    name='Windrichtung (°)', line=dict(color='green', dash='dot'), yaxis='y2'))

fig_wind.update_layout(
    title='Windstärke & Windrichtung (Traunkirchen)',
    xaxis_title='Zeit',
    yaxis=dict(title='Windstärke (kt)', range=[0, df["wind_speed_kt"].max() * 1.2], fixedrange=True),
    yaxis2=dict(title='Windrichtung (°)', overlaying='y', side='right', range=[0, 360], showgrid=False, fixedrange=True),
    legend=dict(orientation='h', y=1.1),
    margin=dict(t=50, b=60),
    dragmode="zoom"
)
st.plotly_chart(fig_wind, use_container_width=True)

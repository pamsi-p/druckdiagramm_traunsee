import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, timedelta

# -----------------------------
# Settings & Location Data
# -----------------------------
st.set_page_config(layout="wide")
st.title("Traunsee Druckgradienten, Bewölkung & Wind (AROME)")

coords = {
    "Traunkirchen": (47.993, 13.745),
    "Gmunden": (47.918, 13.799),
    "Bad_Ischl": (47.714, 13.632),
    "Ried": (48.198, 13.490)
}

# -----------------------------
# Modernes Datumsauswahl UI
# -----------------------------
st.sidebar.header("Zeitraum wählen")
def_date = date.today()
start_date, end_date = st.sidebar.date_input(
    "Start- und Enddatum",
    value=[def_date - timedelta(days=3), def_date + timedelta(days=2)],
    min_value=def_date - timedelta(days=365),
    max_value=def_date + timedelta(days=7)
)

if start_date > end_date:
    st.error("Startdatum darf nicht nach Enddatum liegen.")
    st.stop()

# -----------------------------
# Fetch: Forecast & Archive API (Open-Meteo)
# -----------------------------
def fetch_pressure_and_cloud(start, end, lat, lon):
    today = date.today()
    use_archive = end <= today

    url = "https://archive-api.open-meteo.com/v1/archive" if use_archive else "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": "pressure_msl,cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high",
        "timezone": "Europe/Vienna"
    }

    r = requests.get(url, params=params)
    r.raise_for_status()
    df = pd.DataFrame(r.json()["hourly"])
    df["time"] = pd.to_datetime(df["time"])
    df.set_index("time", inplace=True)
    return df

# -----------------------------
# Fetch: AROME Winddaten
# -----------------------------
def fetch_wind_arome(lat, lon, start, end):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": "wind_speed_10m,wind_direction_10m",
        "model": "dmi_harmonie_arome",   # AROME Modell bei Open-Meteo
        "timezone": "Europe/Vienna"
    }
    r = requests.get(url, params=params)
    r.raise_for_status()
    df = pd.DataFrame(r.json()["hourly"])
    df["time"] = pd.to_datetime(df["time"])
    df.set_index("time", inplace=True)
    return df


# -----------------------------
# Daten abrufen
# -----------------------------
st.info("Lade Wetterdaten...")
df_data = {}
for name, (lat, lon) in coords.items():
    df_data[name] = fetch_pressure_and_cloud(start_date, end_date, lat, lon)

wind_df = fetch_wind_arome(*coords["Traunkirchen"], start_date, end_date)

# Druckgradienten berechnen
main_df = df_data["Traunkirchen"][["pressure_msl"]].rename(columns={"pressure_msl": "P_T"})
main_df["P_G"] = df_data["Gmunden"]["pressure_msl"]
main_df["P_B"] = df_data["Bad_Ischl"]["pressure_msl"]
main_df["P_R"] = df_data["Ried"]["pressure_msl"]
main_df["delta_TG"] = main_df["P_T"] - main_df["P_G"]
main_df["delta_BR"] = main_df["P_B"] - main_df["P_R"]
main_df["cloud"] = df_data["Traunkirchen"]["cloud_cover"] / 100 * 4
main_df["cloud"] = main_df["cloud"].clip(0, 4)

# -----------------------------
# Plot: Druck & Bewölkung
# -----------------------------
fig = go.Figure()
fig.add_trace(go.Scatter(x=main_df.index, y=main_df["delta_TG"], name="ΔP Traunkirchen-Gmunden", line=dict(color="grey")))
fig.add_trace(go.Scatter(x=main_df.index, y=main_df["delta_BR"], name="ΔP Bad Ischl-Ried", line=dict(color="deepskyblue")))
fig.add_trace(go.Scatter(x=main_df.index, y=main_df["cloud"], name="Clouds Total [Okta/2]", line=dict(color="black")))
fig.add_hline(y=1.5, line=dict(color="red", dash="dash"), annotation_text="Oberwind - Süd", annotation_position="top right")
fig.update_layout(title="Druckgradienten & Bewölkung", yaxis_title="hPa / Okta", xaxis_title="Zeit", legend=dict(orientation="h"))
st.plotly_chart(fig, use_container_width=True)

# -----------------------------
# Wind Visualisierung
# -----------------------------
st.subheader("Wind (AROME - Traunkirchen)")
wind_df = wind_df.loc[start_date.strftime("%Y-%m-%d"):end_date.strftime("%Y-%m-%d")]

# Windrichtung als Farbpunkt + Richtung
fig2 = px.scatter(
    wind_df.reset_index(),
    x="time", y="wind_speed_10m",
    color="wind_direction_10m",
    color_continuous_scale="twilight",
    labels={"wind_speed_10m": "Windgeschwindigkeit (km/h)", "wind_direction_10m": "Windrichtung [°]"},
    title="Windrichtung & Geschwindigkeit (AROME - 10m)"
)
fig2.update_traces(marker=dict(size=6))
st.plotly_chart(fig2, use_container_width=True)

st.caption("Winddaten basieren auf AROME-Vorhersagemodell (ca. 48h Vorschau verfügbar)")

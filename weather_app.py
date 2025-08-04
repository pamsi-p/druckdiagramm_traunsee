import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests

st.set_page_config(layout="wide")
st.title("Traunsee Prognose - Druckdifferenz & Bewölkung")

# Koordinaten
orte = {
    "Traunkirchen": {"lat": 47.848, "lon": 13.791},
    "Gmunden": {"lat": 47.918, "lon": 13.799},
    "Bad Ischl": {"lat": 47.711, "lon": 13.619},
    "Ried im Innkreis": {"lat": 48.210, "lon": 13.492}
}

# Open-Meteo URL Builder
def build_url(lat, lon):
    return (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&hourly=pressure_msl,cloudcover,cloudcover_low,cloudcover_mid,cloudcover_high"
        f"&past_days=3&forecast_days=4"
        f"&timezone=Europe%2FBerlin"
    )

# Daten abrufen
def get_weather_df(name, lat, lon, include_clouds=False):
    url = build_url(lat, lon)
    r = requests.get(url)
    data = r.json()
    df = pd.DataFrame(data["hourly"])
    df["time"] = pd.to_datetime(df["time"])
    df.set_index("time", inplace=True)

    df = df.rename(columns={"pressure_msl": f"pressure_{name}"})

    if include_clouds:
        return df[[f"pressure_{name}", "cloudcover", "low", "mid", "high"]]
    else:
        return df[[f"pressure_{name}"]]


with st.spinner("📡 Lade Wetterdaten..."):
    df_tk = get_weather_df("Traunkirchen", **orte["Traunkirchen"], include_clouds=True)
    df_gm = get_weather_df("Gmunden", **orte["Gmunden"])
    df_bi = get_weather_df("BadIschl", **orte["Bad Ischl"])
    df_rd = get_weather_df("Ried", **orte["Ried im Innkreis"])


# Zusammenführen & berechnen
df = pd.concat([df_tk, df_gm, df_bi, df_rd], axis=1)
df = df.interpolate()

df["delta_TG"] = df["pressure_Traunkirchen"] - df["pressure_Gmunden"]
df["delta_BR"] = df["pressure_BadIschl"] - df["pressure_Ried"]
df["clouds_scaled"] = df["cloudcover"] / 25  # (Okta/2)

# Diagramm
fig = go.Figure()

# Druckdifferenzen
fig.add_trace(go.Scatter(x=df.index, y=df["delta_TG"], name="ΔP Traunkirchen - Gmunden", line=dict(color="gray")))
fig.add_trace(go.Scatter(x=df.index, y=df["delta_BR"], name="ΔP Bad Ischl - Ried", line=dict(color="deepskyblue", width=2)))

# Bewölkung (gesamt, skaliert)
fig.add_trace(go.Scatter(x=df.index, y=df["clouds_scaled"], name="Clouds total (Okta/2)", line=dict(color="black", width=1.5)))

# Schwelle Oberwind
fig.add_hline(y=1.5, line=dict(color="red", dash="dash"), annotation_text="Oberwind – Süd", annotation_position="top right", annotation_font_color="red")

# Heatmap für Wolkenschichten
cloud_matrix = np.stack([df["high"].values, df["mid"].values, df["low"].values])
fig.add_trace(go.Heatmap(
    z=cloud_matrix,
    x=df.index,
    y=["H", "M", "L"],
    colorscale="gray",
    showscale=True,
    colorbar=dict(title="Clouds (%)", orientation="h", x=0.5, xanchor="center", y=1.15)
))

fig.update_layout(
    height=600,
    margin=dict(l=40, r=20, t=60, b=40),
    xaxis_title="Zeit",
    yaxis_title="ΔP [hPa]; clouds [Okta/2]",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    hovermode="x unified"
)

st.plotly_chart(fig, use_container_width=True)
st.caption("ΔP: Druckdifferenz, Okta: 0–8 Skala für Bewölkung. Quelle: open-meteo.com")

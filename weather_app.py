
import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import date, timedelta

# Koordinaten:
coords = {
    "Traunkirchen": (47.993,13.745),
    "Gmunden": (47.918,13.799),
    "Bad_Ischl": (47.714,13.632),
    "Ried": (48.198,13.490)
}

def fetch_openmeteo(start, end, lat, lon):
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "hourly": ["pressure_msl","cloud_cover","cloud_cover_low","cloud_cover_mid","cloud_cover_high",
                   "wind_speed_10m","wind_direction_10m"],
        "timezone": "Europe/Vienna",
        "past_days": (date.today()-start).days
    }
    r = requests.get(url, params=params)
    r.raise_for_status()
    return pd.DataFrame(r.json()["hourly"])

st.title("Druckgradienten, Bewölkung & Wind (AROME)")
start_date = st.date_input("Startdatum", date.today() - timedelta(days=5))
end_date = st.date_input("Enddatum", date.today() + timedelta(days=7))
if end_date < start_date: st.error("Enddatum muss nach Startdatum sein")
else:
    # hole Daten für 4 Orte
    dfs = {}
    for name,(lat,lon) in coords.items():
        dfs[name] = fetch_openmeteo(start_date, end_date, lat, lon)
    # Druckgradienten berechnen: P_T–P_G, P_B–P_R
    df = dfs["Traunkirchen"].rename(columns={"pressure_msl":"P_T"})
    df["P_G"] = dfs["Gmunden"]["pressure_msl"]
    df["delta_P_TG"] = df["P_T"] - df["P_G"]
    df["P_B"] = dfs["Bad_Ischl"]["pressure_msl"]
    df["P_R"] = dfs["Ried"]["pressure_msl"]
    df["delta_P_BR"] = df["P_B"] - df["P_R"]
    df["cloud_total"] = dfs["Traunkirchen"]["cloud_cover"] / 100 * 4
    df["cloud_low"] = dfs["Traunkirchen"]["cloud_cover_low"]
    df["cloud_mid"] = dfs["Traunkirchen"]["cloud_cover_mid"]
    df["cloud_high"] = dfs["Traunkirchen"]["cloud_cover_high"]
    df["wind_speed"] = dfs["Traunkirchen"]["wind_speed_10m"]
    df["wind_dir"] = dfs["Traunkirchen"]["wind_direction_10m"]
    # Plotly
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["delta_P_TG"], name="ΔP Traunkirchen–Gmunden", line=dict(color="grey")))
    fig.add_trace(go.Scatter(x=df.index, y=df["delta_P_BR"], name="ΔP Bad Ischl–Ried", line=dict(color="deepskyblue")))
    fig.add_trace(go.Scatter(x=df.index, y=df["cloud_total"], name="clouds total [Okta/2]", line=dict(color="black")))
    fig.add_hline(y=1.5, line=dict(color="red", dash="dash"), annotation_text="Oberwind – Süd", annotation_position="top right")
    fig.update_layout(yaxis_title="δP [hPa]; clouds [Okta/2]",
                      xaxis_title="Datum & Stunde",
                      legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, use_container_width=True)
    # Windoption: Pfeile oder Richtungsplot
    st.subheader("Windrichtung & -stärke (eine Stelle, z.B. Traunkirchen)")
    st.line_chart(df[["wind_speed"]])
    st.write("Richtung [°]:")
    st.line_chart(df["wind_dir"])

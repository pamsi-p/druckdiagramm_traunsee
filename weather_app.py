# app.py
import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import date, timedelta
from plotly.subplots import make_subplots

# Koordinaten:
coords = {
    "Traunkirchen": (47.993,13.745),
    "Gmunden": (47.918,13.799),
    "Bad_Ischl": (47.714,13.632),
    "Ried": (48.198,13.490)
}

def fetch_openmeteo(start, end, lat, lon):
    today = date.today()
    if end <= today:
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": lat, "longitude": lon,
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "hourly": ",".join([
                "pressure_msl", "cloud_cover", "cloud_cover_low",
                "cloud_cover_mid", "cloud_cover_high",
                "wind_speed_10m", "wind_direction_10m"
            ]),
            "timezone": "Europe/Vienna"
        }
    else:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat, "longitude": lon,
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "hourly": ",".join([
                "pressure_msl", "cloud_cover", "cloud_cover_low",
                "cloud_cover_mid", "cloud_cover_high",
                "wind_speed_10m", "wind_direction_10m"
            ]),
            "timezone": "Europe/Vienna"
        }

    r = requests.get(url, params=params)
    r.raise_for_status()
    data = r.json()
    df = pd.DataFrame(data["hourly"])
    df["time"] = pd.to_datetime(df["time"])
    df.set_index("time", inplace=True)
    return df


st.title("Traunsee Druckgradient")
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
    df["cloud_total"] = dfs["Traunkirchen"]["cloud_cover"]
    df["cloud_low"] = dfs["Traunkirchen"]["cloud_cover_low"]
    df["cloud_mid"] = dfs["Traunkirchen"]["cloud_cover_mid"]
    df["cloud_high"] = dfs["Traunkirchen"]["cloud_cover_high"]
    df["wind_speed"] = dfs["Traunkirchen"]["wind_speed_10m"]
    df["wind_dir"] = dfs["Traunkirchen"]["wind_direction_10m"]


# =========================
# 1. ΔP & Clouds Plot
# =========================
fig = make_subplots(specs=[[{"secondary_y": True}]])

# Primäre Y-Achse (ΔP)
fig.add_trace(go.Scatter(x=df.index, y=df["delta_P_TG"],
                         name="ΔP Traunkirchen–Gmunden",
                         line=dict(color="grey")),
              secondary_y=False)

fig.add_trace(go.Scatter(x=df.index, y=df["delta_P_BR"],
                         name="ΔP Bad Ischl–Ried",
                         line=dict(color="deepskyblue")),
              secondary_y=False)

# Sekundäre Y-Achse (clouds total)
fig.add_trace(go.Scatter(x=df.index, y=df["cloud_total"],
                         name="clouds total [Okta]",
                         line=dict(color="black")),
              secondary_y=True)

# Horizontale Linie (als Shape)
fig.add_shape(
    type="line",
    x0=df.index.min(),
    x1=df.index.max(),
    y0=1.5,
    y1=1.5,
    line=dict(color="red", dash="dash"),
    yref="y",  # primäre y-Achse
    xref="x"
)

fig.add_annotation(
    x=df.index.max(),
    y=1.5,
    text="Oberwind – Süd",
    showarrow=False,
    yanchor="bottom",
    xanchor="right"
)

fig.update_layout(
    title="ΔP und Gesamtbewölkung",
    xaxis_title="Datum",
    yaxis_title="ΔP [hPa]",
    legend=dict(orientation="h", y=-0.25),
    margin=dict(t=50, b=60)
)

fig.update_yaxes(title_text="clouds [Okta]", secondary_y=True)

st.plotly_chart(fig, use_container_width=True)

# =========================
# 2. Cloud Stack Plot
# =========================
fig_clouds = go.Figure()

fig_clouds.add_trace(go.Scatter(
    x=df.index,
    y=df["cloud_low"],
    mode='lines',
    name='Wolken unten',
    stackgroup='cloud',
    line=dict(width=0.5, color='lightblue'),
))

fig_clouds.add_trace(go.Scatter(
    x=df.index,
    y=df["cloud_mid"],
    mode='lines',
    name='Wolken Mitte',
    stackgroup='cloud',
    line=dict(width=0.5, color='deepskyblue'),
))

fig_clouds.add_trace(go.Scatter(
    x=df.index,
    y=df["cloud_high"],
    mode='lines',
    name='Wolken oben',
    stackgroup='cloud',
    line=dict(width=0.5, color='dodgerblue'),
))

fig_clouds.update_layout(
    title='Wolkenbedeckung (Traunkirchen)',
    xaxis_title='Zeit',
    yaxis_title='Wolkenbedeckung (Anteil)',
    yaxis=dict(range=[0, 4]),
    legend=dict(orientation='h', y=1.1),
    margin=dict(t=50, b=60)
)

st.plotly_chart(fig_clouds, use_container_width=True)

# =========================
# 3. Winddiagramm
# =========================
fig_wind = go.Figure()

fig_wind.add_trace(go.Scatter(
    x=df.index,
    y=df["wind_speed"],
    mode='lines+markers',
    name='Windstärke (m/s)',
    line=dict(color='orange'),
    yaxis='y1'
))

fig_wind.add_trace(go.Scatter(
    x=df.index,
    y=df["wind_dir"],
    mode='lines',
    name='Windrichtung (°)',
    line=dict(color='green', dash='dot'),
    yaxis='y2'
))

fig_wind.update_layout(
    title='Windstärke & Windrichtung (Traunkirchen)',
    xaxis_title='Zeit',
    yaxis=dict(
        title='Windstärke (m/s)',
        range=[0, df["wind_speed"].max() * 1.2]
    ),
    yaxis2=dict(
        title='Windrichtung (°)',
        overlaying='y',
        side='right',
        range=[0, 360],
        showgrid=False,
        zeroline=False
    ),
    legend=dict(orientation='h', y=1.1),
    margin=dict(t=50, b=60)
)

st.plotly_chart(fig_wind, use_container_width=True)

# app.py
import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go
from datetime import date, timedelta
from plotly.subplots import make_subplots

# ======================
# Koordinaten
# ======================
coords = {
    "Traunkirchen": (47.993, 13.745),
    "Gmunden": (47.918, 13.799),
    "Bad_Ischl": (47.714, 13.632),
    "Ried": (48.198, 13.490)
}

# ======================
# Daten abrufen
# ======================
def fetch_openmeteo(start, end, lat, lon):
    today = date.today()
    if end <= today:
        url = "https://archive-api.open-meteo.com/v1/archive"
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

    # Zeitzone zuweisen (Fix für tz-naive vs. tz-aware Vergleich)
    df["time"] = pd.to_datetime(df["time"]).dt.tz_localize("Europe/Vienna")
    df.set_index("time", inplace=True)
    return df


# ======================
# Hilfsfunktionen für Windkarte
# ======================
def generate_traunsee_grid(lat_start=47.88, lat_end=47.93, lon_start=13.74, lon_end=13.81, step=0.01):
    lats = np.arange(lat_start, lat_end, step)
    lons = np.arange(lon_start, lon_end, step)
    grid = [(round(lat, 4), round(lon, 4)) for lat in lats for lon in lons]
    return grid

def wind_vector(speed, direction_deg):
    """Richtung ist meteorologisch (woher), daher -sin, -cos"""
    rad = np.radians(direction_deg)
    u = -speed * np.sin(rad)
    v = -speed * np.cos(rad)
    return u, v

def fetch_forecast_grid(grid_coords, forecast_hour=0):
    """Holt Winddaten von Open-Meteo für alle Punkte im Gitter"""
    all_data = []
    for lat, lon in grid_coords:
        try:
            url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "hourly": "wind_speed_10m,wind_direction_10m",
                "forecast_days": 2,
                "timezone": "Europe/Vienna"
            }
            r = requests.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            df = pd.DataFrame(data["hourly"])
            df["time"] = pd.to_datetime(df["time"]).dt.tz_localize("Europe/Vienna")

            selected_time = df["time"].min() + pd.Timedelta(hours=forecast_hour)
            df = df[df["time"] == selected_time]

            if not df.empty:
                u, v = wind_vector(df["wind_speed_10m"].iloc[0], df["wind_direction_10m"].iloc[0])
                all_data.append({
                    "lat": lat,
                    "lon": lon,
                    "u": u,
                    "v": v,
                    "speed": df["wind_speed_10m"].iloc[0],
                    "direction": df["wind_direction_10m"].iloc[0],
                    "time": selected_time
                })

        except Exception as e:
            print(f"Fehler bei Koordinate {lat},{lon}: {e}")

    return pd.DataFrame(all_data)

def plot_wind_map(df_wind):
    fig = go.Figure()

    for _, row in df_wind.iterrows():
        fig.add_trace(go.Scattergeo(
            lon=[row["lon"], row["lon"] + row["u"] * 0.02],
            lat=[row["lat"], row["lat"] + row["v"] * 0.02],
            mode="lines+markers",
            line=dict(width=2, color="orange"),
            marker=dict(size=4),
            name=f"{row['speed']:.1f} m/s"
        ))

    fig.update_layout(
        title=f"Windfeld über dem Traunsee ({df_wind['time'].iloc[0].strftime('%Y-%m-%d %H:%M')})",
        geo=dict(
            projection_type="mercator",
            center=dict(lat=47.9, lon=13.775),
            lonaxis_range=[13.73, 13.82],
            lataxis_range=[47.87, 47.94],
            showland=True,
            landcolor="lightgray",
            showcountries=False,
            showlakes=True,
            lakecolor="lightblue"
        ),
        margin=dict(t=30, b=30)
    )

    return fig


# ======================
# UI & Daten vorbereiten
# ======================
st.title("Traunsee Druckgradient")

start_date = st.date_input("Startdatum", date.today() - timedelta(days=5))
end_date = st.date_input("Enddatum", date.today() + timedelta(days=7))

if end_date < start_date:
    st.error("Enddatum muss nach Startdatum sein")
    st.stop()

# Daten laden
dfs = {}
for name, (lat, lon) in coords.items():
    dfs[name] = fetch_openmeteo(start_date, end_date, lat, lon)

# Berechnungen
df = dfs["Traunkirchen"].rename(columns={"pressure_msl": "P_T"})
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
df["wind_speed_kt"] = df["wind_speed"] * 1.94384

# ======================
# 1. ΔP & Clouds Plot
# ======================
fig = make_subplots(specs=[[{"secondary_y": True}]])

fig.add_trace(go.Scatter(x=df.index, y=df["delta_P_TG"],
                         name="ΔP Traunkirchen–Gmunden",
                         line=dict(color="grey")),
              secondary_y=False)

fig.add_trace(go.Scatter(x=df.index, y=df["delta_P_BR"],
                         name="ΔP Bad Ischl–Ried",
                         line=dict(color="deepskyblue")),
              secondary_y=False)

fig.add_trace(go.Scatter(x=df.index, y=df["cloud_total"],
                         name="clouds total [Okta]",
                         line=dict(color="black")),
              secondary_y=True)

# Horizontale Linie
fig.add_shape(
    type="line",
    x0=df.index.min(),
    x1=df.index.max(),
    y0=1.5,
    y1=1.5,
    line=dict(color="red", dash="dash"),
    yref="y",
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

# Vertikale Linie: aktueller Zeitpunkt
now = pd.Timestamp.now(tz="Europe/Vienna")
if df.index.min() <= now <= df.index.max():
    fig.add_shape(
        type="line",
        x0=now,
        x1=now,
        y0=0,
        y1=1,
        line=dict(color="oragnge", width=4, dash="dot"),
        xref="x",
        yref="paper"
    )

    fig.add_annotation(
        x=now,
        y=1,
        text="Jetzt",
        showarrow=False,
        yanchor="top",
        xanchor="left",
        xref="x",
        yref="paper",
        font=dict(color="yellow")
    )

fig.update_layout(
    title="Druckdifferenz und Gesamtbewölkung",
    xaxis_title="Datum",
    yaxis_title="ΔP [hPa]",
    legend=dict(orientation="h", y=-0.25),
    margin=dict(t=50, b=60)
)

fig.update_yaxes(title_text="clouds [Okta]", secondary_y=True)
st.plotly_chart(fig, use_container_width=True)

# ======================
# 2. Cloud Stack Plot
# ======================
fig_clouds = go.Figure()

fig_clouds.add_trace(go.Scatter(
    x=df.index, y=df["cloud_low"],
    mode='lines', name='Wolken unten',
    stackgroup='cloud', line=dict(width=0.5, color='lightblue')
))

fig_clouds.add_trace(go.Scatter(
    x=df.index, y=df["cloud_mid"],
    mode='lines', name='Wolken Mitte',
    stackgroup='cloud', line=dict(width=0.5, color='deepskyblue')
))

fig_clouds.add_trace(go.Scatter(
    x=df.index, y=df["cloud_high"],
    mode='lines', name='Wolken oben',
    stackgroup='cloud', line=dict(width=0.5, color='dodgerblue')
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

# ======================
# 3. Winddiagramm
# ======================
fig_wind = go.Figure()

fig_wind.add_trace(go.Scatter(
    x=df.index,
    y=df["wind_speed_kt"],
    mode='lines+markers',
    name='Windstärke (kt)',
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
        title='Windstärke (kt)',
        range=[0, df["wind_speed_kt"].max() * 1.2]
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

# ======================
# 4. AROME Prognose (Platzhalter)
# ======================
st.header("AROME Modellprognose (Demo)")

hours_forecast = st.slider("AROME Prognosezeitraum (h)", 6, 48, 24)

# Dummy-Daten
arome_times = pd.date_range(start=end_date, periods=hours_forecast, freq="H", tz="Europe/Vienna")
arome_temp = 15 + 3 * np.sin(np.linspace(0, 2 * np.pi, hours_forecast))
arome_wind = 10 + 2 * np.cos(np.linspace(0, 2 * np.pi, hours_forecast))

fig_arome = go.Figure()

fig_arome.add_trace(go.Scatter(
    x=arome_times,
    y=arome_temp,
    mode='lines+markers',
    name='Temperatur (°C)',
    line=dict(color='tomato')
))

fig_arome.add_trace(go.Scatter(
    x=arome_times,
    y=arome_wind,
    mode='lines+markers',
    name='Windgeschwindigkeit (m/s)',
    line=dict(color='steelblue')
))

fig_arome.update_layout(
    title='AROME Modellprognose (Demo)',
    xaxis_title='Zeit',
    yaxis_title='Wert',
    legend=dict(orientation='h', y=1.1),
    margin=dict(t=50, b=60)
)

st.plotly_chart(fig_arome, use_container_width=True)


# ======================
# 5. Windkarte über Traunsee
# ======================
st.header("Windkarte über den Traunsee (Open-Meteo Prognose)")

forecast_hour = st.slider("Prognosezeitpunkt (Stunden ab jetzt)", min_value=0, max_value=48, value=0, step=1)

with st.spinner("Lade Winddaten vom Open-Meteo API..."):
    grid_coords = generate_traunsee_grid()
    df_wind = fetch_forecast_grid(grid_coords, forecast_hour)

if df_wind.empty:
    st.warning("Keine Winddaten verfügbar.")
else:
    fig_map = plot_wind_map(df_wind)
    st.plotly_chart(fig_map, use_container_width=True)


import streamlit as st
import pandas as pd
import plotly.express as px
import requests

from datetime import datetime, timedelta

st.title("🌀 Druckdifferenz am Traunsee – Vergangenheit & Vorhersage")

# 📍 Koordinaten
orte = {
    "Bad Ischl": {"lat": 47.711, "lon": 13.619},
    "Schwanenstadt": {"lat": 48.051, "lon": 13.791}
}

# 🔗 API-URL bauen
def get_openmeteo_url(lat, lon):
    return (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&hourly=pressure_msl"
        f"&past_days=3&forecast_days=4"
        f"&timezone=Europe%2FBerlin"
    )

# 📡 Daten abrufen
def fetch_pressure_data(name, lat, lon):
    url = get_openmeteo_url(lat, lon)
    r = requests.get(url)
    data = r.json()
    df = pd.DataFrame({
        "time": data["hourly"]["time"],
        name: data["hourly"]["pressure_msl"]
    })
    df["time"] = pd.to_datetime(df["time"])
    return df

# 🔄 Daten laden
with st.spinner("Lade Wetterdaten..."):
    df_is = fetch_pressure_data("Bad Ischl", **orte["Bad Ischl"])
    df_sw = fetch_pressure_data("Schwanenstadt", **orte["Schwanenstadt"])

# 🔁 Zusammenführen
df = pd.merge(df_is, df_sw, on="time")
df["Druckdifferenz"] = df["Schwanenstadt"] - df["Bad Ischl"]

# 📈 Plot
fig = px.line(
    df,
    x="time",
    y="Druckdifferenz",
    title="Δp Schwanenstadt – Bad Ischl (hPa) – inkl. Vorhersage",
    labels={"time": "Zeit", "Druckdifferenz": "Druckdifferenz (hPa)"},
    markers=True
)
fig.add_hline(y=0, line_dash="dash", line_color="gray")

# 🔍 Aktueller Wert
aktueller_wert = df["Druckdifferenz"].iloc[-1]
st.subheader(f"Aktueller (letzter) Wert: {aktueller_wert:.2f} hPa")
if aktueller_wert < -1.5:
    st.success("→ Gute Thermik: Südwind wahrscheinlich.")
elif aktueller_wert > 1.0:
    st.warning("→ Möglicher Nordwind / Thermik schlecht.")
else:
    st.info("→ Geringe Druckdifferenz – wenig Wind.")

st.plotly_chart(fig, use_container_width=True)

# 🔎 Tabelle anzeigen
with st.expander("Stündliche Druckdaten anzeigen"):
    st.dataframe(df.tail(48))

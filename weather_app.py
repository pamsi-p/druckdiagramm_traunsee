import streamlit as st
from meteostat import Point, Daily, Hourly
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px

# Titel
st.title("Druckdifferenz Traunsee – Thermik-Vorhersage")

# Zeitbereich definieren
end = datetime.now()
start = end - timedelta(days=7)

# Orte definieren
bad_ischl = Point(47.711, 13.619, 470)         # ca. Bad Ischl
schwanenstadt = Point(48.051, 13.791, 380)     # ca. Schwanenstadt

# Daten laden
st.info("Lade Wetterdaten...")

data_is = Hourly(bad_ischl, start, end).fetch()
data_sw = Hourly(schwanenstadt, start, end).fetch()

# Nur Luftdruck behalten
data = pd.DataFrame()
data['Druck_Bad_Ischl'] = data_is['pres']
data['Druck_Schwanenstadt'] = data_sw['pres']
data['Druckdifferenz'] = data['Druck_Schwanenstadt'] - data['Druck_Bad_Ischl']
data = data.dropna()

# Plot erzeugen
fig = px.line(data, y="Druckdifferenz", title="Druckdifferenz Schwanenstadt – Bad Ischl (hPa)", markers=True)
fig.add_hline(y=0, line_dash="dash", line_color="gray")

# Farbige Warnung
aktueller_wert = data['Druckdifferenz'].iloc[-1]
st.subheader(f"Aktueller Wert: {aktueller_wert:.2f} hPa")
if aktueller_wert < -1.5:
    st.success("→ Wahrscheinlich Südwind / gute Thermik!")
elif aktueller_wert > 1.0:
    st.warning("→ Möglicher Nordwind / Thermik eher schwach.")
else:
    st.info("→ Geringe Druckdifferenz – möglicherweise wenig Wind.")

# Diagramm anzeigen
st.plotly_chart(fig, use_container_width=True)

# Daten anzeigen
with st.expander("Daten anzeigen"):
    st.dataframe(data)

import streamlit as st
from datetime import datetime, timedelta
from meteostat import Point, Hourly
import pandas as pd
import matplotlib.pyplot as plt
import os

# -------------------------------
# Function to fetch hourly weather data
# -------------------------------
def fetch_hourly_weather_data(latitude, longitude, start_date, end_date):
    """
    Fetch hourly weather data for a given location and date range.
    """
    start_date = datetime.combine(start_date, datetime.min.time())
    end_date = datetime.combine(end_date, datetime.min.time())

    location = Point(latitude, longitude)

    data = Hourly(location, start_date, end_date).fetch()

    if 'tsun' in data.columns:
        data['Cloud_Cover_Proxy'] = 1 - (data['tsun'] / 60)

    return data


# -------------------------------
# Function to process sensor data
# -------------------------------
def process_sensor_data(file):
    """
    Process sensor data from a .txt file and return a DataFrame.
    """
    data = pd.read_csv(file, sep=';', quotechar='"', encoding='ISO-8859-1', skiprows=7)

    date_column = data.columns[0]
    time_column = data.columns[1]
    ir20_column = data.columns[16]

    data['Datetime'] = pd.to_datetime(
        data[date_column].astype(str) + ' ' + data[time_column].astype(str),
        dayfirst=True
    )

    data[ir20_column] = pd.to_numeric(data[ir20_column], errors='coerce')
    data.dropna(subset=['Datetime', ir20_column], inplace=True)
    data['Date'] = data['Datetime'].dt.date

    downsampled_data = data.iloc[::10].copy()
    data['Rolling_IR20'] = data[ir20_column].rolling(window=30).mean()

    return data, downsampled_data, ir20_column


# -------------------------------
# Function to plot weather data
# -------------------------------
def plot_weather_data(weather_data):
    """
    Plot weather parameters for better interpretation.
    """
    st.subheader("Weather Parameter Plots")

    # Mark "today" with yellow background
    today = datetime.now().date()
    start_today = datetime.combine(today, datetime.min.time())
    end_today = datetime.combine(today, datetime.max.time())

    # Cloud Cover Proxy Plot
    if 'Cloud_Cover_Proxy' in weather_data.columns:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(weather_data.index, weather_data['Cloud_Cover_Proxy'], label="Cloud Cover Proxy", color="blue")
        ax.axvspan(start_today, end_today, color="yellow", alpha=0.2, label="Heute")
        ax.set_title("Hourly Cloud Cover Proxy")
        ax.set_xlabel("Time")
        ax.set_ylabel("Cloud Cover Proxy")
        ax.legend()
        ax.grid(True)
        st.pyplot(fig)

    # Average Temperature Plot
    if 'tavg' in weather_data.columns:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(weather_data.index, weather_data['tavg'], label="Temperature (°C)", color="orange")
        ax.axvspan(start_today, end_today, color="yellow", alpha=0.2, label="Heute")
        ax.set_title("Hourly Temperature")
        ax.set_xlabel("Time")
        ax.set_ylabel("Temperature (°C)")
        ax.legend()
        ax.grid(True)
        st.pyplot(fig)

    # Wind Speed Plot
    if 'wspd' in weather_data.columns:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(weather_data.index, weather_data['wspd'], label="Wind Speed (km/h)", color="green")
        ax.axvspan(start_today, end_today, color="yellow", alpha=0.2, label="Heute")
        ax.set_title("Hourly Wind Speed")
        ax.set_xlabel("Time")
        ax.set_ylabel("Wind Speed (km/h)")
        ax.legend()
        ax.grid(True)
        st.pyplot(fig)

    # Pressure Plot
    if 'pres' in weather_data.columns:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(weather_data.index, weather_data['pres'], label="Pressure (hPa)", color="purple")
        ax.axvspan(start_today, end_today, color="yellow", alpha=0.2, label="Heute")
        ax.set_title("Hourly Pressure")
        ax.set_xlabel("Time")
        ax.set_ylabel("Pressure (hPa)")
        ax.legend()
        ax.grid(True)
        st.pyplot(fig)

    # Sunshine Duration Plot
    if 'tsun' in weather_data.columns:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(weather_data.index, weather_data['tsun'], label="Sunshine Duration (minutes)", color="red")
        ax.axvspan(start_today, end_today, color="yellow", alpha=0.2, label="Heute")
        ax.set_title("Hourly Sunshine Duration")
        ax.set_xlabel("Time")
        ax.set_ylabel("Sunshine Duration (minutes)")
        ax.legend()
        ax.grid(True)
        st.pyplot(fig)


# -------------------------------
# Function to plot sensor data
# -------------------------------
def plot_sensor_data(data, downsampled_data, ir20_column, unique_dates):
    """
    Plot sensor data for all available dates.
    """
    today = datetime.now().date()
    start_today = datetime.combine(today, datetime.min.time())
    end_today = datetime.combine(today, datetime.max.time())

    # Full Plot with All Data
    st.subheader("Full Plot of Sensor Data")
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(data['Datetime'], data[ir20_column], marker='o', color='orange', alpha=0.5, label="IR20-E-korrigiert")
    ax.plot(data['Datetime'], data['Rolling_IR20'], color='blue', linewidth=2, label="30-Point Rolling Mean")
    ax.axvspan(start_today, end_today, color="yellow", alpha=0.2, label="Heute")
    ax.set_title("IR20-E-korrigiert Over Entire Time Period")
    ax.set_xlabel("Datetime")
    ax.set_ylabel("IR20-E-korrigiert")
    ax.legend()
    ax.grid(True)
    st.pyplot(fig)

    # Plot Each Day Separately
    st.subheader("Daily Plots of Sensor Data")
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    axes = axes.flatten()

    for i, day in enumerate(unique_dates[:4]):  # Limit to 4 days
        daily_data = data[data['Date'] == day]
        downsampled_daily_data = downsampled_data[downsampled_data['Date'] == day]

        axes[i].plot(downsampled_daily_data['Datetime'], downsampled_daily_data[ir20_column],
                     marker='o', color='orange', alpha=0.5, label="Downsampled IR20-E-korrigiert")
        axes[i].plot(daily_data['Datetime'], daily_data['Rolling_IR20'], color='blue', linewidth=2, label="30-Point Rolling Mean")

        axes[i].axvspan(start_today, end_today, color="yellow", alpha=0.2)

        axes[i].set_title(f"IR20-E-korrigiert on {day}")
        axes[i].set_xlabel("Time")
        axes[i].set_ylabel("IR20-E-korrigiert")
        axes[i].legend()
        axes[i].grid(True)

    plt.tight_layout()
    st.pyplot(fig)


# -------------------------------
# Streamlit Application
# -------------------------------
st.title("Weather and Sensor Data Analysis App")

st.sidebar.header("Input Parameters")
latitude = st.sidebar.number_input("Enter Latitude", value=50.9808, step=0.0001, format="%.4f")
longitude = st.sidebar.number_input("Enter Longitude", value=11.3290, step=0.0001, format="%.4f")

sensor_file = st.sidebar.file_uploader("Upload Sensor Data (.txt)", type=["txt"])
data_option = st.sidebar.radio("Select Data Option", ["Single Day", "Multiple Days"])

# Default: Heute + 2 Tage
default_start = datetime.now().date()
default_end = default_start + timedelta(days=2)

if data_option == "Single Day":
    selected_date = st.sidebar.date_input("Select Date", value=default_start)

    if st.sidebar.button("Fetch and Plot Data for Single Day"):
        with st.spinner("Fetching weather data..."):
            weather_data = fetch_hourly_weather_data(latitude, longitude, selected_date, selected_date + timedelta(days=1))
            st.success("Weather data fetched successfully!")
            plot_weather_data(weather_data)

        if sensor_file:
            with st.spinner("Processing sensor data..."):
                sensor_data, downsampled_sensor_data, ir20_column = process_sensor_data(sensor_file)
                unique_dates = sensor_data['Date'].unique()
                st.success("Sensor data processed successfully!")
                plot_sensor_data(sensor_data, downsampled_sensor_data, ir20_column, unique_dates)

elif data_option == "Multiple Days":
    start_date = st.sidebar.date_input("Start Date", value=default_start)
    end_date = st.sidebar.date_input("End Date", value=default_end)

    if st.sidebar.button("Fetch and Plot Data for Multiple Days"):
        with st.spinner("Fetching weather data..."):
            weather_data = fetch_hourly_weather_data(latitude, longitude, start_date, end_date)
            st.success("Weather data fetched successfully!")
            plot_weather_data(weather_data)

        if sensor_file:
            with st.spinner("Processing sensor data..."):
                sensor_data, downsampled_sensor_data, ir20_column = process_sensor_data(sensor_file)
                unique_dates = sensor_data['Date'].unique()
                st.success("Sensor data processed successfully!")
                plot_sensor_data(sensor_data, downsampled_sensor_data, ir20_column, unique_dates)

if st.sidebar.button("Show Parameter Definitions"):
    st.subheader("Parameter Definitions")
    st.markdown("""
    - **Cloud Cover Proxy**: A calculated proxy for cloud cover, where 1 indicates full cloud cover and 0 indicates no cloud cover. It is derived from sunshine duration data.
    - **Temperature (°C)**: The average air temperature at the location.
    - **Wind Speed (km/h)**: The average speed of wind over the time period.
    - **Pressure (hPa)**: Atmospheric pressure measured at sea level.
    - **Sunshine Duration (minutes)**: The total duration of sunshine received during the hour.
    - **IR20-E-korrigiert**: A measurement of longwave radiation recorded by the sensor.
    """)

st.sidebar.markdown("Developed by Midhun Kanadan - Weather and Sensor Data Analysis")

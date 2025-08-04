import streamlit as st
from datetime import datetime, timedelta
from meteostat import Point, Hourly
import pandas as pd
import matplotlib.pyplot as plt
import os


# Function to fetch hourly weather data
def fetch_hourly_weather_data(latitude, longitude, start_date, end_date):
    """
    Fetch hourly weather data for a given location and date range.
    """
    # Ensure dates are in datetime format
    start_date = datetime.combine(start_date, datetime.min.time())
    end_date = datetime.combine(end_date, datetime.min.time())
    
    # Define the location
    location = Point(latitude, longitude)
    
    # Fetch hourly weather data
    data = Hourly(location, start_date, end_date).fetch()
    
    # Add cloud cover proxy if possible
    if 'tsun' in data.columns:
        data['Cloud_Cover_Proxy'] = 1 - (data['tsun'] / 60)  # Using minutes as a proxy
    
    return data


# Function to process sensor data from a .txt file
def process_sensor_data(file):
    """
    Process sensor data from a .txt file and return a DataFrame.
    """
    # Load the .txt file
    data = pd.read_csv(file, sep=';', quotechar='"', encoding='ISO-8859-1', skiprows=7)

    # Define columns based on position for Date, Time, and IR20-E-korrigiert
    date_column = data.columns[0]  # First column for date
    time_column = data.columns[1]  # Second column for time
    ir20_column = data.columns[16]  # 17th column (Q) for 'IR20-E-korrigiert'

    # Combine 'Date' and 'Time' into a single datetime column
    data['Datetime'] = pd.to_datetime(data[date_column].astype(str) + ' ' + data[time_column].astype(str), dayfirst=True)

    # Convert 'IR20-E-korrigiert' to numeric format, handling non-numeric values by setting them as NaN
    data[ir20_column] = pd.to_numeric(data[ir20_column], errors='coerce')

    # Drop rows with NaN values in 'Datetime' or 'IR20-E-korrigiert'
    data.dropna(subset=['Datetime', ir20_column], inplace=True)

    # Add a 'Date' column for each day based on the 'Datetime' column
    data['Date'] = data['Datetime'].dt.date

    # Apply downsampling (e.g., every 10th data point) for a clearer view
    downsampled_data = data.iloc[::10].copy()

    # Apply a rolling mean to smooth the data
    data['Rolling_IR20'] = data[ir20_column].rolling(window=30).mean()

    return data, downsampled_data, ir20_column


# Function to plot weather data
def plot_weather_data(weather_data):
    """
    Plot weather parameters for better interpretation.
    """
    st.subheader("Weather Parameter Plots")

    # Cloud Cover Proxy Plot
    if 'Cloud_Cover_Proxy' in weather_data.columns:
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(weather_data.index, weather_data['Cloud_Cover_Proxy'], label="Cloud Cover Proxy", color="blue")
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
        ax.set_title("Hourly Sunshine Duration")
        ax.set_xlabel("Time")
        ax.set_ylabel("Sunshine Duration (minutes)")
        ax.legend()
        ax.grid(True)
        st.pyplot(fig)


# Function to plot sensor data
def plot_sensor_data(data, downsampled_data, ir20_column, unique_dates):
    """
    Plot sensor data for all available dates.
    """
    # Full Plot with All Data
    st.subheader("Full Plot of Sensor Data")
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(data['Datetime'], data[ir20_column], marker='o', color='orange', alpha=0.5, label="IR20-E-korrigiert")
    ax.plot(data['Datetime'], data['Rolling_IR20'], color='blue', linewidth=2, label="30-Point Rolling Mean")
    ax.set_title("IR20-E-korrigiert Over Entire Time Period")
    ax.set_xlabel("Datetime")
    ax.set_ylabel("IR20-E-korrigiert")
    ax.legend()
    ax.grid(True)
    st.pyplot(fig)

    # Plot Each Day Separately
    st.subheader("Daily Plots of Sensor Data")
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    axes = axes.flatten()  # Flatten the grid for easy indexing

    for i, day in enumerate(unique_dates[:4]):  # Limit to 4 days for 2x2 grid
        daily_data = data[data['Date'] == day]
        downsampled_daily_data = downsampled_data[downsampled_data['Date'] == day]

        # Plot downsampled data
        axes[i].plot(downsampled_daily_data['Datetime'], downsampled_daily_data[ir20_column], 
                     marker='o', color='orange', alpha=0.5, label="Downsampled IR20-E-korrigiert")

        # Plot rolling mean
        axes[i].plot(daily_data['Datetime'], daily_data['Rolling_IR20'], color='blue', linewidth=2, label="30-Point Rolling Mean")

        # Set labels and title for each subplot
        axes[i].set_title(f"IR20-E-korrigiert on {day}")
        axes[i].set_xlabel("Time")
        axes[i].set_ylabel("IR20-E-korrigiert")
        axes[i].legend()
        axes[i].grid(True)

    # Adjust layout for better display
    plt.tight_layout()
    st.pyplot(fig)


# Streamlit Application
st.title("Weather and Sensor Data Analysis App")

# Sidebar for input options
st.sidebar.header("Input Parameters")
latitude = st.sidebar.number_input("Enter Latitude", value=50.9808, step=0.0001, format="%.4f")
longitude = st.sidebar.number_input("Enter Longitude", value=11.3290, step=0.0001, format="%.4f")

# File uploader for sensor data
sensor_file = st.sidebar.file_uploader("Upload Sensor Data (.txt)", type=["txt"])

# User can select single day or multiple days
data_option = st.sidebar.radio("Select Data Option", ["Single Day", "Multiple Days"])

if data_option == "Single Day":
    # Single day input
    selected_date = st.sidebar.date_input("Select Date", value=datetime(2024, 10, 31))

    if st.sidebar.button("Fetch and Plot Data for Single Day"):
        with st.spinner("Fetching weather data..."):
            # Fetch hourly weather data for a single day
            weather_data = fetch_hourly_weather_data(latitude, longitude, selected_date, selected_date + timedelta(days=1))
            st.success("Weather data fetched successfully!")

            # Plot weather data
            plot_weather_data(weather_data)

        # Process and plot sensor data if a file is uploaded
        if sensor_file:
            with st.spinner("Processing sensor data..."):
                sensor_data, downsampled_sensor_data, ir20_column = process_sensor_data(sensor_file)
                unique_dates = sensor_data['Date'].unique()
                st.success("Sensor data processed successfully!")

                # Plot sensor data
                plot_sensor_data(sensor_data, downsampled_sensor_data, ir20_column, unique_dates)

elif data_option == "Multiple Days":
    # Date range input
    start_date = st.sidebar.date_input("Start Date", value=datetime(2024, 10, 31))
    end_date = st.sidebar.date_input("End Date", value=datetime(2024, 11, 3))

    if st.sidebar.button("Fetch and Plot Data for Multiple Days"):
        with st.spinner("Fetching weather data..."):
            # Fetch hourly weather data for multiple days
            weather_data = fetch_hourly_weather_data(latitude, longitude, start_date, end_date)
            st.success("Weather data fetched successfully!")

            # Plot weather data
            plot_weather_data(weather_data)

        # Process and plot sensor data if a file is uploaded
        if sensor_file:
            with st.spinner("Processing sensor data..."):
                sensor_data, downsampled_sensor_data, ir20_column = process_sensor_data(sensor_file)
                unique_dates = sensor_data['Date'].unique()
                st.success("Sensor data processed successfully!")

                # Plot sensor data
                plot_sensor_data(sensor_data, downsampled_sensor_data, ir20_column, unique_dates)

# Sidebar button to show parameter definitions
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

# Display footer message
st.sidebar.markdown("Developed by Midhun Kanadan - Weather and Sensor Data Analysis")

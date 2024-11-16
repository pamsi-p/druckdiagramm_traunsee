
# Weather-and-Sensor-Data-Analysis-App


This repository contains a Streamlit application for analyzing weather data and sensor measurements. The app provides interactive visualizations and allows users to:

- Fetch weather data for a specified location and time range using the Meteostat API.
- Upload sensor data in `.txt` format, process it, and visualize the longwave radiation (`IR20-E-korrigiert`) measurements.
- Compare weather parameters like temperature, wind speed, pressure, and cloud cover with sensor data for meaningful insights.

## Features
- **Single Day Analysis**: Visualize weather and sensor data for a specific day.
- **Multiple Days Analysis**: Fetch and compare data over a date range.
- **Interactive Visualizations**: Separate plots for weather parameters and sensor measurements.
- **Parameter Definitions**: Built-in explanation of weather and sensor metrics.
- **Data Download**: Save weather and sensor data as `.csv` files.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Midhun-Kanadan/Weather-and-Sensor-Data-Analysis-App.git
   ```
2. Navigate to the repository directory:
   ```bash
   cd weather_sensor_analysis_app
   ```
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the Streamlit app locally:
```bash
streamlit run weather_sensor_app.py
```

## File Structure

- `weather_sensor_app.py`: Main Streamlit application script.
- `requirements.txt`: Python dependencies for the app.

## Dependencies

- `streamlit`
- `meteostat`
- `matplotlib`
- `pandas`

## Example

The app fetches weather data (e.g., temperature, wind speed, pressure, cloud cover proxy) and processes sensor data from uploaded `.txt` files, displaying both in interactive visualizations.

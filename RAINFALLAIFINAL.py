import logging
import sqlite3
import time
import threading
from datetime import datetime, timedelta
from gpiozero import Button
from signal import pause, signal, SIGINT
import sys
import numpy as np
import pandas as pd
from keras.models import load_model
import joblib

# Logging setup
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Constants
TIP_PER_MM = 0.3  # Rainfall per bucket tip in mm
DEBOUNCE_TIME = 1.0  # Debounce time in seconds
rainfall_data = []  # To store recent rainfall data for calculation
rainfall_timestamps = []  # To store timestamps of each tip for cumulative calculation
cumulative_15min_rainfall = []  # List to store cumulative 15-minute rainfall amounts
last_tip_time = 0  # Timestamp of the last tip event
real_time_rainfall = 0.0  # Shared variable to store real-time rainfall amount
lock = threading.Lock()  # Lock for synchronizing access to shared variables

# Database setup
conn = sqlite3.connect('rainfall_data2.db', check_same_thread=False)
cursor = conn.cursor()

# Create tables if they don't exist
cursor.execute("""CREATE TABLE IF NOT EXISTS rainfall_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    rainfall_15min REAL,
                    rainfall_1hour REAL,
                    rainfall_classification_1hour TEXT,
                    rainfall_classification_15min TEXT,
                    flood_risk TEXT,
                    action_needed TEXT
                )""")

cursor.execute("""CREATE TABLE IF NOT EXISTS real_time_rainfall (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    rainfall_mm REAL
                )""")

cursor.execute("""CREATE TABLE IF NOT EXISTS rainfall_predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    predicted_1hour REAL,
                    rainfall_classification TEXT,
                    flood_risk TEXT,
                    action_needed TEXT
                )""")
conn.commit()

# Define the file path for the new model
model_path = '/home/pi/Documents/models/model_15minfor1hr(mostrecent23).h5'

# Load the Keras model
try:
    model = load_model(model_path)
except FileNotFoundError as e:
    logging.error(f"Error loading model: {e}")
    sys.exit(1)

# Load the scalers
scaler_features = joblib.load('/home/pi/Documents/scaler_features.pkl')
scaler_labels = joblib.load('/home/pi/Documents/scaler_labels.pkl')

# Function to classify rainfall and flood risk
def classify_rainfall_and_flood(rainfall_mm):
    if rainfall_mm == 0:
        return "No Rain", "No immediate action necessary.", "No action needed"
    elif 0.01 <= rainfall_mm < 2.5:
        return "Light Rain", "No immediate action necessary.", "No action needed"
    elif 2.5 <= rainfall_mm < 7.5:
        return "Moderate Rain", "No flood warning, but stay informed of changing conditions.", "Stay informed"
    elif 7.5 <= rainfall_mm < 15:
        return "Yellow Rainfall Advisory", "Monitor the weather and be warned of potential flooding in low-lying areas.", "Monitor weather"
    elif 15 <= rainfall_mm < 30:
        return "Orange Rainfall Warning", "Be cautious about the possibility of flooding.", "Be cautious"
    elif rainfall_mm >= 30:
        return "Red Rainfall Warning", "Emergency: Heavy rains detected; possibility of severe flooding.", "Emergency actions needed"
    else:
        return "Unknown", "No classification available", "No action available"

# Function to log rainfall data
def log_rainfall(rainfall_15min, rainfall_1hour, rainfall_classification_1hr=None, rainfall_classification_15min=None, flood_risk=None, action_needed=None):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rainfall_15min = 0.0000 if rainfall_15min is None else rainfall_15min
    rainfall_1hour = 0.0000 if rainfall_1hour is None else rainfall_1hour
    logging.debug(f"Logging rainfall at {timestamp}: 15min={rainfall_15min}, 1hour={rainfall_1hour}")
    cursor.execute("INSERT INTO rainfall_log (timestamp, rainfall_15min, rainfall_1hour, rainfall_classification_1hour, rainfall_classification_15min, flood_risk, action_needed) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                   (timestamp, f"{rainfall_15min:.4f}", f"{rainfall_1hour:.4f}", rainfall_classification_1hr, rainfall_classification_15min, flood_risk, action_needed))
    conn.commit()
    logging.info(f"Rainfall logged: 15min: {rainfall_15min:.4f} mm, 1hr: {rainfall_1hour:.4f} mm, Classification: {rainfall_classification_15min}, Flood Risk: {flood_risk}, Action Needed: {action_needed} at {timestamp}")

# Function to log real-time rainfall data
def log_real_time_rainfall(rainfall_mm):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT INTO real_time_rainfall (timestamp, rainfall_mm) VALUES (?, ?)", 
                   (timestamp, rainfall_mm))
    conn.commit()
    logging.info(f"Real-time rainfall logged: {rainfall_mm} mm at {timestamp}")

# Function to log prediction data
def log_prediction(predicted_1hour, rainfall_classification, flood_risk, action_needed):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT INTO rainfall_predictions (timestamp, predicted_1hour, rainfall_classification, flood_risk, action_needed) VALUES (?, ?, ?, ?, ?)", 
                   (timestamp, f"{predicted_1hour:.4f}", rainfall_classification, flood_risk, action_needed))
    conn.commit()
    logging.info(f"Prediction logged: 1hr: {predicted_1hour:.4f} mm, Classification: {rainfall_classification}, Flood Risk: {flood_risk}, Action Needed: {action_needed} at {timestamp}")

# Function to calculate cumulative rainfall
def calculate_cumulative_rainfall(interval_minutes):
    now = datetime.now()
    interval = timedelta(minutes=interval_minutes)
    cumulative_rainfall = sum([rain for rain, ts in zip(rainfall_data, rainfall_timestamps) if now - ts <= interval])
    logging.debug(f"Cumulative rainfall for past {interval_minutes} minutes: {cumulative_rainfall}")
    return round(cumulative_rainfall, 4)

# Function to handle tipping bucket events
def bucket_tipped():
    global last_tip_time, real_time_rainfall
    current_time = time.time()
    
    # Check if the tip event is within the debounce time
    if current_time - last_tip_time < DEBOUNCE_TIME:
        return

    last_tip_time = current_time
    rainfall_mm = round(TIP_PER_MM, 4)
    logging.info(f"Bucket tipped! Rainfall: {rainfall_mm:.4f} mm")

    with lock:
        rainfall_data.append(rainfall_mm)
        rainfall_timestamps.append(datetime.now())
        real_time_rainfall += rainfall_mm  # Update the shared variable with the rainfall amount
        logging.debug(f"Updated rainfall_data: {rainfall_data}")
        logging.debug(f"Updated rainfall_timestamps: {rainfall_timestamps}")

        # Remove data points older than 1 hour
        cutoff_time = datetime.now() - timedelta(hours=1)
        while rainfall_timestamps and rainfall_timestamps[0] < cutoff_time:
            rainfall_data.pop(0)
            rainfall_timestamps.pop(0)

# Function to log cumulative rainfall at appropriate intervals and make predictions
def rainfall_logging():
    # Timestamps for the last log entries
    last_15min_log = datetime.now()
    last_1hour_log = datetime.now()

    while True:
        time.sleep(60)  # Check every minute
        now = datetime.now()

        with lock:
            # Determine if we need to log
            log_15min = now - last_15min_log >= timedelta(minutes=15)
            log_1hour = now - last_1hour_log >= timedelta(hours=1)

            if log_15min or log_1hour:
                # Calculate rainfall for each interval
                rainfall_15min = calculate_cumulative_rainfall(15)
                rainfall_1hour = calculate_cumulative_rainfall(60)

                if log_15min:
                    logging.info(f"Logging 15-minute rainfall at {now}: {rainfall_15min} mm")
                    cumulative_15min_rainfall.append(rainfall_15min)  # Store the 15-minute cumulative rainfall
                    if len(cumulative_15min_rainfall) > 4:
                        cumulative_15min_rainfall.pop(0)  # Keep only the last 4 data points

                if log_1hour:
                    logging.info(f"Logging 1-hour rainfall at {now}: {rainfall_1hour} mm")

                # Prepare input data for the model
                if len(cumulative_15min_rainfall) == 4:  # Ensure we have enough data points for lagged features
                    logging.debug("Preparing input data for the model")

                    # Prepare lagged features using the last four 15-minute cumulative rainfall amounts
                    lag1 = cumulative_15min_rainfall[-1]
                    lag2 = cumulative_15min_rainfall[-2]
                    lag3 = cumulative_15min_rainfall[-3]
                    current = cumulative_15min_rainfall[-4]

                    # Debug logging for input data
                    logging.debug(f"Current: {current}, Lag1: {lag1}, Lag2: {lag2}, Lag3: {lag3}")

                    # Define the feature names
                    feature_names = ['Rain - mm', 'hour', 'Rain - mm lag1', 'Rain - mm lag2', 'Rain - mm lag3']

                    # Prepare input data as a DataFrame to include feature names
                    input_data = pd.DataFrame([[
                        current,
                        now.hour,
                        lag1,
                        lag2,
                        lag3
                    ]], columns=feature_names)

                    # Scale the input data
                    input_data_scaled = scaler_features.transform(input_data)
                    logging.debug(f"Scaled input_data: {input_data_scaled}")

                    # Reshape back to the expected shape for the model
                    input_data_scaled = input_data_scaled.reshape(1, 1, 5)  # 1 time step, 5 features

                    # Duplicate the 1 time step to create a sequence of 4 time steps
                    input_data_scaled = np.repeat(input_data_scaled, 4, axis=1)
                    logging.debug(f"Final input data shape: {input_data_scaled.shape}")

                    # Make predictions using the Keras model
                    predicted_1hour = round(model.predict(input_data_scaled)[0][0], 4)
                    logging.debug(f"Predicted 1-hour rainfall: {predicted_1hour}")

                    # Ensure no negative values in predictions
                    predicted_1hour = max(predicted_1hour, 0.00)

                    # Classify the predicted 1-hour rainfall
                    rainfall_classification, flood_risk, action_needed = classify_rainfall_and_flood(predicted_1hour)

                    # Log prediction
                    log_prediction(predicted_1hour, rainfall_classification, flood_risk, action_needed)
                else:
                    logging.debug(f"Not enough data points for prediction: {len(cumulative_15min_rainfall)} data points available")

                # Classify rainfall, flood risk, and action needed based on 1-hour data
                rainfall_classification_15min = "No read"
                if log_15min:
                    rainfall_classification_15min, flood_risk, action_needed = classify_rainfall_and_flood(rainfall_15min)

                rainfall_classification_1hour = rainfall_classification_15min
                if log_1hour:
                    rainfall_classification_1hour, flood_risk, action_needed = classify_rainfall_and_flood(rainfall_1hour)
                

                # Log cumulative rainfall and predictions at appropriate intervals
                log_rainfall(
                    rainfall_15min if log_15min else None,
                    rainfall_1hour if log_1hour else None,
                    rainfall_classification_1hour if log_1hour else None,
                    rainfall_classification_15min if log_15min else None,
                    flood_risk if log_1hour else None,
                    action_needed if log_1hour else None
                )
                if log_15min:
                    last_15min_log = now
                if log_1hour:
                    last_1hour_log = now

# Function to log real-time rainfall data every second
def continuous_real_time_logging():
    global real_time_rainfall
    while True:
        with lock:
            if real_time_rainfall > 0.0:
                log_real_time_rainfall(real_time_rainfall)  # Log the actual rainfall amount
                real_time_rainfall = 0.0  # Reset the rainfall amount for the next second
            else:
                log_real_time_rainfall(0.0)  # Log 0.0 mm if no tip detected
        time.sleep(1)  # Log every 1 second (for actual deployment)

# Configure the tipping bucket rain gauge
rain_sensor = Button(16)
rain_sensor.when_activated = bucket_tipped

# Start the continuous real-time logging thread
continuous_real_time_thread = threading.Thread(target=continuous_real_time_logging, daemon=True)
continuous_real_time_thread.start()

# Start the rainfall logging thread
rainfall_thread = threading.Thread(target=rainfall_logging, daemon=True)
rainfall_thread.start()

def cleanup(signal, frame):
    logging.info("Cleaning up GPIO and exiting...")
    cursor.close()
    conn.close()
    sys.exit(0)

# Handle SIGINT (Ctrl+C) for cleanup
signal(SIGINT, cleanup)

# Main program loop
logging.info("Rainfall monitoring started.")
try:
    pause()  # Block the main thread and keep the script running
except KeyboardInterrupt:
    cleanup(None, None)
import subprocess
import time
import csv  # Import the csv module
from datetime import datetime  # Import datetime for timestamps
import re # Import regular expression module

T_sleep = 1.0  # Sleep time in seconds (variable)
ENABLE_LOGGING = True  # Hardcoded variable to enable/disable CSV logging (True to enable, False to disable)
ENABLE_DELTA_COLUMNS = False  # Flag to enable/disable delta columns in output (True to enable, False to disable)

def get_battery_value(property_name):
    """
    Executes adb shell command to read battery property from sysfs.

    Args:
        property_name: The name of the battery property file in sysfs
                       (e.g., 'current_now', 'voltage_now', 'capacity').

    Returns:
        str: The value read from the property file, or None if there's an error.
    """
    try:
        process = subprocess.run(
            ["./adb", "shell", f"cat /sys/class/power_supply/battery/{property_name}"], # Using ./adb
            capture_output=True,
            text=True,
            check=True  # Raise an exception for non-zero exit codes
        )
        output = process.stdout.strip()
        return output
    except subprocess.CalledProcessError as e:
        print(f"Error reading {property_name}: ADB command failed with error code {e.returncode}")
        print(f"Stderr: {e.stderr}")
        return None
    except FileNotFoundError:
        print("Error: ./adb command not found. Make sure ADB is in the current directory and executable, or in your PATH.") # Updated error message for ./adb
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def get_battery_temperature():
    """
    Reads battery temperature using `dumpsys battery | grep temp`.
    Temperature is typically in tenths of a degree Celsius.
    """
    try:
        process = subprocess.run(
            ["./adb", "shell", "dumpsys battery | grep temp"],
            capture_output=True,
            text=True,
            check=True
        )
        output = process.stdout.strip()
        # Example output:   temperature: 280
        parts = output.split(':') # Split by colon
        if len(parts) > 1:
            temp_str = parts[1].strip() # Take the part after the colon and remove whitespace
            try:
                temp_tenths_celsius = int(temp_str)
                temp_celsius = temp_tenths_celsius / 10.0 # Convert to Celsius
                return temp_celsius
            except ValueError:
                print(f"Warning: Could not convert temperature value to float: {temp_str}")
                return None
        else:
            print(f"Warning: Unexpected output format for temperature: {output}")
            return None

    except subprocess.CalledProcessError as e:
        print(f"Error reading battery temperature: ADB command failed with error code {e.returncode}")
        print(f"Stderr: {e.stderr}")
        return None
    except FileNotFoundError:
        print("Error: ./adb command not found for battery temperature. Make sure ADB is in the current directory and executable, or in your PATH.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while reading battery temperature: {e}")
        return None

def get_device_model():
    """
    Retrieves the device model using `adb shell getprop ro.product.model`.
    """
    try:
        process = subprocess.run(
            ["./adb", "shell", "getprop ro.product.model"],
            capture_output=True,
            text=True,
            check=True
        )
        model = process.stdout.strip()
        return model
    except subprocess.CalledProcessError as e:
        print(f"Error getting device model: ADB command failed with error code {e.returncode}")
        print(f"Stderr: {e.stderr}")
        return "UNKNOWN_MODEL"
    except FileNotFoundError:
        print("Error: ./adb command not found for getting device model.")
        return "UNKNOWN_MODEL"
    except Exception as e:
        print(f"An unexpected error occurred while getting device model: {e}")
        return "UNKNOWN_MODEL"

def get_device_serial():
    """
    Retrieves the device serial number using `adb get-serialno`.
    """
    try:
        process = subprocess.run(
            ["./adb", "get-serialno"],
            capture_output=True,
            text=True,
            check=True
        )
        serial = process.stdout.strip()
        return serial
    except subprocess.CalledProcessError as e:
        print(f"Error getting device serial: ADB command failed with error code {e.returncode}")
        print(f"Stderr: {e.stderr}")
        return "UNKNOWN_SERIAL"
    except FileNotFoundError:
        print("Error: ./adb command not found for getting device serial.")
        return "UNKNOWN_SERIAL"
    except Exception as e:
        print(f"An unexpected error occurred while getting device serial: {e}")
        return "UNKNOWN_SERIAL"

def sanitize_filename(filename):
    """
    Sanitizes a filename by replacing invalid characters with underscores.
    """
    return re.sub(r'[^\w\-_\.]', '_', filename) # Keep alphanumeric, underscore, hyphen, dot


if __name__ == "__main__":
    print("-" * 160) # Increased separator width
    print("Real-time Battery Monitoring Script with Temperature (Fixed-Width Output)") # Updated title
    print("-" * 160)
    print(f"Polling Interval: {T_sleep:.2f} seconds")
    print(f"Logging to CSV:   {'Enabled' if ENABLE_LOGGING else 'Disabled'}")
    print(f"Delta Columns:    {'Enabled' if ENABLE_DELTA_COLUMNS else 'Disabled'}") # Added delta columns status
    print("-" * 160)
    print("Press Ctrl+C to stop")
    print("-" * 160)

    header_row = f"{'Timestamp':<23} | {'Current (mA)':>10} | "
    if ENABLE_DELTA_COLUMNS:
        header_row += f"{'ΔCurrent (mA)':>10} | "
    header_row += f"{'Avg Current (mA)':>10} | "
    if ENABLE_DELTA_COLUMNS:
        header_row += f"{'ΔAvg Current (mA)':>12} | "
    header_row += f"{'Voltage (mV)':>10} | "
    if ENABLE_DELTA_COLUMNS:
        header_row += f"{'ΔVoltage (mV)':>10} | "
    header_row += f"{'Power (W)':>10} | "
    if ENABLE_DELTA_COLUMNS:
        header_row += f"{'ΔPower (W)':>10} | "
    header_row += f"{'Capacity (%)':>8} | {'Temp (°C)':>8}"
    print(header_row)
    print("-" * 160)


    previous_current_ua = None
    previous_current_avg_ua = None # Track previous average current
    previous_voltage_uv = None
    previous_power_w = None # Track previous power (calculated)
    previous_temp_celsius = None # Track previous temperature


    csv_filename = "battery_data_with_temp.csv"  # Default CSV filename - fallback
    csv_file = None # Initialize csv_file outside the if block
    csv_writer = None # Initialize csv_writer outside the if block

    if ENABLE_LOGGING:
        device_model = get_device_model()
        device_serial = get_device_serial()
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")

        sanitized_model = sanitize_filename(device_model)
        sanitized_serial = sanitize_filename(device_serial)
        csv_filename = f"battery_log_{sanitized_model}_{sanitized_serial}_{timestamp_str}.csv"


        csv_file = open(csv_filename, 'w', newline='') # Open CSV file in write mode if logging is enabled
        csv_writer = csv.writer(csv_file) # Create CSV writer object
        # Write header row to CSV - NO DELTA COLUMNS IN CSV
        csv_writer.writerow(["Timestamp", "Current (mA)", "Avg Current (mA)", "Voltage (mV)", "Power (W)", "Capacity (%)", "Temperature (°C)"])
        csv_file.flush() # Forza lo scaricamento del buffer dopo aver scritto l'header**
        print(f"Logging data to: {csv_filename}") # Inform user about the log filename


    while True:
        current_now_str = get_battery_value("current_now")
        current_avg_str = get_battery_value("current_avg") # Get average current
        voltage_now_str = get_battery_value("voltage_now")
        capacity_str = get_battery_value("capacity") # Get capacity value
        temp_celsius = get_battery_temperature() # Get battery temperature using dumpsys

        if current_now_str is not None and current_avg_str is not None and voltage_now_str is not None and capacity_str is not None and temp_celsius is not None: # Check if temperature is also not None
            try:
                current_ua = int(current_now_str)  # Current in microamps (instantaneous)
                current_avg_ua = int(current_avg_str) # Average current in microamps
                voltage_uv = int(voltage_now_str)  # Voltage in microvolts (instantaneous)
                capacity_percent = int(capacity_str) # Capacity as percentage


                current_ma = current_ua / 1000.0  # Convert instantaneous to milliamps for easier reading
                current_avg_ma = current_avg_ua / 1000.0 # Convert average to milliamps
                voltage_mv = voltage_uv / 1000.0  # Convert to millivolts for easier reading
                power_w = voltage_mv/1000 * abs(current_ma/1000) # Power in Watts


                current_delta_ma = None
                current_avg_delta_ma = None # Delta for average current
                voltage_delta_mv = None
                power_delta_mw = None # Delta for power
                temp_delta_celsius = None # Delta for temperature


                if previous_current_ua is not None and previous_current_avg_ua is not None and previous_voltage_uv is not None and previous_power_w is not None and previous_temp_celsius is not None: # Added check for previous_temp_celsius
                    current_delta_ma = (current_ua - previous_current_ua) / 1000.0
                    current_avg_delta_ma = (current_avg_ua - previous_current_avg_ua) / 1000.0 # Calculate delta for average current
                    voltage_delta_mv = (voltage_uv - previous_voltage_uv) / 1000.0
                    power_delta_mw = power_w - previous_power_w # Calculate delta for power
                    temp_delta_celsius = temp_celsius - previous_temp_celsius # Calculate delta for temperature


                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f") # Get timestamp with milliseconds

                print_output = f"{timestamp:<23} | " # Timestamp (left aligned, width 23)
                print_output += f"{current_ma:>10.2f} | " # Current Now (right aligned, width 10, 2 decimal places)
                if ENABLE_DELTA_COLUMNS and current_delta_ma is not None:
                    print_output += f"{current_delta_ma:>+10.2f} | " # Current Now Delta (right aligned, width 10, with sign, 2 decimal places)
                elif ENABLE_DELTA_COLUMNS:
                    print_output += f"{'Initial':>10} | " # Current Now Delta - Initial Value (right aligned, width 10)
                print_output += f"{current_avg_ma:>10.2f} | " # Current Avg (right aligned, width 10, 2 decimal places)
                if ENABLE_DELTA_COLUMNS and current_avg_delta_ma is not None:
                    print_output += f"{current_avg_delta_ma:>+12.2f} | " # Current Avg Delta (right aligned, width 12, with sign, 2 decimal places)
                elif ENABLE_DELTA_COLUMNS:
                    print_output += f"{'Initial':>12} | " # Current Avg Delta - Initial Value (right aligned, width 12)
                print_output += f"{voltage_mv:>10.2f} | " # Voltage Now (right aligned, width 10, 2 decimal places)
                if ENABLE_DELTA_COLUMNS and voltage_delta_mv is not None:
                    print_output += f"{voltage_delta_mv:>+10.2f} | " # Voltage Now Delta (right aligned, width 10, with sign, 2 decimal places)
                elif ENABLE_DELTA_COLUMNS:
                    print_output += f"{'Initial':>10} | " # Voltage Now Delta - Initial Value (right aligned, width 10)
                print_output += f"{power_w:>10.2f} | " # Power Now (right aligned, width 10, 2 decimal places)
                if ENABLE_DELTA_COLUMNS and power_delta_mw is not None:
                    print_output += f"{power_delta_mw:>+10.2f} | " # Power Now Delta (right aligned, width 10, with sign, 2 decimal places)
                elif ENABLE_DELTA_COLUMNS:
                    print_output += f"{'Initial':>10} | " # Power Now Delta - Initial Value (right aligned, width 10)
                print_output += f"{capacity_percent:>8}% | " # Capacity (right aligned, width 8)
                print_output += f"{temp_celsius:>8.1f}°C" # Temperature (right aligned, width 8, 1 decimal place)
                print(print_output)


                if ENABLE_LOGGING and csv_writer is not None:
                    # CSV WRITE - NO DELTA COLUMNS
                    csv_writer.writerow([timestamp, f"{current_ma:.2f}", f"{current_avg_ma:.2f}", f"{voltage_mv:.2f}", f"{power_w:.2f}", capacity_percent, f"{temp_celsius:.1f}"])
                    csv_file.flush() # Forza lo scaricamento del buffer dopo ogni riga di dati**


                previous_current_ua = current_ua  # Update previous current for next iteration
                previous_current_avg_ua = current_avg_ua # Update previous average current
                previous_voltage_uv = voltage_uv  # Update previous voltage for next iteration
                previous_power_w = power_w # Update previous power for next iteration
                previous_temp_celsius = temp_celsius # Update previous temperature


            except ValueError:
                print("-" * 80) # Shorter separator for error messages
                print("Error: Could not convert value to integer. Raw values:")
                print(f"  Current Now (raw):   {current_now_str}") # Tab for aligned error output
                print(f"  Current Avg (raw):   {current_avg_str}") # Tab for aligned error output
                print(f"  Voltage Now (raw):       {voltage_now_str}") # Tab for aligned error output
                print(f"  Capacity (raw):      {capacity_str}") # Tab for aligned error output
                print(f"  Temperature (raw):   {temp_celsius}") # Tab for aligned error output
                print("-" * 80)
        else:
            print("-" * 80) # Shorter separator for error messages
            print("Failed to read battery data (including temperature). Check ADB connection & device. Raw values:")
            print(f"  Current Now (raw):   {current_now_str}") # Tab for aligned error output
            print(f"  Current Avg (raw):   {current_avg_str}") # Tab for aligned error output
            print(f"  Voltage Now (raw):       {voltage_now_str}") # Tab for aligned error output
            print(f"  Capacity (raw):      {capacity_str}") # Tab for aligned error output
            print(f"  Temperature (raw):   {temp_celsius}") # Tab for aligned error output
            print("-" * 80)


        time.sleep(T_sleep)

    # In a real application where the loop might terminate, you should close the file:
    # This part is not reached in this infinite loop, but good practice for other scripts.
    if ENABLE_LOGGING and csv_file is not None:
        csv_file.close()
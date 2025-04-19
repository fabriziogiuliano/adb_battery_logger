import subprocess
import time
import csv
from datetime import datetime
import re

T_sleep = 1  # Sleep time in seconds (variable)
ENABLE_LOGGING = True  # Enable/disable CSV logging
ENABLE_DELTA_COLUMNS = False  # Enable/disable delta columns
ENABLE_THERMAL_SENSORS = False # Enable/disable thermal sensor readings <--- NEW VARIABLE

# Dictionary to control displayed columns (True to show, False to hide) for VIDEO OUTPUT
DISPLAY_COLUMNS = {
    'Timestamp': True,
    'Current (mA)': True,
    'ΔCurrent (mA)': ENABLE_DELTA_COLUMNS, # Controlled by ENABLE_DELTA_COLUMNS
    'Avg Current (mA)': True,
    'ΔAvg Current (mA)': ENABLE_DELTA_COLUMNS, # Controlled by ENABLE_DELTA_COLUMNS
    'Voltage (mV)': True,
    'ΔVoltage (mV)': ENABLE_DELTA_COLUMNS, # Controlled by ENABLE_DELTA_COLUMNS
    'Power (W)': True,
    'ΔPower (W)': ENABLE_DELTA_COLUMNS, # Controlled by ENABLE_DELTA_COLUMNS
    'Capacity (%)': True,
    'Battery Temp (°C)': True,
    'Thermal Sensors': ENABLE_THERMAL_SENSORS # Master switch for thermal sensors display, controlled by ENABLE_THERMAL_SENSORS now
}


def get_battery_value(property_name):
    """Reads battery property from sysfs."""
    try:
        process = subprocess.run(
            ["./adb", "shell", f"cat /sys/class/power_supply/battery/{property_name}"],
            capture_output=True, text=True, check=True
        )
        return process.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error reading {property_name}: ADB command failed: {e}")
        return None
    except FileNotFoundError:
        print("Error: ./adb command not found.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def get_battery_temperature():
    """Reads battery temperature using dumpsys battery."""
    try:
        process = subprocess.run(
            ["./adb", "shell", "dumpsys battery | grep temp"],
            capture_output=True, text=True, check=True
        )
        output = process.stdout.strip()
        parts = output.split(':')
        if len(parts) > 1:
            try:
                return float(parts[1].strip()) / 10.0
            except ValueError:
                print(f"Warning: Could not convert temperature value to float: {parts[1].strip()}")
                return None
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error reading battery temp: ADB command failed: {e}")
        return None
    except FileNotFoundError:
        print("Error: ./adb command not found for battery temp.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred reading battery temp: {e}")
        return None

def get_device_model():
    """Retrieves device model using adb shell getprop."""
    try:
        process = subprocess.run(
            ["./adb", "shell", "getprop ro.product.model"],
            capture_output=True, text=True, check=True
        )
        return process.stdout.strip()
    except Exception:
        return "UNKNOWN_MODEL"

def get_device_serial():
    """Retrieves device serial using adb get-serialno."""
    try:
        process = subprocess.run(
            ["./adb", "get-serialno"],
            capture_output=True, text=True, check=True
        )
        return process.stdout.strip()
    except Exception:
        return "UNKNOWN_SERIAL"

def sanitize_filename(filename):
    """Sanitizes filename by replacing invalid chars."""
    return re.sub(r'[^\w\-_\.]', '_', filename)

def get_temperature_data():
    """Executes adb shell dumpsys thermalservice and returns output."""
    try:
        process = subprocess.run(['./adb', 'shell', 'dumpsys', 'thermalservice'],
                                   capture_output=True, text=True, check=True)
        return process.stdout
    except subprocess.CalledProcessError as e:
        print(f"Error executing adb for thermalservice: {e}")
        return None
    except FileNotFoundError:
        print("Error: 'adb' command not found for thermalservice.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred getting thermalservice data: {e}")
        return None

def parse_temperature_output(output):
    """Parses dumpsys thermalservice output and extracts temperatures."""
    temperatures = {}
    if output:
        lines = output.splitlines()
        start_parsing_cached = False
        start_parsing_current = False

        for line in lines:
            line = line.strip()
            if line == "Cached temperatures:":
                start_parsing_cached = True
                continue
            if line == "Current temperatures from HAL:":
                start_parsing_current = True
                start_parsing_cached = False
                continue

            start_parsing = start_parsing_current or start_parsing_cached

            if start_parsing and line.startswith("Temperature{"):
                match = re.search(r"mValue=([\d.]+),.*?mName=([^,]+)", line)
                if match:
                    value = float(match.group(1))
                    name = match.group(2).strip()
                    temperatures[name] = value
            elif start_parsing and not line.startswith("Temperature{") and line != "":
                start_parsing_cached = False
                start_parsing_current = False
    return temperatures

if __name__ == "__main__":
    print("-" * 200)
    print("Real-time Battery and Thermal Monitoring Script (Fixed-Width Output)")
    print("-" * 200)
    print(f"Polling Interval: {T_sleep:.2f} seconds")
    print(f"Logging to CSV:   {'Enabled' if ENABLE_LOGGING else 'Disabled'}")
    print(f"Delta Columns:    {'Enabled' if ENABLE_DELTA_COLUMNS else 'Disabled'}")
    print(f"Thermal Sensors:  {'Enabled' if ENABLE_THERMAL_SENSORS else 'Disabled'}") # <--- PRINT THERMAL SENSOR STATUS
    print("-" * 200)
    print("Press Ctrl+C to stop")
    print("-" * 200)

    video_header_row_parts = [] # List to build VIDEO header row dynamically
    csv_header_csv = ["Timestamp", "Current (mA)", "Avg Current (mA)", "Voltage (mV)", "Power (W)", "Capacity (%)", "Battery Temperature (°C)"] # Base CSV header - always present


    if DISPLAY_COLUMNS.get('Timestamp', False):
        video_header_row_parts.append(f"{'Timestamp':<23} | ")
    if DISPLAY_COLUMNS.get('Current (mA)', False):
        video_header_row_parts.append(f"{'Current (mA)':>10} | ")
    if DISPLAY_COLUMNS.get('ΔCurrent (mA)', False):
        video_header_row_parts.append(f"{'ΔCurrent (mA)':>10} | ")
    if DISPLAY_COLUMNS.get('Avg Current (mA)', False):
        video_header_row_parts.append(f"{'Avg Current (mA)':>10} | ")
    if DISPLAY_COLUMNS.get('ΔAvg Current (mA)', False):
        video_header_row_parts.append(f"{'ΔAvg Current (mA)':>12} | ")
    if DISPLAY_COLUMNS.get('Voltage (mV)', False):
        video_header_row_parts.append(f"{'Voltage (mV)':>10} | ")
    if DISPLAY_COLUMNS.get('ΔVoltage (mV)', False):
        video_header_row_parts.append(f"{'ΔVoltage (mV)':>10} | ")
    if DISPLAY_COLUMNS.get('Power (W)', False):
        video_header_row_parts.append(f"{'Power (W)':>10} | ")
    if DISPLAY_COLUMNS.get('ΔPower (W)', False):
        video_header_row_parts.append(f"{'ΔPower (W)':>10} | ")
    if DISPLAY_COLUMNS.get('Capacity (%)', False):
        video_header_row_parts.append(f"{'Capacity (%)':>8} | ")
    if DISPLAY_COLUMNS.get('Battery Temp (°C)', False):
        video_header_row_parts.append(f"{'Battery Temp (°C)':>12} | ")


    print("".join(video_header_row_parts), end="") # Print initial VIDEO header, sensor columns will be added later

    thermal_sensor_names = [] # To store sensor names for header, will be populated in the loop

    previous_current_ua = None
    previous_current_avg_ua = None
    previous_voltage_uv = None
    previous_power_w = None
    previous_temp_celsius = None

    csv_filename = "battery_thermal_data.csv"
    csv_file = None
    csv_writer = None

    if ENABLE_LOGGING:
        device_model = get_device_model()
        device_serial = get_device_serial()
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_model = sanitize_filename(device_model)
        sanitized_serial = sanitize_filename(device_serial)
        csv_filename = f"battery_thermal_log_{sanitized_model}_{sanitized_serial}_{timestamp_str}.csv"

        csv_file = open(csv_filename, 'w', newline='')
        csv_writer = csv.writer(csv_file)
        # csv_header_csv is defined before the loop now
        print(f"Logging data to: {csv_filename}")

    first_iteration = True # Flag for the first iteration

    while True:
        current_now_str = get_battery_value("current_now")
        current_avg_str = get_battery_value("current_avg")
        voltage_now_str = get_battery_value("voltage_now")
        capacity_str = get_battery_value("capacity")
        temp_celsius = get_battery_temperature()
        thermal_sensors = {} # Initialize as empty dictionary in case thermal sensors are disabled
        if ENABLE_THERMAL_SENSORS: # <--- CONDITIONAL THERMAL SENSOR READING
            thermal_output = get_temperature_data()
            thermal_sensors = parse_temperature_output(thermal_output) if thermal_output else {}

        if current_now_str is not None and current_avg_str is not None and voltage_now_str is not None and capacity_str is not None and temp_celsius is not None: # Thermal sensors are now optional in the main condition
            try:
                current_ua = int(current_now_str)
                current_avg_ua = int(current_avg_str)
                voltage_uv = int(voltage_now_str)
                capacity_percent = int(capacity_str)

                current_ma = current_ua / 1000.0
                current_avg_ma = current_avg_ua / 1000.0
                voltage_mv = voltage_uv / 1000.0
                power_w = (voltage_mv / 1000) * abs(current_ma / 1000)

                current_delta_ma = None
                current_avg_delta_ma = None
                voltage_delta_mv = None
                power_delta_mw = None

                if previous_current_ua is not None and previous_current_avg_ua is not None and previous_voltage_uv is not None and previous_power_w is not None:
                    current_delta_ma = (current_ua - previous_current_ua) / 1000.0
                    current_avg_delta_ma = (current_avg_ua - previous_current_avg_ua) / 1000.0
                    voltage_delta_mv = (voltage_uv - previous_voltage_uv) / 1000.0
                    power_delta_mw = power_w - previous_power_w

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

                print_output_parts = []

                if DISPLAY_COLUMNS.get('Timestamp', False):
                    print_output_parts.append(f"{timestamp:<23} | ")
                if DISPLAY_COLUMNS.get('Current (mA)', False):
                    print_output_parts.append(f"{current_ma:>10.2f} | ")
                if DISPLAY_COLUMNS.get('ΔCurrent (mA)', False):
                    if ENABLE_DELTA_COLUMNS and current_delta_ma is not None:
                        print_output_parts.append(f"{current_delta_ma:>+10.2f} | ")
                    elif ENABLE_DELTA_COLUMNS:
                        print_output_parts.append(f"{'Initial':>10} | ")
                if DISPLAY_COLUMNS.get('Avg Current (mA)', False):
                    print_output_parts.append(f"{current_avg_ma:>10.2f} | ")
                if DISPLAY_COLUMNS.get('ΔAvg Current (mA)', False):
                    if ENABLE_DELTA_COLUMNS and current_avg_delta_ma is not None:
                        print_output_parts.append(f"{current_avg_delta_ma:>+12.2f} | ")
                    elif ENABLE_DELTA_COLUMNS:
                        print_output_parts.append(f"{'Initial':>12} | ")
                if DISPLAY_COLUMNS.get('Voltage (mV)', False):
                    print_output_parts.append(f"{voltage_mv:>10.2f} | ")
                if DISPLAY_COLUMNS.get('ΔVoltage (mV)', False):
                    if ENABLE_DELTA_COLUMNS and voltage_delta_mv is not None:
                        print_output_parts.append(f"{voltage_delta_mv:>+10.2f} | ")
                    elif ENABLE_DELTA_COLUMNS:
                        print_output_parts.append(f"{'Initial':>10} | ")
                if DISPLAY_COLUMNS.get('Power (W)', False):
                    print_output_parts.append(f"{power_w:>10.2f} | ")
                if DISPLAY_COLUMNS.get('ΔPower (W)', False):
                    if ENABLE_DELTA_COLUMNS and power_delta_mw is not None:
                        print_output_parts.append(f"{power_delta_mw:>+10.2f} | ")
                    elif ENABLE_DELTA_COLUMNS:
                        print_output_parts.append(f"{'Initial':>10} | ")
                if DISPLAY_COLUMNS.get('Capacity (%)', False):
                    print_output_parts.append(f"{capacity_percent:>8}% | ")
                if DISPLAY_COLUMNS.get('Battery Temp (°C)', False):
                    print_output_parts.append(f"{temp_celsius:>12.2f}°C | ")


                # Add thermal sensor values to output and header if it's the first iteration AND thermal sensors are enabled
                if first_iteration and ENABLE_THERMAL_SENSORS: # <--- CHECK ENABLE_THERMAL_SENSORS HERE
                    thermal_sensor_names = list(thermal_sensors.keys()) # Get sensor names for header
                    video_header_sensors_row_parts = []

                    for sensor_name in thermal_sensor_names:
                        sensor_header_name = sensor_name.replace("soc_", "").replace("_therm", "").replace("_throttling", "").title() # Simplify sensor name for header
                        DISPLAY_COLUMNS[sensor_header_name] = DISPLAY_COLUMNS.get('Thermal Sensors', True) # Enable display based on 'Thermal Sensors' master switch or default to True
                        if DISPLAY_COLUMNS.get(sensor_header_name, False): # Only add to video header if enabled in DISPLAY_COLUMNS
                            video_header_sensors_row_parts.append(f"{sensor_header_name:>18} | ") # Adjust width as needed
                        csv_header_csv.append(sensor_name) # Add full sensor name to CSV header - always log all sensors

                    print("".join(video_header_sensors_row_parts)) # Print sensor headers for VIDEO after initial header
                    print("-" * 200) # Separator after full header is printed
                    if ENABLE_LOGGING and csv_writer is not None:
                        csv_writer.writerow(csv_header_csv) # Write full CSV header including ALL sensors
                        csv_file.flush() # Flush after writing header


                sensor_values_output_parts = []
                csv_row_data = [timestamp, f"{current_ma:.2f}", f"{current_avg_ma:.2f}", f"{voltage_mv:.2f}", f"{power_w:.2f}", capacity_percent, f"{temp_celsius:.2f}"] # Base CSV data, battery temp to 2 decimals as well
                if ENABLE_THERMAL_SENSORS: # <--- CONDITIONAL THERMAL SENSOR OUTPUT AND CSV DATA
                    for sensor_name in thermal_sensor_names: # Use names from the first iteration to maintain order
                        sensor_value = thermal_sensors.get(sensor_name, "N/A") # Get value, default to "N/A" if not found
                        sensor_header_name = sensor_name.replace("soc_", "").replace("_therm", "").replace("_throttling", "").title() # Simplify sensor name for header
                        if DISPLAY_COLUMNS.get(sensor_header_name, False): # Only print to VIDEO if enabled in DISPLAY_COLUMNS
                            sensor_values_output_parts.append(f"{sensor_value:>18.2f} | " if isinstance(sensor_value, float) else f"{str(sensor_value).rjust(18)} | ") # Format float or string - ALREADY FORMATTED TO 2 DECIMAL PLACES
                        csv_row_data.append(sensor_value if isinstance(sensor_value, (int, float)) else str(sensor_value)) # Add to CSV row, keep numeric or string


                print("".join(print_output_parts), end="") # Print battery and base temp data for VIDEO
                print("".join(sensor_values_output_parts)) # Print thermal sensor values for VIDEO

                if ENABLE_LOGGING and csv_writer is not None:
                    csv_writer.writerow(csv_row_data)
                    csv_file.flush()

                previous_current_ua = current_ua
                previous_current_avg_ua = current_avg_ua
                previous_voltage_uv = voltage_uv
                previous_power_w = power_w
                previous_temp_celsius = temp_celsius
                first_iteration = False # Disable flag after first iteration - moved here to ensure header is written even if no thermal sensors are read in the first iteration when disabled

            except ValueError:
                print("-" * 80)
                print("Error: Could not convert value to integer. Raw values:")
                print(f"  Current Now (raw):   {current_now_str}")
                print(f"  Current Avg (raw):   {current_avg_str}")
                print(f"  Voltage Now (raw):       {voltage_now_str}")
                print(f"  Capacity (raw):      {capacity_str}")
                print(f"  Battery Temperature (raw):   {temp_celsius}")
                if ENABLE_THERMAL_SENSORS:
                    print(f"  Thermal Sensors (raw):   {thermal_sensors}")
                print("-" * 80)
        else:
            print("-" * 80)
            print("Failed to read battery and/or thermal data. Check ADB connection & device. Raw values:")
            print(f"  Current Now (raw):   {current_now_str}")
            print(f"  Current Avg (raw):   {current_avg_str}")
            print(f"  Voltage Now (raw):       {voltage_now_str}")
            print(f"  Capacity (raw):      {capacity_str}")
            print(f"  Battery Temperature (raw):   {temp_celsius}")
            if ENABLE_THERMAL_SENSORS:
                print(f"  Thermal Sensors (raw):   {thermal_sensors}")
            print("-" * 80)

        time.sleep(T_sleep)

    if ENABLE_LOGGING and csv_file is not None:
        csv_file.close()
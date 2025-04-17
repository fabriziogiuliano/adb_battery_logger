import subprocess
import time
import csv  # Import the csv module
from datetime import datetime  # Import datetime for timestamps

T_sleep = 1  # Sleep time in seconds (variable)
ENABLE_LOGGING = True  # Hardcoded variable to enable/disable CSV logging (True to enable, False to disable)

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

if __name__ == "__main__":
    print("-" * 140) # Increased separator width for fixed width output
    print("Real-time Battery Monitoring Script with Calculated Power (Fixed-Width Output)")
    print("-" * 140)
    print(f"Polling Interval: {T_sleep:.2f} seconds")
    print(f"Logging to CSV:   {'Enabled' if ENABLE_LOGGING else 'Disabled'}")
    print("-" * 140)
    print("Press Ctrl+C to stop")
    print("-" * 140)
    print(f"{'Timestamp':<23} | {'Current (mA)':>10} | {'ΔCurrent (mA)':>10} | {'Avg Current (mA)':>10} | {'ΔAvg Current (mA)':>12} | {'Voltage (mV)':>10} | {'ΔVoltage (mV)':>10} | {'Power (W)':>10} | {'ΔPower (W)':>10} | {'Capacity (%)':>8}") # Header row with fixed widths and shorter units
    print("-" * 140)


    previous_current_ua = None
    previous_current_avg_ua = None # Track previous average current
    previous_voltage_uv = None
    previous_power_w = None # Track previous power (calculated) - now tracking mW directly

    csv_filename = "battery_data.csv"  # Name of the CSV file
    csv_file = None # Initialize csv_file outside the if block
    csv_writer = None # Initialize csv_writer outside the if block

    if ENABLE_LOGGING:
        csv_file = open(csv_filename, 'w', newline='') # Open CSV file in write mode if logging is enabled
        csv_writer = csv.writer(csv_file) # Create CSV writer object
        # Write header row to CSV with shorter units
        csv_writer.writerow(["Timestamp", "Current (mA)", "Current Δ (mA)", "Avg Current (mA)", "Avg Current Δ (mA)", "Voltage (mV)", "Voltage Δ (mV)", "Power (mW)", "Power Δ (W)", "Capacity (%)"])

    while True:
        current_now_str = get_battery_value("current_now")
        current_avg_str = get_battery_value("current_avg") # Get average current
        voltage_now_str = get_battery_value("voltage_now")
        capacity_str = get_battery_value("capacity") # Get capacity value

        if current_now_str is not None and current_avg_str is not None and voltage_now_str is not None and capacity_str is not None:
            try:
                current_ua = int(current_now_str)  # Current in microamps (instantaneous)
                current_avg_ua = int(current_avg_str) # Average current in microamps
                voltage_uv = int(voltage_now_str)  # Voltage in microvolts (instantaneous)
                capacity_percent = int(capacity_str) # Capacity as percentage

                current_ma = current_ua / 1000.0  # Convert instantaneous to milliamps for easier reading
                current_avg_ma = current_avg_ua / 1000.0 # Convert average to milliamps
                voltage_mv = voltage_uv / 1000.0  # Convert to millivolts for easier reading

                # Calculate power in milliwatts (mW) - Corrected calculation
                power_w = voltage_mv/1000 * abs(current_ma/1000)

                current_delta_ma = None
                current_avg_delta_ma = None # Delta for average current
                voltage_delta_mv = None
                power_delta_mw = None # Delta for power

                if previous_current_ua is not None and previous_current_avg_ua is not None and previous_voltage_uv is not None and previous_power_w is not None: # Changed to previous_power_w
                    current_delta_ma = (current_ua - previous_current_ua) / 1000.0
                    current_avg_delta_ma = (current_avg_ua - previous_current_avg_ua) / 1000.0 # Calculate delta for average current
                    voltage_delta_mv = (voltage_uv - previous_voltage_uv) / 1000.0
                    power_delta_mw = power_w - previous_power_w # Calculate delta for power - now using mW directly

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f") # Get timestamp with milliseconds

                if current_delta_ma is not None and current_avg_delta_ma is not None and voltage_delta_mv is not None and power_delta_mw is not None:
                    print_output = f"{timestamp:<23} | " # Timestamp (left aligned, width 23)
                    print_output += f"{current_ma:>10.2f} | " # Current Now (right aligned, width 10, 2 decimal places)
                    print_output += f"{current_delta_ma:>+10.2f} | " # Current Now Delta (right aligned, width 10, with sign, 2 decimal places)
                    print_output += f"{current_avg_ma:>10.2f} | " # Current Avg (right aligned, width 10, 2 decimal places)
                    print_output += f"{current_avg_delta_ma:>+12.2f} | " # Current Avg Delta (right aligned, width 12, with sign, 2 decimal places)
                    print_output += f"{voltage_mv:>10.2f} | " # Voltage Now (right aligned, width 10, 2 decimal places)
                    print_output += f"{voltage_delta_mv:>+10.2f} | " # Voltage Now Delta (right aligned, width 10, with sign, 2 decimal places)
                    print_output += f"{power_w:>10.2f} | " # Power Now (right aligned, width 10, 2 decimal places)
                    print_output += f"{power_delta_mw:>+10.2f} | " # Power Now Delta (right aligned, width 10, with sign, 2 decimal places)
                    print_output += f"{capacity_percent:>8}%" # Capacity (right aligned, width 8)
                    print(print_output)

                    if ENABLE_LOGGING and csv_writer is not None:
                        csv_writer.writerow([timestamp, f"{current_ma:.2f}", f"{current_delta_ma:.2f}", f"{current_avg_ma:.2f}", f"{current_avg_delta_ma:.2f}", f"{voltage_mv:.2f}", f"{voltage_delta_mv:.2f}", f"{power_w:.2f}", f"{power_delta_mw:.2f}", capacity_percent]) # Write row to CSV
                else:
                    print_output = f"{timestamp:<23} | " # Timestamp (left aligned, width 23)
                    print_output += f"{current_ma:>10.2f} | " # Current Now (right aligned, width 10, 2 decimal places)
                    print_output += f"{'Initial':>10} | " # Current Now Delta - Initial Value (right aligned, width 10)
                    print_output += f"{current_avg_ma:>10.2f} | " # Current Avg (right aligned, width 10, 2 decimal places)
                    print_output += f"{'Initial':>12} | " # Current Avg Delta - Initial Value (right aligned, width 12)
                    print_output += f"{voltage_mv:>10.2f} | " # Voltage Now (right aligned, width 10, 2 decimal places)
                    print_output += f"{'Initial':>10} | " # Voltage Now Delta - Initial Value (right aligned, width 10)
                    print_output += f"{power_w:>10.2f} | " # Power Now (right aligned, width 10, 2 decimal places)
                    print_output += f"{'Initial':>10} | " # Power Now Delta - Initial Value (right aligned, width 10)
                    print_output += f"{capacity_percent:>8}%" # Capacity (right aligned, width 8)
                    print(print_output)

                    if ENABLE_LOGGING and csv_writer is not None:
                        csv_writer.writerow([timestamp, f"{current_ma:.2f}", "", f"{current_avg_ma:.2f}", "", f"{voltage_mv:.2f}", "", f"{power_w:.2f}", "", capacity_percent]) # Write initial value row to CSV (empty delta columns)

                previous_current_ua = current_ua  # Update previous current for next iteration
                previous_current_avg_ua = current_avg_ua # Update previous average current
                previous_voltage_uv = voltage_uv  # Update previous voltage for next iteration
                previous_power_w = power_w # Update previous power for next iteration - now storing mW


            except ValueError:
                print("-" * 80) # Shorter separator for error messages
                print("Error: Could not convert value to integer. Raw values:")
                print(f"  Current Now (raw):   {current_now_str}") # Tab for aligned error output
                print(f"  Current Avg (raw):   {current_avg_str}") # Tab for aligned error output
                print(f"  Voltage Now (raw):       {voltage_now_str}") # Tab for aligned error output
                print(f"  Capacity (raw):      {capacity_str}") # Tab for aligned error output
                print("-" * 80)
        else:
            print("-" * 80) # Shorter separator for error messages
            print("Failed to read battery data. Check ADB connection & device. Raw values:")
            print(f"  Current Now (raw):   {current_now_str}") # Tab for aligned error output
            print(f"  Current Avg (raw):   {current_avg_str}") # Tab for aligned error output
            print(f"  Voltage Now (raw):       {voltage_now_str}") # Tab for aligned error output
            print(f"  Capacity (raw):      {capacity_str}") # Tab for aligned error output
            print("-" * 80)


        time.sleep(T_sleep)

    # In a real application where the loop might terminate, you should close the file:
    # This part is not reached in this infinite loop, but good practice for other scripts.
    if ENABLE_LOGGING and csv_file is not None:
        csv_file.close()
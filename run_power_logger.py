import subprocess
import time
import csv
from datetime import datetime
import re
import sys
import os

# ========================= GLOBAL CONFIGURATION =========================
T_sleep = 0.5  # Wait time in seconds (variable, try smaller values now)
ENABLE_LOGGING = True  # Enable/disable CSV logging
ENABLE_DELTA_COLUMNS = False # Enable/disable delta columns (for display and CSV)
ENABLE_THERMAL_SENSORS = True # Enable/disable thermal sensor reading
ENABLE_CPU_MONITORING = True  # Enable/disable CPU monitoring (now faster)
ENABLE_MEMORY_MONITORING = True # Enable/disable Memory monitoring (now faster)

# Path to the ADB executable (modify if necessary)
ADB_PATH = "./adb"

# Default column selection for display prompt ('all' or '1-7' or specific numbers '1,2,5')
# Set to 'all' to display everything by default without prompting for selection each time.
# Change this value to customize the default selection shown in the prompt.
COLUMN_SELECTION_DEFAULT = '1-20' # Example: Default to basic power metrics
# COLUMN_SELECTION_DEFAULT = 'all' # Alternative: Default to all detected columns

# --- Internal constants ---
# CPU states from /proc/stat (adjust if device has different columns)
CPU_FIELDS = ['user', 'nice', 'system', 'idle', 'iowait', 'irq', 'softirq', 'steal', 'guest', 'guest_nice']
# ========================= END GLOBAL CONFIGURATION =====================

# --- Helper Functions (Improved & Translated) ---

def run_adb_command(command_args, capture=True, text=True, check=False): # Default check=False to handle errors internally
    """Executes an ADB command and handles common errors."""
    global ADB_PATH # Allow modification if ADB found in PATH
    try:
        # Add encoding and error handling for potentially problematic output
        process = subprocess.run(
            [ADB_PATH] + command_args,
            capture_output=capture, text=text, check=check,
            encoding='utf-8', errors='ignore' # Ignore decoding errors
        )
        if check and process.returncode != 0:
             # If check=True was required and failed, print error but continue (return None)
             print(f"\nADB Error (Code {process.returncode}): Command '{' '.join(command_args)}' failed.", file=sys.stderr)
             if process.stderr:
                 print(f"Stderr: {process.stderr.strip()}", file=sys.stderr)
             return None

        # If check=False, we still check returncode for safety
        if process.returncode != 0:
             # Don't print error if check=False, might be expected (e.g., grep finding nothing)
             # But return None to indicate the command didn't succeed as expected.
             # print(f"Debug: Command '{' '.join(command_args)}' finished with code {process.returncode}", file=sys.stderr)
             return None # Indicate failure or non-useful output

        return process.stdout.strip() if capture else True # Return True if capture=False and success
    except subprocess.CalledProcessError as e:
        # This is caught only if check=True fails
        print(f"\nADB Error: Command '{' '.join(command_args)}' failed: {e}", file=sys.stderr)
        return None
    except FileNotFoundError:
        # Try finding adb in system PATH if initial path fails
        try:
            result = subprocess.run(['which', 'adb'], capture_output=True, text=True, check=True)
            found_adb_path = result.stdout.strip()
            if found_adb_path and os.path.exists(found_adb_path):
                print(f"Warning: ADB not found at '{ADB_PATH}'. Found and using '{found_adb_path}' from system PATH.", file=sys.stderr)
                ADB_PATH = found_adb_path
                # Retry the command with the found path
                return run_adb_command(command_args, capture, text, check)
            else:
                raise FileNotFoundError # Raise again if 'which' result is invalid
        except (FileNotFoundError, subprocess.CalledProcessError):
            print(f"\nError: Command '{ADB_PATH}' not found. Make sure ADB is in the specified path or in the system PATH.", file=sys.stderr)
            sys.exit(1) # Exit if ADB cannot be found
    except Exception as e:
        print(f"\nUnexpected error during ADB execution '{' '.join(command_args)}': {e}", file=sys.stderr)
        return None

def get_battery_value(property_name):
    """Reads battery properties from sysfs."""
    # Don't use check=True because a file might not exist (e.g., current_avg on some devices)
    output = run_adb_command(["shell", f"cat /sys/class/power_supply/battery/{property_name}"], check=False)
    # print(f"Debug Batt Read: {property_name} -> {output}") # DEBUG
    return output

def get_battery_temperature():
    """Reads battery temperature from dumpsys battery."""
    # We use grep, so check=False is appropriate (might not find "temp")
    output = run_adb_command(["shell", "dumpsys battery | grep temp"], check=False)
    # print(f"Debug Batt Temp Raw: {output}") # DEBUG
    if output:
        parts = output.split(':')
        if len(parts) > 1:
            val_str = parts[1].strip()
            try:
                temp_val = float(val_str) / 10.0
                # print(f"Debug Batt Temp Parsed: {temp_val}") # DEBUG
                return temp_val
            except ValueError:
                print(f"Warning: Cannot convert battery temperature value: '{val_str}'", file=sys.stderr)
                return None
    return None

def get_temperature_data():
    """Executes adb shell dumpsys thermalservice and returns output."""
    # check=True here is reasonable, the service should exist
    output = run_adb_command(['shell', 'dumpsys', 'thermalservice'], check=True)
    # print(f"Debug Thermal Raw: {'Long output...' if output else 'No output'}") # DEBUG
    return output

def parse_temperature_output(output):
    """Parses dumpsys thermalservice output and extracts temperatures."""
    temperatures = {}
    if not output:
        return temperatures

    lines = output.splitlines()
    start_parsing_cached = False
    start_parsing_current = False

    # Improved regex: looks for name and value more flexibly
    temp_regex = re.compile(r"Temperature\{.*?mValue=([\d.-]+).*?mName=([^,}]+)")

    current_section_temps = {} # Prioritize Current HAL
    cached_section_temps = {}

    for line in lines:
        line = line.strip()
        if line == "Cached temperatures:":
            start_parsing_cached = True
            start_parsing_current = False
            continue
        if line == "Current temperatures from HAL:":
            start_parsing_current = True
            start_parsing_cached = False
            continue
        if line == "Sensor Status:": # Next section, stop looking for temperatures
             start_parsing_cached = False
             start_parsing_current = False
             continue

        if start_parsing_current or start_parsing_cached:
            match = temp_regex.search(line)
            if match:
                try:
                    value = float(match.group(1))
                    # Clean name: remove leading/trailing spaces, replace internal spaces with _, remove quotes
                    name = match.group(2).strip().replace(" ", "_").replace('"','')
                    if start_parsing_current:
                        current_section_temps[name] = value
                    elif start_parsing_cached:
                         # Add only if not present in Current HAL section
                         if name not in current_section_temps:
                             cached_section_temps[name] = value

                except ValueError:
                    print(f"Warning: Cannot convert thermal sensor value: {match.group(1)} for {match.group(2)}", file=sys.stderr)
                except IndexError:
                     print(f"Warning: Regex failed on thermal line: {line}", file=sys.stderr)

    # Merge results, prioritizing "Current HAL"
    temperatures.update(cached_section_temps)
    temperatures.update(current_section_temps) # Overwrites cached if duplicates exist
    # print(f"Debug Thermal Parsed: {temperatures}") # DEBUG
    return temperatures

# ========================================================================
# <<< START OF NEW get_cpu_usage FUNCTION (using /proc/stat) >>>
# ========================================================================
def get_cpu_usage(previous_stat_data):
    """
    Gets CPU usage percentages by comparing /proc/stat readings.
    Returns a dictionary with CPU stats and the current raw stat data for the next iteration.
    Returns (None, previous_stat_data) on failure.
    """
    output = run_adb_command(["shell", "cat /proc/stat"], check=False)
    if not output:
        print("Warning: Failed to read /proc/stat for CPU usage.", file=sys.stderr)
        return None, previous_stat_data # Return previous data on failure

    lines = output.splitlines()
    if not lines or not lines[0].startswith("cpu "):
        print("Warning: Unexpected format in /proc/stat output.", file=sys.stderr)
        return None, previous_stat_data

    # Parse current CPU times from the first line ("cpu  user nice system idle iowait irq softirq steal guest guest_nice")
    parts = lines[0].split()
    current_stat_values = {}
    total_ticks_current = 0
    try:
        raw_values = [int(p) for p in parts[1:]]
        for i, field in enumerate(CPU_FIELDS):
            if i < len(raw_values):
                current_stat_values[field] = raw_values[i]
                total_ticks_current += raw_values[i]
            else:
                current_stat_values[field] = 0 # Handle devices with fewer fields
    except (ValueError, IndexError):
        print("Warning: Failed to parse CPU times from /proc/stat.", file=sys.stderr)
        return None, previous_stat_data

    current_stat_data = {'values': current_stat_values, 'total_ticks': total_ticks_current}

    # Calculate percentages if previous data exists
    cpu_percentages = { # Initialize with N/A
        "total": 'N/A', "user": 'N/A', "nice": 'N/A', "system": 'N/A',
        "idle": 'N/A', "iowait": 'N/A', "irq": 'N/A', "sirq": 'N/A',
        #"host": 'N/A' # 'steal' or 'guest' might map here, but keep simple for now
    }

    if previous_stat_data:
        prev_values = previous_stat_data['values']
        prev_total = previous_stat_data['total_ticks']
        delta_total = total_ticks_current - prev_total

        if delta_total > 0: # Avoid division by zero and nonsensical negative delta
            deltas = {}
            active_delta_sum = 0
            for field in CPU_FIELDS:
                 delta = current_stat_values.get(field, 0) - prev_values.get(field, 0)
                 deltas[field] = delta
                 # Calculate percentage
                 percentage = (delta / delta_total) * 100.0
                 cpu_percentages[field] = round(percentage, 1)
                 # Sum non-idle components for total
                 if field not in ['idle', 'guest', 'guest_nice']: # Consider main active components
                     active_delta_sum += delta

            # Calculate total usage based on sum of active components or 100 - idle
            # Using 100 - idle is often more intuitive
            if isinstance(cpu_percentages.get('idle'), (int, float)):
                 cpu_percentages['total'] = round(100.0 - cpu_percentages['idle'], 1)
            elif active_delta_sum > 0: # Fallback to summing active parts
                 cpu_percentages['total'] = round((active_delta_sum / delta_total) * 100.0, 1)

            # Map specific fields if needed (e.g., softirq -> sirq)
            cpu_percentages['sirq'] = cpu_percentages.get('softirq', 'N/A')
            # 'host' usually relates to virtualization (steal/guest), mark N/A for simplicity unless needed
            #cpu_percentages['host'] = 'N/A'

        # else: print(f"Debug CPU: Delta total is {delta_total}, skipping percentage calculation.")

    # Return calculated percentages and the raw data for the next calculation
    # print(f"Debug CPU Parsed: {cpu_percentages}") # DEBUG
    return cpu_percentages, current_stat_data

# ========================================================================
# <<< END OF NEW get_cpu_usage FUNCTION >>>
# ========================================================================


# ========================================================================
# <<< START OF NEW get_memory_usage FUNCTION (using /proc/meminfo) >>>
# ========================================================================
def get_memory_usage():
    """Gets memory usage from /proc/meminfo."""
    output = run_adb_command(["shell", "cat /proc/meminfo"], check=False)
    # print(f"Debug Mem Raw Output (/proc/meminfo):\n{output}\n----------------") # DEBUG

    mem_data = { # Initialize with N/A
        'total_mb': 'N/A', 'used_mb': 'N/A', 'free_mb': 'N/A',
        'available_mb': 'N/A', 'buffers_mb': 'N/A', 'cached_mb': 'N/A',
        'swap_total_mb': 'N/A', 'swap_used_mb': 'N/A'
    }

    if not output:
        print("Warning: Failed to read /proc/meminfo for memory usage.", file=sys.stderr)
        return mem_data # Return N/A dict

    meminfo = {}
    try:
        for line in output.splitlines():
            parts = line.split(':')
            if len(parts) == 2:
                key = parts[0].strip()
                # Parse value, remove " kB" suffix if present
                value_str = parts[1].strip().lower().replace(' kb', '')
                try:
                    meminfo[key] = int(value_str)
                except ValueError:
                    # Ignore lines with non-integer values
                    pass #print(f"Debug Mem: Ignoring line '{line}'", file=sys.stderr)
    except Exception as e:
         print(f"Warning: Error parsing /proc/meminfo: {e}", file=sys.stderr)
         return mem_data # Return N/A dict on parsing error

    # --- Calculate Memory Values (in MB) ---
    def kb_to_mb(kb_val):
        return round(kb_val / 1024.0, 0) if isinstance(kb_val, (int, float)) else 'N/A'

    total_kb = meminfo.get('MemTotal')
    free_kb = meminfo.get('MemFree')
    available_kb = meminfo.get('MemAvailable') # Preferred measure of available memory
    buffers_kb = meminfo.get('Buffers')
    cached_kb = meminfo.get('Cached')
    swap_total_kb = meminfo.get('SwapTotal')
    swap_free_kb = meminfo.get('SwapFree')
    # SReclaimable is part of cache that might be freed (can be added to Cached for a broader view if needed)
    # sreclaimable_kb = meminfo.get('SReclaimable')

    mem_data['total_mb'] = kb_to_mb(total_kb)
    mem_data['free_mb'] = kb_to_mb(free_kb)
    mem_data['buffers_mb'] = kb_to_mb(buffers_kb)
    mem_data['cached_mb'] = kb_to_mb(cached_kb) # Just 'Cached' value

    # Calculate 'Available' (use MemAvailable if present, otherwise estimate)
    if available_kb is not None:
        mem_data['available_mb'] = kb_to_mb(available_kb)
    elif free_kb is not None and buffers_kb is not None and cached_kb is not None:
         # Basic estimate if MemAvailable is missing (less accurate)
        mem_data['available_mb'] = kb_to_mb(free_kb + buffers_kb + cached_kb)
    else:
         mem_data['available_mb'] = 'N/A'

    # Calculate 'Used' RAM
    if total_kb is not None:
        if available_kb is not None: # Preferred calculation: Total - Available
             mem_data['used_mb'] = kb_to_mb(total_kb - available_kb)
        elif free_kb is not None and buffers_kb is not None and cached_kb is not None: # Fallback calculation
             mem_data['used_mb'] = kb_to_mb(total_kb - free_kb - buffers_kb - cached_kb)
        else: # Cannot calculate
             mem_data['used_mb'] = 'N/A'
    else:
         mem_data['used_mb'] = 'N/A'

    # Calculate Swap
    mem_data['swap_total_mb'] = kb_to_mb(swap_total_kb)
    if swap_total_kb is not None and swap_total_kb > 0 and swap_free_kb is not None:
        mem_data['swap_used_mb'] = kb_to_mb(swap_total_kb - swap_free_kb)
    elif swap_total_kb == 0:
         mem_data['swap_used_mb'] = 0 # No swap used if total is 0
    else:
         mem_data['swap_used_mb'] = 'N/A'

    # print(f"Debug Mem Parsed (/proc): {mem_data}") # DEBUG
    return mem_data
# ========================================================================
# <<< END OF NEW get_memory_usage FUNCTION >>>
# ========================================================================


def get_device_model():
    """Retrieves device model."""
    model = run_adb_command(["shell", "getprop ro.product.model"])
    return model if model else "UNKNOWN_MODEL"

def get_device_serial():
    """Retrieves device serial number."""
    serial = run_adb_command(["get-serialno"])
    return serial if serial else "UNKNOWN_SERIAL"

def sanitize_filename(filename):
    """Sanitizes a string to be used as a filename."""
    sanitized = re.sub(r'[<>:"/\\|?*\s]+', '_', filename) # Replace one or more illegal characters with underscore
    sanitized = re.sub(r'_+', '_', sanitized) # Remove multiple underscores
    sanitized = sanitized.strip('._') # Remove leading/trailing dots or underscores
    return sanitized if sanitized else "invalid_filename"


# --- Structure Functions (Translated) ---

def get_all_available_columns(include_thermal=True, include_cpu=True, include_memory=True, include_deltas=True):
    """Determines all potentially available columns."""
    columns = [ # Base order
        'Timestamp', 'Current (mA)', 'Avg Current (mA)', 'Voltage (mV)',
        'Power (W)', 'Capacity (%)', 'Battery Temp (°C)'
    ]

    if include_deltas:
        columns.extend([
            'ΔCurrent (mA)', 'ΔAvg Current (mA)', 'ΔVoltage (mV)', 'ΔPower (W)'
        ])

    if include_cpu:
        columns.extend([ # Keep consistent order (matches new function output keys)
            'CPU Total (%)', 'CPU User (%)','CPU System (%)', 'CPU Nice (%)',
            'CPU Idle (%)', 'CPU Iowait (%)', 'CPU Irq (%)', 'CPU Sirq (%)',
            #'CPU Host (%)' # Kept, but likely N/A from /proc/stat
        ])

    if include_memory:
        columns.extend([ # Matches new function output keys
            'Memory Total (MB)', 'Memory Used (MB)', 'Memory Free (MB)',
            'Memory Available (MB)', 'Memory Buffers (MB)', 'Memory Cached (MB)',
            'Swap Total (MB)', 'Swap Used (MB)'
        ])

    thermal_sensor_names = []
    if include_thermal:
        print("Retrieving thermal sensor names from device...")
        thermal_output = get_temperature_data()
        if thermal_output:
            thermal_sensors = parse_temperature_output(thermal_output)
            # Sort sensor names alphabetically for consistent output
            thermal_sensor_names = sorted(list(thermal_sensors.keys()))
            columns.extend(thermal_sensor_names) # Add at the end
            print(f"Found {len(thermal_sensor_names)} thermal sensors.")
        else:
            print("Warning: Could not retrieve thermal sensor names.", file=sys.stderr)

    return columns, thermal_sensor_names


def prompt_user_for_display_columns(all_columns, default_selection='all'):
    """Asks the user which columns to display."""
    print("\n--- Available Columns for Display ---")
    for i, col_name in enumerate(all_columns):
        print(f"  {i+1}: {col_name}")

    while True:
        try:
            prompt_text = (f"\nEnter the numbers of the columns to display, separated by commas (e.g., 1,3,5) "
                           f"or ranges (e.g., 1-4,8,10-12), or 'all' for all.\n"
                           f"(Default: '{default_selection}'): ")
            choice_str = input(prompt_text).strip()

            # Use default if input is empty
            if not choice_str:
                 choice_str = default_selection

            choice_str = choice_str.lower()

            if choice_str == 'all':
                chosen_indices = set(range(len(all_columns)))
            else:
                chosen_indices = set()
                parts = choice_str.split(',')
                for part in parts:
                    part = part.strip()
                    if not part: continue
                    if '-' in part:
                        start_str, end_str = part.split('-')
                        start = int(start_str)
                        end = int(end_str)
                        if start < 1 or end > len(all_columns) or start > end:
                            raise ValueError(f"Invalid range: {part}")
                        chosen_indices.update(range(start - 1, end)) # 0-based indices
                    else:
                        idx = int(part)
                        if idx < 1 or idx > len(all_columns):
                            raise ValueError(f"Invalid column number: {idx}")
                        chosen_indices.add(idx - 1)

            if not chosen_indices:
                print("No columns selected. Please try again.")
                continue

            # Use an ordered list based on the original order
            chosen_columns_ordered = [all_columns[i] for i in range(len(all_columns)) if i in chosen_indices]

            print("\nSelected columns for display:")
            for col in chosen_columns_ordered:
                 print(f" - {col}")
            # Return the ordered list, not the set, to maintain order
            return chosen_columns_ordered

        except ValueError as e:
            print(f"Invalid input: {e}. Make sure to use numbers, commas, or hyphens correctly. Please try again.")
        except Exception as e:
            print(f"Unexpected error during input: {e}. Please try again.")


def build_display_header(ordered_chosen_columns):
    """Builds the header string for the console."""
    if not ordered_chosen_columns:
        return ""

    header_parts = []
    # Indicative maps for column widths (adjust as needed)
    widths = {
        'Timestamp': 23, 'Current (mA)': 12, 'Avg Current (mA)': 16, 'Voltage (mV)': 12,
        'Power (W)': 11, 'Capacity (%)': 10, 'Battery Temp (°C)': 15,
        'ΔCurrent (mA)': 14, 'ΔAvg Current (mA)': 18, 'ΔVoltage (mV)': 14, 'ΔPower (W)': 12,
        'CPU Total (%)': 11, 'CPU User (%)': 10, 'CPU System (%)': 12, 'CPU Nice (%)': 10,
        'CPU Idle (%)': 10, 'CPU Iowait (%)': 12, 'CPU Irq (%)': 9, 'CPU Sirq (%)': 10,
        #'CPU Host (%)': 10,
        'Memory Total (MB)': 15, 'Memory Used (MB)': 14, 'Memory Free (MB)': 14,
        'Memory Available (MB)': 18, 'Memory Buffers (MB)': 16, 'Memory Cached (MB)': 15,
        'Swap Total (MB)': 13, 'Swap Used (MB)': 12,
        # Default width for thermal sensors (adjustable)
        'DEFAULT_THERMAL': 18
    }

    for col_name in ordered_chosen_columns:
         # Determine width: use specific if exists, otherwise default
         # Base default on name length if longer than default thermal width
         default_w = widths['DEFAULT_THERMAL'] if len(col_name) < widths['DEFAULT_THERMAL'] - 2 else len(col_name) + 2
         width = widths.get(col_name, default_w)
         header_parts.append(f"{col_name:<{width}} | ") # Left-aligned header

    return "".join(header_parts)[:-3] # Remove trailing " | "

def format_value_for_display(value, col_name):
    """Formats a value for console display (Right-aligned)."""
    # Indicative maps for decimal precision
    precision_map = {
        'Current (mA)': 1, 'Avg Current (mA)': 1, 'Voltage (mV)': 1,
        'Power (W)': 3, 'Battery Temp (°C)': 1,
        'ΔCurrent (mA)': 1, 'ΔAvg Current (mA)': 1, 'ΔVoltage (mV)': 1, 'ΔPower (W)': 3,
        'Memory Total (MB)': 0, 'Memory Used (MB)': 0, 'Memory Free (MB)': 0,
        'Memory Available (MB)': 0, 'Memory Buffers (MB)': 0, 'Memory Cached (MB)': 0,
        'Swap Total (MB)': 0, 'Swap Used (MB)': 0,
        'CPU': 1, # Default for all CPU fields
        'DEFAULT_THERMAL': 1
    }
    # Widths (must match build_display_header)
    widths = {
        'Timestamp': 23, 'Current (mA)': 12, 'Avg Current (mA)': 16, 'Voltage (mV)': 12,
        'Power (W)': 11, 'Capacity (%)': 10, 'Battery Temp (°C)': 15,
        'ΔCurrent (mA)': 14, 'ΔAvg Current (mA)': 18, 'ΔVoltage (mV)': 14, 'ΔPower (W)': 12,
        'CPU Total (%)': 11, 'CPU User (%)': 10, 'CPU System (%)': 12, 'CPU Nice (%)': 10,
        'CPU Idle (%)': 10, 'CPU Iowait (%)': 12, 'CPU Irq (%)': 9, 'CPU Sirq (%)': 10,
        #'CPU Host (%)': 10,
        'Memory Total (MB)': 15, 'Memory Used (MB)': 14, 'Memory Free (MB)': 14,
        'Memory Available (MB)': 18, 'Memory Buffers (MB)': 16, 'Memory Cached (MB)': 15,
        'Swap Total (MB)': 13, 'Swap Used (MB)': 12,
        'DEFAULT_THERMAL': 18
    }
    default_w = widths['DEFAULT_THERMAL'] if len(col_name) < widths['DEFAULT_THERMAL'] - 2 else len(col_name) + 2
    width = widths.get(col_name, default_w)

    # Handle N/A or None
    if value is None or value == 'N/A':
        return f"{'N/A':>{width}}"

    # Specific formatting
    formatted_str = "ERR" # Default in case of unexpected error
    try:
        if col_name == 'Timestamp':
             return f"{str(value):<{width}}" # Timestamp left-aligned

        is_delta = col_name.startswith('Δ')
        prec = 0 # Default precision 0

        # Find correct precision
        if col_name in precision_map:
            prec = precision_map[col_name]
        elif 'CPU' in col_name and '(%)' in col_name:
             prec = precision_map['CPU']
        elif 'Memory' in col_name and '(MB)' in col_name:
             prec = precision_map.get(col_name, 0) # Use specific if exists, else 0 for MB
        elif isinstance(value, float): # Heuristic for thermal sensors or unmapped floats
             prec = precision_map['DEFAULT_THERMAL']

        # Apply formatting
        if isinstance(value, (int, float)):
             # Python's default float formatting handles precision well
             sign = '+' if is_delta and float(value) > 0 else ''
             formatted_str = f"{sign}{value:.{prec}f}"
        else: # Strings (e.g., Capacity with %)
             formatted_str = str(value)

    except (ValueError, TypeError, Exception) as e:
         print(f"Warning: Error formatting value '{value}' for column '{col_name}': {e}", file=sys.stderr)
         formatted_str = "FMT_ERR"

    # Right-align and pad
    return f"{formatted_str:>{width}}"


def collect_data(thermal_sensor_names, previous_proc_stat):
    """Collects all enabled data from the device (Improved error handling)."""
    data = {'Timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]} # Milliseconds
    current_proc_stat = previous_proc_stat # Keep track of the latest proc stat data

    # --- Battery ---
    current_now_str = get_battery_value("current_now")
    current_avg_str = get_battery_value("current_avg") # Might not exist
    voltage_now_str = get_battery_value("voltage_now")
    capacity_str = get_battery_value("capacity")
    temp_celsius = get_battery_temperature() # Already handles internal errors

    data['Battery Temp (°C)'] = temp_celsius # Assign directly, can be None

    # Convert individually to isolate errors
    current_ua = None
    current_avg_ua = None
    voltage_uv = None
    capacity_percent = None

    try:
        if current_now_str is not None: current_ua = int(current_now_str)
    except (ValueError, TypeError): print(f"Warning: Invalid 'current_now' value: {current_now_str}", file=sys.stderr)

    try:
        # Treat '0' from current_avg as potentially valid (some devices report 0 when idle)
        if current_avg_str is not None: current_avg_ua = int(current_avg_str)
        # else: current_avg_ua = None # Let it be None if file doesn't exist
    except (ValueError, TypeError): print(f"Warning: Invalid 'current_avg' value: {current_avg_str}", file=sys.stderr)

    try:
        if voltage_now_str is not None: voltage_uv = int(voltage_now_str)
    except (ValueError, TypeError): print(f"Warning: Invalid 'voltage_now' value: {voltage_now_str}", file=sys.stderr)

    try:
        if capacity_str is not None: capacity_percent = int(capacity_str)
    except (ValueError, TypeError): print(f"Warning: Invalid 'capacity' value: {capacity_str}", file=sys.stderr)

    # Assign converted values or None
    data['Current (mA)'] = current_ua / 1000.0 if current_ua is not None else None
    data['Avg Current (mA)'] = current_avg_ua / 1000.0 if current_avg_ua is not None else None
    data['Voltage (mV)'] = voltage_uv / 1000.0 if voltage_uv is not None else None
    data['Capacity (%)'] = f"{capacity_percent}%" if capacity_percent is not None else None # Add % for display

    # Calculate Power
    if data['Voltage (mV)'] is not None and data['Current (mA)'] is not None:
        try:
            # Power (W) = Voltage (V) * Current (A)
            power_w = (data['Voltage (mV)'] / 1000.0) * (data['Current (mA)'] / 1000.0)
            # Handle negative current (charging) - power should still be calculated based on magnitudes?
            # Or should power be negative during charging? Conventionally, power consumption is positive.
            # Let's keep it as calculated for now.
            data['Power (W)'] = power_w
        except TypeError: data['Power (W)'] = None
    else: data['Power (W)'] = None


    # --- CPU (if enabled) ---
    if ENABLE_CPU_MONITORING:
        # Pass the previous stat data, get back percentages and the new stat data
        cpu_percentages, current_proc_stat = get_cpu_usage(previous_proc_stat)
        if cpu_percentages:
            # Map the keys from cpu_percentages to the standard column names
            data['CPU Total (%)'] = cpu_percentages.get('total', 'N/A')
            data['CPU User (%)'] = cpu_percentages.get('user', 'N/A')
            data['CPU System (%)'] = cpu_percentages.get('system', 'N/A')
            data['CPU Nice (%)'] = cpu_percentages.get('nice', 'N/A')
            data['CPU Idle (%)'] = cpu_percentages.get('idle', 'N/A')
            data['CPU Iowait (%)'] = cpu_percentages.get('iowait', 'N/A')
            data['CPU Irq (%)'] = cpu_percentages.get('irq', 'N/A')
            data['CPU Sirq (%)'] = cpu_percentages.get('sirq', 'N/A') # Already mapped in get_cpu_usage
            #data['CPU Host (%)'] = cpu_percentages.get('host', 'N/A') # Already mapped in get_cpu_usage
        else: # Error during CPU retrieval
             for key in ['CPU Total (%)', 'CPU User (%)','CPU System (%)', 'CPU Nice (%)', 'CPU Idle (%)', 'CPU Iowait (%)', 'CPU Irq (%)', 'CPU Sirq (%)', 'CPU Host (%)']:
                 data[key] = 'N/A'


    # --- Memory (if enabled) ---
    if ENABLE_MEMORY_MONITORING:
        memory_data = get_memory_usage() # Returns dict (with N/A on failure)
        data['Memory Total (MB)'] = memory_data.get('total_mb', 'N/A')
        data['Memory Used (MB)'] = memory_data.get('used_mb', 'N/A')
        data['Memory Free (MB)'] = memory_data.get('free_mb', 'N/A')
        data['Memory Available (MB)'] = memory_data.get('available_mb', 'N/A')
        data['Memory Buffers (MB)'] = memory_data.get('buffers_mb', 'N/A')
        data['Memory Cached (MB)'] = memory_data.get('cached_mb', 'N/A')
        data['Swap Total (MB)'] = memory_data.get('swap_total_mb', 'N/A')
        data['Swap Used (MB)'] = memory_data.get('swap_used_mb', 'N/A')


    # --- Thermal Sensors (if enabled) ---
    if ENABLE_THERMAL_SENSORS:
        thermal_output = get_temperature_data()
        thermal_readings = parse_temperature_output(thermal_output)
        for sensor_name in thermal_sensor_names:
            # Use get() which returns None if sensor_name is not in thermal_readings
            data[sensor_name] = thermal_readings.get(sensor_name)

    # Return the collected data and the current proc_stat for the next iteration
    return data, current_proc_stat


def calculate_deltas(current_data, previous_data):
    """Calculates differences from previous data (only if numeric)."""
    deltas = {}
    # Initialize delta keys to None if deltas are enabled, ensures columns exist
    if ENABLE_DELTA_COLUMNS:
        for delta_key in ['ΔCurrent (mA)', 'ΔAvg Current (mA)', 'ΔVoltage (mV)', 'ΔPower (W)']:
            deltas[delta_key] = None

    if not previous_data or not ENABLE_DELTA_COLUMNS:
        return deltas # Return initialized Nones if first iteration or disabled

    for key, delta_key in [('Current (mA)', 'ΔCurrent (mA)'),
                           ('Avg Current (mA)', 'ΔAvg Current (mA)'),
                           ('Voltage (mV)', 'ΔVoltage (mV)'),
                           ('Power (W)', 'ΔPower (W)')]:
        current_val = current_data.get(key)
        previous_val = previous_data.get(key)

        # Check if both values are numeric (int or float)
        if isinstance(current_val, (int, float)) and isinstance(previous_val, (int, float)):
            try:
                 delta_val = float(current_val) - float(previous_val)
                 deltas[delta_key] = delta_val
            except (ValueError, TypeError):
                 deltas[delta_key] = None # Error during calculation
        # else: deltas[delta_key] = None # Already initialized to None

    return deltas


def print_data_to_console(data_snapshot, ordered_chosen_display_columns):
    """Prints the selected data to the console."""
    if not ordered_chosen_display_columns: return

    output_parts = []
    for col_name in ordered_chosen_display_columns:
        value = data_snapshot.get(col_name) # Use get() for safety
        formatted_value = format_value_for_display(value, col_name)
        output_parts.append(formatted_value + " | ")

    print("".join(output_parts).rstrip(" | ")) # Remove trailing separator


def log_data_to_csv(csv_writer, data_snapshot, csv_header_order):
    """Writes a row of data to the CSV file in the specified order."""
    if not csv_writer or not ENABLE_LOGGING: return

    csv_row = []
    for col_name in csv_header_order:
        value = data_snapshot.get(col_name)

        if value is None or value == 'N/A':
            csv_row.append("N/A")
        elif isinstance(value, float):
            # Determine precision for CSV (can be different from display)
            prec = 3 if 'Power' in col_name else \
                   1 if 'Temp' in col_name or 'CPU' in col_name else \
                   0 if 'Memory' in col_name and '(MB)' in col_name else \
                   1 # Default for others (delta mA/mV, thermal)
            try:
                # Format float without unnecessary trailing zeros if possible
                # E.g. use general format 'g' or check if it's an integer
                if value == int(value) and prec == 0 :
                     csv_row.append(str(int(value)))
                else:
                     csv_row.append(f"{value:.{prec}f}")
            except (ValueError, TypeError):
                 csv_row.append(str(value)) # Fallback to string
        elif isinstance(value, str) and '%' in value:
            csv_row.append(value.replace('%','')) # Remove % for CSV
        else:
            csv_row.append(str(value))

    try:
        csv_writer.writerow(csv_row)
    except Exception as e:
        print(f"\nError while writing to CSV: {e}", file=sys.stderr)


# --- Main Flow ---

if __name__ == "__main__":
    print("-" * 80)
    print("Device Monitoring Script (Battery, Thermal, CPU, Memory)")
    print("    Column Selection for Display / Full CSV Logging")
    print(f"    Using ADB: {ADB_PATH}")
    print("-" * 80)

    # --- Initial ADB Checks ---
    print("Checking ADB connection...")
    # Use run_adb_command which now includes the PATH check logic
    devices_output = run_adb_command(["devices"])
    if not devices_output or "List of devices attached" not in devices_output:
         print("\nError: Could not get ADB device list.", file=sys.stderr)
         print("Ensure ADB is working correctly and the daemon is running.")
         sys.exit(1)

    device_lines = devices_output.strip().splitlines()
    if len(device_lines) < 2:
         print("\nError: No ADB devices found.", file=sys.stderr)
         print("Ensure a device is connected, authorized, and USB debugging is enabled.")
         sys.exit(1)

    found_device = False
    active_serial = None
    for line in device_lines[1:]:
        parts = line.split()
        if len(parts) >= 2: # Handle potential extra info after state
             serial, state = parts[0], parts[1]
             if state == "device":
                 print(f"Found active device: {serial}")
                 active_serial = serial
                 found_device = True
                 # Don't break, check for multiple active devices (user should ideally only have one for this script)
                 if len(device_lines) > 2:
                     print("Warning: Multiple devices detected. Using the first active one found.", file=sys.stderr)
                 break # Use the first active device
             elif state == "unauthorized":
                 print(f"\nError: Device {serial} is unauthorized.", file=sys.stderr)
                 print("Please accept the RSA authorization request on your device.")
                 sys.exit(1)
             elif state == "offline":
                 print(f"\nError: Device {serial} is offline.", file=sys.stderr)
                 print("Try reconnecting the device, restarting ADB (adb kill-server; adb start-server), or restarting the device.")
                 sys.exit(1)
             else:
                 print(f"Found device {serial} with unknown state: {state}")

    if not found_device:
         print("\nError: No active (state='device') ADB device found.")
         sys.exit(1)
    print("ADB check passed.")


    # --- Determine Columns and User Choice ---
    # Fetch all potential column names based on enabled features
    all_possible_columns_for_csv, thermal_names = get_all_available_columns(
        ENABLE_THERMAL_SENSORS, ENABLE_CPU_MONITORING, ENABLE_MEMORY_MONITORING, ENABLE_DELTA_COLUMNS
    )

    # Prompt user for columns to display, using the configured default
    chosen_display_columns_ordered = prompt_user_for_display_columns(all_possible_columns_for_csv, COLUMN_SELECTION_DEFAULT)

    # --- Prepare CSV Logging ---
    csv_file = None
    csv_writer = None
    csv_filename = ""
    if ENABLE_LOGGING:
        # Use the confirmed active serial if possible, otherwise fallback
        device_serial = active_serial if active_serial else get_device_serial()
        device_model = get_device_model()
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        sanitized_model = sanitize_filename(device_model)
        sanitized_serial = sanitize_filename(device_serial)
        csv_filename = f"log_{sanitized_model}_{sanitized_serial}_{timestamp_str}.csv"

        try:
            # Use 'w' mode to create/overwrite the file
            csv_file = open(csv_filename, 'w', newline='', encoding='utf-8')
            csv_writer = csv.writer(csv_file)
            # CSV header always uses ALL potentially available columns for consistency
            csv_writer.writerow(all_possible_columns_for_csv)
            csv_file.flush() # Ensure header is written immediately
            print(f"\nCSV Logging enabled. Data will be saved to: {csv_filename}")
        except IOError as e:
            print(f"\nError: Could not open or write to CSV file '{csv_filename}': {e}", file=sys.stderr)
            ENABLE_LOGGING = False # Disable logging if file cannot be opened
            csv_file = None
            csv_writer = None

    # --- Print Console Header ---
    # Display header uses only the columns chosen by the user
    display_header = build_display_header(chosen_display_columns_ordered)
    print("\n" + "=" * (len(display_header) if display_header else 80))
    if display_header:
        print(display_header)
        print("-" * len(display_header))
    else:
        print("No columns selected for display.")
        if not ENABLE_LOGGING:
            print("WARNING: CSV Logging is disabled AND no columns selected for display. Script will run but produce no output.")


    # --- Monitoring Loop ---
    previous_data_snapshot = None
    # Initialize previous_proc_stat for the first CPU calculation
    previous_proc_stat_data = None
    if ENABLE_CPU_MONITORING:
         print("Performing initial read for CPU baseline...")
         # Do an initial read just to populate previous_proc_stat_data
         # We ignore the percentages calculated here as the delta is undefined
         _, initial_proc_stat_data = get_cpu_usage(None)
         if initial_proc_stat_data:
             previous_proc_stat_data = initial_proc_stat_data
             print("CPU baseline captured.")
         else:
             print("Warning: Could not get initial CPU baseline. CPU% may be inaccurate on first reading.", file=sys.stderr)


    print(f"\nStarting monitoring... Interval: {T_sleep}s. Press Ctrl+C to stop.")

    try:
        while True:
            start_time = time.monotonic()

            # 1. Collect all data (pass previous CPU state)
            current_data_snapshot, current_proc_stat_data = collect_data(
                thermal_names,
                previous_proc_stat_data if ENABLE_CPU_MONITORING else None
            )

            # 2. Calculate Deltas (if enabled)
            deltas = calculate_deltas(current_data_snapshot, previous_data_snapshot)
            current_data_snapshot.update(deltas) # Add delta values to the snapshot

            # 3. Print to console
            print_data_to_console(current_data_snapshot, chosen_display_columns_ordered)

            # 4. Log to CSV
            if ENABLE_LOGGING and csv_writer:
                # Log the complete snapshot using the full header order
                log_data_to_csv(csv_writer, current_data_snapshot, all_possible_columns_for_csv)
                if csv_file: csv_file.flush() # Ensure data is written periodically

            # 5. Save current data for next iteration's delta calculation
            previous_data_snapshot = current_data_snapshot
            if ENABLE_CPU_MONITORING:
                 previous_proc_stat_data = current_proc_stat_data # Update CPU state

            # 6. Wait
            end_time = time.monotonic()
            elapsed_time = end_time - start_time
            sleep_duration = T_sleep - elapsed_time
            if sleep_duration > 0:
                time.sleep(sleep_duration)
            # else: print(f"Warning: Loop took longer ({elapsed_time:.3f}s) than T_sleep ({T_sleep}s)", file=sys.stderr)


    except KeyboardInterrupt:
        print("\n\nUser interrupt requested (Ctrl+C). Shutting down...")
    except Exception as e:
        print(f"\nCritical error in main loop: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
    finally:
        # --- Cleanup ---
        if csv_file:
            try:
                csv_file.close()
                print(f"CSV file '{csv_filename}' closed.")
            except Exception as e:
                print(f"Error closing CSV file: {e}", file=sys.stderr)
        print("Script finished.")
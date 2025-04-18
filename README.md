
*   **`install.py`**: This Python script is designed to help you set up the necessary tools to run the battery monitoring script.  It likely automates the download and installation of Android platform-tools (specifically ADB - Android Debug Bridge), which is required for communication with your Android device. Refer to the script's documentation (if available within the script itself) or the main `README.md` for specific instructions on how to use `install.py`.
*   **`run_power_logger.py`**: This is the main Python script for monitoring your Android device's battery in real-time. When executed, it will:
    *   Connect to your Android device using ADB.
    *   Read battery properties (like current, voltage, capacity) from your device.
    *   Calculate power consumption.
    *   Display the battery data in your terminal.
    *   Optionally log the data to `battery_data.csv` if logging is enabled within the script.

    This script is essentially the `run_power_logger.py` script discussed previously, likely renamed to `run_power_logger.py` for clarity.

## Getting Started

1.  **Installation:** Run the `install.py` script to ensure you have ADB set up correctly. Follow the instructions provided by the `install.py` script.
2.  **Usage:** After installation, run the `run_power_logger.py` script to start monitoring your Android device's battery. Make sure your Android device is connected via USB with USB Debugging enabled and authorized.
3.  **Monitoring:** Observe the real-time battery data output in your terminal.
4.  **Data Logging (Optional):** If logging is enabled in `run_power_logger.py`, check the `battery_data.csv` file in the same directory for the recorded battery data.

For detailed instructions on running the scripts, refer to the main `README.md` file (this file) or the documentation within the scripts themselves.

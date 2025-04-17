# Platform-tools Downloader Script

## Description

This Python script automates the download of Android platform-tools (ADB and Fastboot) from Google's official repository. It detects your operating system (Windows, Linux, or macOS), downloads the appropriate platform-tools zip file, extracts the `adb` executable to the same directory where the script is run, and then cleans up the downloaded zip file and the extracted platform-tools directory.

## Prerequisites

*   **Python 3.x** installed on your system.
*   **Internet connection** to download platform-tools.

## How to Use

1.  **Save the script:** Save the Python code (e.g., the provided `download_adb.py` file) to a directory on your computer.
2.  **Open a terminal or command prompt:** Navigate to the directory where you saved the script using your terminal or command prompt.
3.  **Run the script:** Execute the script using the Python interpreter:
    ```bash
    python download_adb.py
    ```
4.  **Follow the prompts:** The script will print messages to the console indicating the download progress, extraction, and cleanup steps.
5.  **ADB is ready:** After successful execution, you will find the `adb` executable (`adb` on Linux/macOS, `adb.exe` on Windows) in the same directory as the script.

## Important Notes

*   **Executable Permissions (Linux/macOS):** The script automatically sets executable permissions for `adb` and `fastboot` on Linux and macOS systems.
*   **PATH Environment Variable:** For easier access to `adb` from any terminal location, you should add the directory where you ran the script (and where `adb` is now located) to your system's `PATH` environment variable. Instructions for doing this vary depending on your operating system. Search online for "how to add to PATH environment variable on [your OS name]".
*   **Clean Installation:** The script removes any existing `platform-tools` directory and any `adb` executable in the script's directory before downloading and extracting, ensuring a fresh installation each time you run it.
*   **macOS Double Directory Issue:** This script is designed to handle a potential issue on macOS where the extracted platform-tools are placed in a nested `platform-tools/platform-tools` directory.

## Output

Upon successful execution, the script will:

*   Download the platform-tools zip file for your operating system.
*   Extract the contents of the zip file.
*   Move the `adb` executable to the same directory where you ran the script.
*   Remove the downloaded zip file (`platform-tools.zip`).
*   Remove the temporary `platform-tools` directory.
*   Print a success message indicating that `adb` is ready to use in the current directory.

If any errors occur during the process (download, extraction, permissions, etc.), the script will print error messages to the console.

---

**Example Success Output in Terminal:**

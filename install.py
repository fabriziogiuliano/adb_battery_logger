import platform
import urllib.request
import zipfile
import os
import shutil  # For removing directories

def get_os_platform():
    """Detects the current operating system."""
    system = platform.system()
    if system == "Windows":
        return "windows"
    elif system == "Linux":
        return "linux"
    elif system == "Darwin":  # Darwin is macOS
        return "mac"
    else:
        return None

def get_download_url(os_platform):
    """Returns the download URL for platform-tools based on OS."""
    urls = {
        "windows": "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
        "linux": "https://dl.google.com/android/repository/platform-tools-latest-linux.zip",
        "mac": "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip"
    }
    return urls.get(os_platform)

def download_platform_tools(download_url, zip_filename="platform-tools.zip"):
    """Downloads platform-tools zip file from the given URL."""
    try:
        print(f"Downloading platform-tools from: {download_url}")
        urllib.request.urlretrieve(download_url, zip_filename)
        print(f"Download complete: {zip_filename}")
        return True
    except urllib.error.URLError as e:
        print(f"Error downloading platform-tools: {e}")
        return False

def extract_platform_tools(zip_filename="platform-tools.zip", extract_dir="platform-tools"):
    """Extracts platform-tools zip file to the specified directory."""
    try:
        print(f"Extracting {zip_filename} to {extract_dir}")
        with zipfile.ZipFile(zip_filename, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        print(f"Extraction complete to: {extract_dir}")
        return True
    except zipfile.BadZipFile:
        print(f"Error: {zip_filename} is not a valid zip file or is corrupted.")
        return False
    except Exception as e:
        print(f"Error extracting platform-tools: {e}")
        return False

def set_executable_permission(platform_tools_dir="platform-tools", os_platform=None):
    """Sets executable permission for adb and other tools on Linux/macOS."""
    if os_platform in ["linux", "mac"]:
        # Corrected path to account for double platform-tools directory
        adb_path = os.path.join(platform_tools_dir, platform_tools_dir, "adb")
        fastboot_path = os.path.join(platform_tools_dir, platform_tools_dir, "fastboot")
        if not os.path.exists(adb_path): # Check if the path actually exists before trying to chmod
            print(f"Warning: ADB not found at expected path: {adb_path}.  Extraction might have failed or path is incorrect.")
            return False
        if not os.path.exists(fastboot_path): # Check if the path actually exists before trying to chmod
            print(f"Warning: Fastboot not found at expected path: {fastboot_path}. Extraction might have failed or path is incorrect.")
            return False
        try:
            os.chmod(adb_path, 0o755)  # rwxr-xr-x for adb
            os.chmod(fastboot_path, 0o755) # rwxr-xr-x for fastboot
            print(f"Set executable permissions for adb and fastboot in {platform_tools_dir}")
            return True
        except OSError as e:
            print(f"Error setting executable permissions: {e}")
            return False
    elif os_platform == "windows":
        print("Executable permissions not needed on Windows.")
        return True
    else:
        return False # Platform not recognized

def cleanup_zip(zip_filename="platform-tools.zip"):
    """Removes the downloaded zip file."""
    try:
        os.remove(zip_filename)
        print(f"Removed temporary zip file: {zip_filename}")
        return True
    except FileNotFoundError:
        print(f"Warning: Zip file {zip_filename} not found, cannot cleanup.")
        return False
    except OSError as e:
        print(f"Error cleaning up zip file: {e}")
        return False

def check_adb_exists(adb_path): # Modified to take adb_path directly
    """Checks if adb exists at the given path."""
    os_platform = get_os_platform() # Determine os_platform inside the function if needed
    if os.path.exists(adb_path) and os.access(adb_path, os.X_OK if os_platform in ["linux", "mac"] else os.R_OK):
        print(f"ADB found at: {adb_path}")
        return True
    else:
        print(f"Error: ADB not found at expected path: {adb_path}")
        return False

def remove_platform_tools_dir(platform_tools_dir="platform-tools"):
    """Removes the platform-tools directory if it exists."""
    if os.path.exists(platform_tools_dir):
        try:
            shutil.rmtree(platform_tools_dir)
            print(f"Removed platform-tools directory: {platform_tools_dir}")
            return True
        except OSError as e:
            print(f"Error removing directory {platform_tools_dir}: {e}")
            return False
    else:
        return True # Directory doesn't exist, nothing to remove

def move_adb_to_root(platform_tools_dir="platform-tools", os_platform=None):
    """Moves adb executable to the root directory and cleans up platform-tools."""
    if not os_platform:
        os_platform = get_os_platform()
    adb_executable = "adb.exe" if os_platform == "windows" else "adb"
    # Corrected source path to account for double platform-tools directory
    source_adb_path = os.path.join(platform_tools_dir, platform_tools_dir, adb_executable)
    dest_adb_path = os.path.join(".", adb_executable) # Root directory

    try:
        if os.path.exists(source_adb_path):
            shutil.move(source_adb_path, dest_adb_path)
            print(f"Moved ADB from '{source_adb_path}' to '{dest_adb_path}'")
            return True
        else:
            print(f"Error: ADB not found at source path: {source_adb_path}")
            return False
    except FileNotFoundError:
        print(f"Error: ADB source file not found: {source_adb_path}")
        return False
    except OSError as e:
        print(f"Error moving ADB file: {e}")
        return False

if __name__ == "__main__":
    print("-" * 40)
    print("Platform-tools Downloader Script")
    print("-" * 40)

    current_os = get_os_platform()
    if not current_os:
        print("Operating system not recognized (Windows, Linux, macOS supported).")
    else:
        print(f"Detected operating system: {current_os.capitalize()}")
        download_url = get_download_url(current_os)
        if not download_url:
            print(f"No platform-tools download URL found for {current_os}.")
        else:
            zip_file = "platform-tools.zip"
            extract_directory = "platform-tools"

            # Remove any existing platform-tools directory and adb in root
            remove_platform_tools_dir(extract_directory)
            adb_executable = "adb.exe" if current_os == "windows" else "adb"
            root_adb_path = os.path.join(".", adb_executable)
            if os.path.exists(root_adb_path):
                try:
                    os.remove(root_adb_path)
                    print(f"Removed existing ADB file in root directory: {root_adb_path}")
                except OSError as e:
                    print(f"Error removing existing ADB in root: {e}")


            if download_platform_tools(download_url, zip_file):
                if extract_platform_tools(zip_file, extract_directory):
                    if set_executable_permission(extract_directory, current_os):
                        if move_adb_to_root(extract_directory, current_os): # Move adb to root
                            remove_platform_tools_dir(extract_directory) # Remove platform-tools directory
                            root_adb_path = os.path.join(".", adb_executable)
                            if check_adb_exists(root_adb_path): # Check adb in root
                                cleanup_zip(zip_file)
                                print("-" * 40)
                                print(f"ADB successfully downloaded and moved to the script's directory.")
                                print(f"Platform-tools directory and zip file have been removed.")
                                print(f"You can now use ADB from this directory.")
                                print("Make sure to add this directory to your system's PATH environment variable for easier access.")
                                print("-" * 40)
                            else:
                                print("Platform-tools download, extraction, and ADB move successful, but ADB not found in root directory.")
                        else:
                            print("Platform-tools download, extraction, and executable permissions set, but moving ADB to root failed.")
                    else:
                        print("Platform-tools download and extraction successful, but setting executable permissions failed (Linux/macOS).")
                else:
                    print("Platform-tools download successful, but extraction failed.")
            else:
                print("Platform-tools download failed.")


    print("Script finished.")
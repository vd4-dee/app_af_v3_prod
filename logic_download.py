# filename: logic_download.py
import os
import time
import csv
import traceback
import functools
import zipfile # Needed for extract_zip_files
from datetime import datetime, timedelta

import pyotp # type: ignore
# import requests # Removed if not used directly for downloads
# from requests.adapters import HTTPAdapter # Removed
# from urllib3.util.retry import Retry # Removed
# from urllib3.exceptions import ReadTimeoutError, MaxRetryError # Removed
# import urllib3 # Removed
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.remote_connection import RemoteConnection # For setting command timeout
from selenium.common.exceptions import (
    WebDriverException, TimeoutException, NoSuchElementException,
    ElementClickInterceptedException, ElementNotInteractableException,
    UnexpectedAlertPresentException, NoAlertPresentException,
    StaleElementReferenceException # Added for handling stale elements
)
# Use webdriver_manager only if driver_path in config is not set or invalid
# from webdriver_manager.chrome import ChromeDriverManager # type: ignore

# --- Constants ---
# Increased timeouts (in seconds)
SELENIUM_COMMAND_TIMEOUT = 3600 # Increased from default (usually 60s) for Selenium commands
WEBDRIVER_WAIT_TIMEOUT = 3600   # Increased timeout for explicit waits (WebDriverWait)
PAGE_LOAD_TIMEOUT = 3600        # Increased timeout for page loads
DOWNLOAD_WAIT_TIMEOUT = 3600   # Max time to wait for a single file download (15 min)
RETRY_DELAY = 10               # Default delay between retries for operations
CLICK_RETRY_DELAY = 15         # Longer delay specifically for click retries
MAX_RETRIES = 3                # Default number of retries for operations prone to failure
SHORT_WAIT = 2                 # Short pause time in seconds

# --- Region Data (Keep as defined) ---
regions_data = {
    0: {"name": "HCM", "xpath": "/html/body/form/div[1]/div/div/ul/li/span[3]/div/ul/li/ul/li[1]/div/span[3]"},
    1: {"name": "HNi", "xpath": "/html/body/form/div[1]/div/div/ul/li/span[3]/div/ul/li/ul/li[2]/div/span[3]"},
    2: {"name": "Mdong", "xpath": "/html/body/form/div[1]/div/div/ul/li/span[3]/div/ul/li/ul/li[3]/div/span[3]"},
    3: {"name": "Mtay", "xpath": "/html/body/form/div[1]/div/div/ul/li/span[3]/div/ul/li/ul/li[4]/div/span[3]"},
    4: {"name": "MB2", "xpath": "/html/body/form/div[1]/div/div/ul/li/span[3]/div/ul/li/ul/li[5]/div/span[3]"},
    5: {"name": "Mtrung", "xpath": "/html/body/form/div[1]/div/div/ul/li/span[3]/div/ul/li/ul/li[6]/div/span[3]"},
    6: {"name": "MB1", "xpath": "/html/body/form/div[1]/div/div/ul/li/span[3]/div/ul/li/ul/li[7]/div/span[3]"}
}

# --- Global Path Definitions ---
current_folder = os.path.dirname(os.path.abspath(__file__))
csv_filename = os.path.join(current_folder, 'download_log.csv') # Default log name

# --- Custom Exception Class ---
# Moved definition UP so it's known before being used in decorators
class DownloadFailedException(Exception):
    """Custom exception for download failures after retries or specific errors."""
    pass

# --- Helper Functions ---
def format_date_ddmmyyyy(date_str):
    """ Formats date string from 'YYYY-MM-DD' to 'DD/MM/YYYY'. """
    try:
        if isinstance(date_str, datetime):
             return date_str.strftime('%d/%m/%Y')
        elif isinstance(date_str, str) and date_str:
             dt_obj = datetime.strptime(date_str, '%Y-%m-%d')
             return dt_obj.strftime('%d/%m/%Y')
        else:
            # Handle None or empty string gracefully
            print(f"Warning: Received invalid date input '{date_str}' for formatting.")
            return "" # Or raise error? Returning empty string might be safer for send_keys
    except (ValueError, TypeError) as e:
        print(f"Warning: Could not format date '{date_str}' to DD/MM/YYYY: {e}. Returning original.")
        return str(date_str) # Return original string representation on error

def retry_on_exception(exceptions=(WebDriverException,), retries=MAX_RETRIES, delay=RETRY_DELAY, backoff=1.5):
    """
    Decorator to retry a function on specific Selenium exceptions with exponential backoff.
    Catches WebDriverException by default.
    Now `DownloadFailedException` (if included in `exceptions`) is defined before this point.
    """
    if not isinstance(exceptions, tuple):
        exceptions = (exceptions,)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            status_callback = kwargs.get('status_callback')
            instance = args[0] if args and isinstance(args[0], WebAutomation) else None
            attempt = 0
            current_delay = delay
            last_exception = None

            while attempt < retries:
                attempt += 1
                try:
                    return func(*args, **kwargs)
                except exceptions as e: # This now correctly handles DownloadFailedException if passed
                    last_exception = e
                    is_recoverable_timeout = isinstance(e, WebDriverException) and \
                                             ('timed out' in str(e).lower() or 'connection refused' in str(e).lower())

                    if status_callback:
                        status_callback(f"WARNING: Attempt {attempt}/{retries} failed for {func.__name__} with {type(e).__name__}. Error: {str(e)[:150]}...")

                    if attempt >= retries:
                        if status_callback:
                            status_callback(f"ERROR: Max retries ({retries}) reached for {func.__name__}. Last error: {type(e).__name__}")
                        # Capture screenshot on final failure
                        if instance and hasattr(instance, 'capture_screenshot'):
                            instance.capture_screenshot(f"{func.__name__}_final_retry_fail")
                        raise last_exception from e
                    else:
                        if status_callback:
                             status_callback(f"Retrying in {current_delay:.2f}s...")
                        time.sleep(current_delay)
                        current_delay *= backoff

                        # Optional: Reconnect logic (use cautiously)
                        # if is_recoverable_timeout and instance and hasattr(instance, 'reconnect_if_needed'):
                        #     if status_callback: status_callback("Attempting WebDriver reconnect...")
                        #     instance.reconnect_if_needed(status_callback=status_callback)

                except Exception as e: # Catch any other unexpected error
                    if status_callback:
                        status_callback(f"FATAL UNEXPECTED ERROR in {func.__name__} (attempt {attempt}): {type(e).__name__} - {e}. Stopping retries.")
                    if instance and hasattr(instance, 'capture_screenshot'):
                         instance.capture_screenshot(f"{func.__name__}_unexpected_fail")
                    traceback.print_exc()
                    raise # Re-raise immediately

            # Should not be reached if retries > 0 and loop completes normally
            if last_exception:
                raise last_exception
            raise RuntimeError(f"{func.__name__} failed after {retries} attempts without specific exception capture.")

        return wrapper
    return decorator


class WebAutomation:
    """Handles browser automation using Selenium for downloading reports."""

    def __init__(self, driver_path, download_folder, status_callback=None):
        """
        Initializes the WebDriver.
        Args:
            driver_path (str): Path to ChromeDriver.
            download_folder (str): Specific folder for this run's downloads.
            status_callback (function, optional): Callback for status updates during init.
        """
        self.driver_path = driver_path
        self.download_folder = download_folder
        self.driver = None
        self.wait = None
        self.before_download = set()
        self.extracted_zips = set()  # Track extracted zip files to avoid re-extraction
        self._status_callback = status_callback # Store callback for internal use
        # Derive session identifier from download folder name
        # self.session_id = os.path.basename(self.download_folder)
        now = datetime.now()
        self.session_id = os.path.basename(self.download_folder) + "-" + now.strftime("%H%M%S")
        self._log(f"Session ID: {self.session_id}")

        try:
            RemoteConnection.set_timeout(SELENIUM_COMMAND_TIMEOUT)
            self._log(f"Set Selenium RemoteConnection command timeout to {SELENIUM_COMMAND_TIMEOUT}s.")
        except Exception as e:
             self._log(f"Warning: Could not set RemoteConnection timeout: {e}")

        chrome_options = webdriver.ChromeOptions()
        prefs = {
            'download.default_directory': self.download_folder,
            'download.prompt_for_download': False,
            'download.directory_upgrade': True,
            'plugins.always_open_pdf_externally': True,
            'safebrowsing.enabled': True, # Keep safety features enabled
            # 'profile.managed_default_content_settings.images': 2, # Uncomment to disable images
        }
        chrome_options.add_experimental_option('prefs', prefs)
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])

        # Stability arguments
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920x1080')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--enable-automation')
        chrome_options.add_argument('--dns-prefetch-disable')
        # chrome_options.add_argument('--headless=new') # Uncomment for headless operation

        try:
            if not os.path.exists(self.driver_path):
                self._log(f"Warning: ChromeDriver path '{self.driver_path}' not found.")
                # Option: Fallback to webdriver-manager (pip install webdriver-manager)
                # try:
                #     from webdriver_manager.chrome import ChromeDriverManager
                #     self._log("Attempting to use webdriver-manager...")
                #     self.service = Service(ChromeDriverManager().install())
                # except Exception as wdm_e:
                #     self._log(f"Error using webdriver-manager: {wdm_e}")
                #     raise RuntimeError(f"ChromeDriver not found at '{self.driver_path}' and webdriver-manager failed.") from wdm_e
                # else: # If manager succeeds
                #     self._log("webdriver-manager successfully installed/found ChromeDriver.")
                # --- End Option ---
                # Raise error if not using webdriver-manager or if it fails
                raise FileNotFoundError(f"ChromeDriver executable not found at the specified path: {self.driver_path}")
            else:
                self.service = Service(self.driver_path)

            self._log("Starting ChromeDriver service...")
            self.driver = webdriver.Chrome(
                service=self.service,
                options=chrome_options
            )
            self._log("WebDriver initialized.")
            try:
                self.driver.command_executor.set_timeout(SELENIUM_COMMAND_TIMEOUT)
                self._log(f"Set driver command executor timeout to {SELENIUM_COMMAND_TIMEOUT}s.")
            except Exception as e:
                self._log(f"Warning: Could not set driver command executor timeout: {e}")

            self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            self.driver.implicitly_wait(5) # Reduce implicit wait, rely on explicit waits
            self.wait = WebDriverWait(self.driver, WEBDRIVER_WAIT_TIMEOUT)

            self.update_files_before_download()

        except (WebDriverException, FileNotFoundError, RuntimeError) as e:
            self._log(f"FATAL: WebDriver initialization failed: {e}")
            traceback.print_exc()
            if hasattr(self, 'service') and self.service and self.service.process:
                self.service.stop()
            raise # Re-raise to stop the application

    def _log(self, message):
        """Internal logging helper using the status callback if available."""
        if self._status_callback:
            self._status_callback(message)
        else:
            print(message) # Fallback to console if no callback

    # --- Utility Methods ---

    def update_files_before_download(self):
        """Updates the set of files currently present in the download folder."""
        if os.path.exists(self.download_folder):
            try:
                self.before_download = set(os.listdir(self.download_folder))
                # self._log(f"[Debug] Files before download: {self.before_download}") # Debug log
            except OSError as e:
                 self._log(f"Error listing download directory {self.download_folder}: {e}")
                 self.before_download = set()
        else:
            self._log(f"Warning: Download directory {self.download_folder} does not exist yet.")
            self.before_download = set()

    def wait_for_download_to_finish(self, timeout=DOWNLOAD_WAIT_TIMEOUT, status_callback=None):
        """Waits for a new file download to complete."""
        log_func = status_callback or self._log
        log_func(f"Waiting for download to complete (timeout: {timeout}s)...")

        start_time = time.time()
        last_partial_file_info = {} # {filename: (size, timestamp)}

        while time.time() - start_time < timeout:
            current_files = set()
            try:
                if os.path.exists(self.download_folder):
                    current_files = set(os.listdir(self.download_folder))
                else:
                    log_func("Warning: Download folder disappeared during wait.")
                    time.sleep(SHORT_WAIT)
                    continue
            except OSError as e:
                log_func(f"Error accessing download folder during wait: {e}")
                time.sleep(SHORT_WAIT)
                continue

            new_files = current_files - self.before_download
            completed_files = [f for f in new_files if not f.lower().endswith(('.tmp', '.crdownload', '.part'))]
            partial_files = {f for f in new_files if f.lower().endswith(('.tmp', '.crdownload', '.part'))}

            # 1. Check completed files
            if completed_files:
                try:
                    completed_paths = [os.path.join(self.download_folder, f) for f in completed_files]
                    valid_files = [p for p in completed_paths if os.path.isfile(p)]
                    if valid_files:
                        newest_file_path = max(valid_files, key=os.path.getmtime)
                        new_file_name = os.path.basename(newest_file_path)
                        # Check file size is > 0 (simple check for validity)
                        if os.path.getsize(newest_file_path) > 0:
                            log_func(f"Detected completed file: {new_file_name}")
                            return new_file_name # Success
                        else:
                            log_func(f"Warning: Detected zero-byte completed file: {new_file_name}. Continuing wait.")
                    # Handle case where completed_files list only contained directories or non-files
                except (ValueError, OSError) as e:
                     log_func(f"Error identifying latest completed file: {e}")

            # 2. Monitor partial files for progress
            active_partials_found = False
            if partial_files:
                now = time.time()
                for partial_file in partial_files:
                    partial_file_path = os.path.join(self.download_folder, partial_file)
                    try:
                        current_size = os.path.getsize(partial_file_path)
                        last_size, last_time = last_partial_file_info.get(partial_file, (-1, 0))

                        if current_size > last_size:
                            # Log progress less frequently
                            if now - last_time > 10: # Log approx every 10 seconds
                                log_func(f"Download in progress ({partial_file}): {current_size} bytes...")
                            last_partial_file_info[partial_file] = (current_size, now)
                            active_partials_found = True
                            # Extend timeout slightly only if progress is recent
                            # start_time = time.time() # Risky, can lead to infinite loops

                        elif current_size == last_size:
                             # Size hasn't changed, could be stalled or done but not renamed.
                             # Consider it active for now.
                             active_partials_found = True
                             # If stalled for too long, maybe log a warning?
                             if now - last_time > 60: # E.g., stalled for 1 minute
                                 if (now - last_time) % 60 < SHORT_WAIT: # Log warning once per minute
                                     log_func(f"Warning: Download progress for '{partial_file}' seems stalled at {current_size} bytes.")

                        # else: size decreased? Ignore or log warning

                    except OSError: # File might have been renamed/deleted
                        if partial_file in last_partial_file_info:
                             del last_partial_file_info[partial_file]
                        continue

            # Cleanup info for partials that disappeared
            stale_partials = set(last_partial_file_info.keys()) - partial_files
            for stale in stale_partials:
                 del last_partial_file_info[stale]

            # If no completed files and no active partials, keep waiting but log if needed
            if not completed_files and not active_partials_found and partial_files:
                 # All partials seem stalled, just wait.
                 pass

            time.sleep(SHORT_WAIT)

        # --- Loop Timed Out ---
        log_func(f"WARNING: Download wait timed out after {timeout} seconds.")
        # Final check
        final_files = set(os.listdir(self.download_folder)) if os.path.exists(self.download_folder) else set()
        final_new_files = final_files - self.before_download
        final_completed = [f for f in final_new_files if not f.lower().endswith(('.tmp', '.crdownload', '.part'))]
        final_partial = [f for f in final_new_files if f.lower().endswith(('.tmp', '.crdownload', '.part'))]

        if final_completed:
            log_func(f"Timeout occurred, but found completed file(s) post-timeout: {final_completed}")
            try:
                final_paths = [os.path.join(self.download_folder, f) for f in final_completed]
                valid_files = [p for p in final_paths if os.path.isfile(p) and os.path.getsize(p) > 0]
                if valid_files:
                    newest_file_path = max(valid_files, key=os.path.getmtime)
                    return os.path.basename(newest_file_path) # Consider success if found post-timeout
                else:
                    log_func("No valid (non-empty) completed files found post-timeout.")
                    return None
            except Exception as e:
                log_func(f"Error getting newest file post-timeout: {e}")
                return None
        elif final_partial:
              log_func(f"Timeout occurred with file(s) still potentially downloading: {final_partial}")
              return None
        else:
              log_func("Timeout occurred and no new completed or partial files were detected.")
              return None

    def safe_click(self, locator, description="element", retries=MAX_RETRIES, delay=CLICK_RETRY_DELAY, status_callback=None):
        """Attempts to click an element safely using explicit waits and retries."""
        log_func = status_callback or self._log
        if not self.driver or not self.wait:
            log_func("ERROR: safe_click called but WebDriver not initialized.")
            return False

        last_exception = None
        for attempt in range(retries):
            try:
                # Wait for element to be clickable (includes presence, visibility, enabled)
                element = self.wait.until(EC.element_to_be_clickable(locator))

                # Scroll into view
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", element)
                    time.sleep(0.5) # Pause after scroll
                except Exception as scroll_err:
                     log_func(f"Warning: Could not scroll '{description}' into view: {scroll_err}")

                # Perform the click
                element.click()
                log_func(f"Clicked '{description}' successfully (Attempt {attempt+1}).")
                return True # Success

            except (ElementClickInterceptedException, ElementNotInteractableException) as e:
                last_exception = e
                error_type = type(e).__name__
                log_func(f"WARNING: Click attempt {attempt+1} for '{description}' failed ({error_type}). Element might be obscured or not ready.")
                # Try JS click fallback on the last attempt
                if attempt == retries - 1:
                     try:
                         log_func(f"Trying JavaScript click fallback for '{description}'...")
                         # Re-find element for JS click to ensure it's fresh
                         element_js = self.wait.until(EC.presence_of_element_located(locator))
                         self.driver.execute_script("arguments[0].click();", element_js)
                         log_func(f"JavaScript click successful for '{description}'.")
                         return True
                     except Exception as js_e:
                         log_func(f"JavaScript click fallback failed: {js_e}")
                         last_exception = js_e # Update last exception

            except StaleElementReferenceException as e:
                last_exception = e
                log_func(f"WARNING: StaleElementReferenceException on attempt {attempt+1} for '{description}'. Element changed. Retrying find & click...")
                # Retry logic will handle re-finding the element

            except (TimeoutException, NoSuchElementException) as e:
                last_exception = e
                error_type = type(e).__name__
                log_func(f"ERROR: Failed to find or wait for '{description}' (locator: {locator}) on attempt {attempt+1} ({error_type}).")
                self.capture_screenshot(f"{description.replace(' ','_')}_not_found")
                break # Exit retry loop, element likely won't appear

            except WebDriverException as e:
                last_exception = e
                error_type = type(e).__name__
                is_timeout = 'timed out' in str(e).lower()
                timeout_msg = " (Timeout Error)" if is_timeout else ""
                log_func(f"WARNING: WebDriverException{timeout_msg} during click attempt {attempt+1} for '{description}': {str(e)[:150]}...")

            except Exception as e:
                last_exception = e
                error_type = type(e).__name__
                log_func(f"ERROR: Unexpected error {error_type} clicking '{description}' on attempt {attempt+1}: {e}")
                self.capture_screenshot(f"{description.replace(' ','_')}_unexpected_click_error")
                traceback.print_exc()
                break # Exit retry loop for unexpected errors

            # Wait before retrying if loop continues
            if attempt < retries - 1:
                log_func(f"Waiting {delay}s before retrying click on '{description}'...")
                time.sleep(delay)
            else: # Last attempt failed
                 log_func(f"ERROR: Failed to click '{description}' after {retries} attempts. Last error: {type(last_exception).__name__}")
                 self.capture_screenshot(f"{description.replace(' ','_')}_click_failed_final")

        return False # Failed after all retries or breaking early


    @staticmethod
    def write_log_to_csv(log_data, filename=csv_filename):
        """Writes a log entry to the specified CSV file."""
        file_exists = os.path.isfile(filename)
        try:
            # Use 'a' mode to append, newline='' to prevent extra blank rows
            with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                if not file_exists or os.path.getsize(filename) == 0:
                    writer.writerow(['SessionID','Timestamp','File Name','Start Date','Status','End Date','Error Message'])
                # Reorder fields: Timestamp, File Name, Start Date, Status, End Date, Error Message
                writer.writerow([log_data[0], log_data[1], log_data[2], log_data[3], log_data[4], log_data[5], log_data[6]])
        except IOError as e:
            print(f"CRITICAL ERROR: Could not write to log file {filename}: {e}")
            print(f"LOG_DATA (CSV failed): {log_data}")
        except Exception as e:
             print(f"CRITICAL ERROR: Unexpected error writing to log file {filename}: {e}")
             print(f"LOG_DATA (CSV failed): {log_data}")

    def capture_screenshot(self, filename_prefix="error_screenshot"):
        """Saves a screenshot of the current browser window."""
        if not self.driver:
            self._log("Cannot capture screenshot, driver not available.")
            return None
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Save screenshot in the specific download folder for this run
            filename = os.path.join(self.download_folder, f"{filename_prefix}_{timestamp}.png")
            if self.driver.save_screenshot(filename):
                 self._log(f"Screenshot saved: {filename}")
                 return filename
            else:
                 self._log("Failed to save screenshot (driver returned false).")
                 return None
        except WebDriverException as e:
            self._log(f"Failed to capture screenshot due to WebDriverException: {e}")
            return None
        except Exception as e:
            self._log(f"Failed to capture screenshot due to unexpected error: {e}")
            return None

    def handle_alert(self, accept=True, status_callback=None):
        """Checks for and handles browser alerts."""
        log_func = status_callback or self._log
        try:
            # Use a short wait specifically for the alert
            short_wait = WebDriverWait(self.driver, 5) # Wait up to 5 seconds for an alert
            alert = short_wait.until(EC.alert_is_present())
            alert_text = alert.text
            log_func(f"Alert detected: '{alert_text}'")
            if accept:
                alert.accept()
                log_func("Accepted alert.")
            else:
                alert.dismiss()
                log_func("Dismissed alert.")
            return True # Alert was handled
        except TimeoutException:
            # No alert was present within the short wait time - this is normal
            return False # No alert handled
        except NoAlertPresentException:
             # Alert disappeared before we could handle it
             log_func("Warning: Alert disappeared before handling.")
             return False
        except Exception as e:
            log_func(f"Error handling alert: {e}")
            self.capture_screenshot("alert_handling_error")
            return False # Indicate alert was not successfully handled

    # --- Login Method ---
    @retry_on_exception(exceptions=(WebDriverException,), retries=2, delay=10)
    def login(self, login_url, email, password, otp_secret, status_callback=None):
        """Logs into the website using credentials and OTP."""
        log_func = status_callback or self._log
        if not self.driver or not self.wait:
            raise WebDriverException("WebDriver not initialized for login.")
        log_func(f"Attempting login for user {email}...")

        try:
            self.driver.get(login_url) # Navigate to trigger login if needed

            # --- Check for 502 Bad Gateway and retry if needed ---
            max_502_retries = 3
            for attempt_502 in range(max_502_retries):
                page_source = self.driver.page_source
                if '<h1>502 Bad Gateway</h1>' in page_source:
                    log_func(f"Detected 502 Bad Gateway (attempt {attempt_502+1}/{max_502_retries}). Refreshing and retrying...")
                    time.sleep(3)
                    self.driver.refresh()
                    time.sleep(2)
                    continue
                else:
                    break
            else:
                log_func("ERROR: 502 Bad Gateway persists after retries. Aborting this report.")
                self.capture_screenshot("502_bad_gateway")
                raise DownloadFailedException("502 Bad Gateway after retries.")
            # --- End 502 check ---

            # !!! VERIFY THESE LOCATORS AGAINST THE ACTUAL LOGIN PAGE !!!
            email_locator = (By.ID, 'mat-input-3')
            password_locator = (By.ID, 'mat-input-4')
            otp_locator = (By.ID, 'mat-input-5')
            login_button_locator = (By.ID, 'kt_login_signin_submit')

            log_func("Waiting for login elements...")
            email_field = self.wait.until(EC.element_to_be_clickable(email_locator))
            email_field.clear()
            email_field.send_keys(email)

            password_field = self.wait.until(EC.element_to_be_clickable(password_locator))
            password_field.clear()
            password_field.send_keys(password)

            # Generate and Enter OTP
            try:
                totp = pyotp.TOTP(otp_secret)
                otp_code = totp.now()
                # log_func(f"[DEBUG ONLY] Generated OTP: {otp_code}") # Debug only
                log_func("Entering OTP...")
                otp_field = self.wait.until(EC.element_to_be_clickable(otp_locator))
                otp_field.clear()
                otp_field.send_keys(otp_code)
            except Exception as otp_e:
                log_func(f"ERROR: Failed to generate or enter OTP: {otp_e}")
                self.capture_screenshot("otp_error")
                raise WebDriverException(f"OTP generation/entry failed: {otp_e}") from otp_e

            # Click Login Button Safely
            log_func("Clicking login button...")
            print(f"[DEBUG] Attempting robust click on locator: {login_button_locator}") # Console debug
            # Using the robust click method
            click_ok = self.robust_click_download_button(login_button_locator, description="CSV Download Button", status_callback=log_func)

            if not click_ok:
                log_func(f"ERROR: Failed to click Download Button (Locator: {login_button_locator}) after all attempts.")
                self.capture_screenshot("login_click_failed")
                raise WebDriverException("Failed to click login button after retries.")

            log_func("Download click initiated (or attempted). Checking for alerts...")
            # Handle potential alerts *after* clicking download
            self.handle_alert(accept=True, status_callback=log_func)

            # Wait for Login Success by checking URL or a known element on the home page
            # !!! VERIFY THE EXPECTED URL OR ELEMENT AFTER SUCCESSFUL LOGIN !!!
            expected_url_after_login = "https://bi.nhathuoclongchau.com.vn/Home.aspx"
            # Alternatively, wait for a specific element unique to the logged-in state:
            # expected_element_locator = (By.ID, 'some_element_id_only_visible_after_login')

            log_func(f"Waiting for successful login (expecting URL: {expected_url_after_login})...")
            try:
                self.wait.until(EC.url_to_be(expected_url_after_login))
                # Or: self.wait.until(EC.presence_of_element_located(expected_element_locator))
                current_url = self.driver.current_url
                log_func(f"Login successful! Current URL: {current_url}")
                return True
            except TimeoutException:
                current_url = self.driver.current_url
                log_func(f"ERROR: Login failed or took too long. Current URL: {current_url}. Expected: {expected_url_after_login}")
                self.capture_screenshot("login_failed_or_timeout")
                return False

        # Specific Exception Handling
        except DownloadFailedException as df_err: # Catch failures from click or wait
             log_func(f"DownloadFailedException caught: {df_err}")
             # Screenshot likely already taken by the failing function
             # No need to re-raise here, let finally block log

        except WebDriverException as e:
            log_func(f"ERROR: WebDriver error during login steps: {type(e).__name__} - {str(e)[:150]}...")
            self.capture_screenshot("login_webdriver_error")
            raise # Re-raise for decorator
        except Exception as e: # Catch other unexpected errors
            log_func(f"FATAL ERROR: Unexpected error during login steps: {type(e).__name__} - {e}")
            self.capture_screenshot("login_unexpected_error")
            traceback.print_exc()
            raise WebDriverException(log_func) from e # Wrap for consistency


    # --- File Handling ---
    def extract_zip_files(self, status_callback=None):
        """Extracts newly downloaded zip files and returns a list of extracted file paths."""
        log_func = status_callback or self._log
        log_func("Checking for new zip files to extract...")
        files_after_download = set()
        extracted_files = []
        try:
            if os.path.exists(self.download_folder):
                 files_after_download = set(os.listdir(self.download_folder))
            else:
                 log_func("Warning: Download folder not found for extraction.")
                 return [] # Cannot extract

            # Identify zip files and filter only those not extracted before
            zip_files = [f for f in files_after_download if f.lower().endswith('.zip')]
            new_zip_files = [f for f in zip_files if f not in self.extracted_zips]
            if not new_zip_files:
                log_func("No new zip files to extract.")
                return extracted_files
            for zip_file in new_zip_files:
                zip_path = os.path.join(self.download_folder, zip_file)
                try:
                    log_func(f"Extracting '{zip_file}'...")
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(self.download_folder)
                        extracted_names = zip_ref.namelist()
                        extracted_files.extend([os.path.join(self.download_folder, name) for name in extracted_names])
                        log_func(f"Extracted files from {zip_file}: {extracted_names}")
                    # Mark this zip as extracted
                    self.extracted_zips.add(zip_file)
                except zipfile.BadZipFile:
                     log_func(f"ERROR: Bad zip file '{zip_file}'. Skipping.")
                except Exception as e:
                     log_func(f"ERROR extracting '{zip_file}': {e}")
                     traceback.print_exc()

        except Exception as e:
             log_func(f"Error during zip extraction process: {e}")
             traceback.print_exc()
        return extracted_files

    def rename_extract_file(self, extracted_file_path, from_date, to_date, suffix="", status_callback=None):
        """Renames a file extracted from a zip archive."""
        log_func = status_callback or self._log
        if not extracted_file_path or not os.path.isfile(extracted_file_path):
            log_func(f"Rename extracted file failed: File '{extracted_file_path}' not found.")
            return None
        # Skip renaming for files already standardized
        original_filename = os.path.basename(extracted_file_path)
        if original_filename.startswith("BaoCaoFAF001"):
            log_func(f"Skipping rename for standardized file: {original_filename}")
            return original_filename
        try:
            file_dir, original_filename = os.path.split(extracted_file_path)
            file_name_part, file_extension = os.path.splitext(original_filename)
            from_date_formatted = datetime.strptime(from_date, '%Y-%m-%d').strftime('%d%m%Y')
            to_date_formatted = datetime.strptime(to_date, '%Y-%m-%d').strftime('%d%m%Y')
            new_name_base = f"{file_name_part}_{from_date_formatted}_{to_date_formatted}{suffix}{file_extension}".replace(' ','_')
            new_full_path = os.path.join(file_dir, new_name_base)
            # Handle naming conflicts
            counter = 1
            final_new_name = new_name_base
            while os.path.exists(new_full_path):
                final_new_name = f"{file_name_part}_{from_date_formatted}_{to_date_formatted}{suffix}_v{counter}{file_extension}".replace(' ','_')
                new_full_path = os.path.join(file_dir, final_new_name)
                counter += 1
            os.rename(extracted_file_path, new_full_path)
            log_func(f"Successfully renamed extracted file to: {final_new_name}")
            return final_new_name
        except Exception as e:
            error_msg = f"Error renaming extracted file '{extracted_file_path}': {e}"
            log_func(f"ERROR: {error_msg}")
            traceback.print_exc()
            return None # Indicate failure

    def rename_downloaded_file(self, original_filename, from_date, to_date, suffix="", status_callback=None):
        """Renames a specific downloaded file."""
        log_func = status_callback or self._log
        if not original_filename:
             log_func("Rename failed: No original filename provided.")
             return None
        # Skip renaming for files already standardized
        if original_filename.startswith("BaoCaoFAF001"):
            log_func(f"Skipping rename for standardized file: {original_filename}")
            return original_filename

        original_full_path = os.path.join(self.download_folder, original_filename)

        if not os.path.isfile(original_full_path):
             log_func(f"Rename failed: File '{original_filename}' not found in {self.download_folder}.")
             # Maybe the file is still downloading or has a different name?
             # Check current files again?
             # current_files = os.listdir(self.download_folder)
             # log_func(f"Current files in download folder: {current_files}")
             return None

        try:
            from_date_formatted = datetime.strptime(from_date, '%Y-%m-%d').strftime('%d%m%Y')
            to_date_formatted = datetime.strptime(to_date, '%Y-%m-%d').strftime('%d%m%Y')
            file_name_part, file_extension = os.path.splitext(original_filename)

            # Construct new name, replace spaces
            new_name_base = f"{file_name_part}_{from_date_formatted}_{to_date_formatted}{suffix}{file_extension}".replace(' ','_')
            new_full_path = os.path.join(self.download_folder, new_name_base)

            # Handle naming conflicts
            counter = 1
            final_new_name = new_name_base
            while os.path.exists(new_full_path):
                 log_func(f"Warning: File '{final_new_name}' already exists. Appending counter.")
                 name_part, ext_part = os.path.splitext(new_name_base)
                 final_new_name = f"{name_part}_{counter}{ext_part}"
                 new_full_path = os.path.join(self.download_folder, final_new_name)
                 counter += 1

            log_func(f"Attempting to rename '{original_filename}' to '{final_new_name}'")
            os.rename(original_full_path, new_full_path)
            log_func(f"Successfully renamed file to: {final_new_name}")
            # Update the baseline state *after* successful rename
            self.before_download.discard(original_filename)
            self.before_download.add(final_new_name)
            return final_new_name # Return the actual new name

        except Exception as e:
            error_msg = f"Error renaming file '{original_filename}': {e}"
            log_func(f"ERROR: {error_msg}")
            traceback.print_exc()
            return None # Indicate failure


    # --- Core Download Logic ---

    def _perform_download_steps(self, report_url, from_date, to_date, report_specific_setup=None, file_suffix="", status_callback=None):
        """Internal helper for common download steps."""
        log_func = status_callback or self._log
        if not self.driver or not self.wait:
            raise WebDriverException("WebDriver not initialized for download.")

        log_file_name = ""
        log_status = "Failed (Initial)"
        log_error = ""
        downloaded_original_name = None

        # --- Add logic to check date range validity ---
        try:
            from_dt = datetime.strptime(from_date, '%Y-%m-%d')
            to_dt = datetime.strptime(to_date, '%Y-%m-%d')
            if from_dt > to_dt:
                log_error = f"Invalid date range: from_date ({from_date}) is after to_date ({to_date})"
                log_status = "Failed (Invalid Date Range)"
                log_func(f"ERROR: {log_error}")
                # Ghi log vào file CSV
                log_data = [
                    self.session_id,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    log_file_name, from_date, log_status, to_date, log_error
                ]
                self.write_log_to_csv(log_data)
                return False
        except Exception as e:
            log_error = f"Error parsing date range: {e}"
            log_status = "Failed (Date Parse Error)"
            log_func(f"ERROR: {log_error}")
            log_data = [
                self.session_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                log_file_name, from_date, log_status, to_date, log_error
            ]
            self.write_log_to_csv(log_data)
            return False
        # --- End logic ---

        # --- Add session check and re-login logic ---
        if not self.is_session_valid():
            log_func("Session expired or invalid before starting download. Attempting to re-login...")
            try:
                relogin_ok = self.login(self.login_url, self.email, self.password, self.otp_secret, status_callback=log_func)
                if not relogin_ok:
                    log_func("ERROR: Re-login failed. Skipping this report.")
                    self.capture_screenshot("relogin_failed")
                    raise DownloadFailedException("Session expired and re-login failed.")
                log_func("Re-login successful. Continuing download.")
                # Sau khi login lại, luôn truy cập lại đúng report_url để đảm bảo ở đúng trang báo cáo
                self.driver.get(report_url)
                log_func(f"Re-login done. Navigated again to report URL: {report_url}")
            except Exception as e:
                log_func(f"ERROR: Exception during re-login: {e}")
                self.capture_screenshot("relogin_exception")
                raise DownloadFailedException("Session expired and re-login exception.")
        else:
            # Nếu không cần re-login, vẫn phải truy cập report_url như cũ
            self.driver.get(report_url)
            log_func(f"Navigating to report URL: {report_url}")
        # --- End session check ---

        try:
            # Nếu vừa re-login thì đã get(report_url) ở trên, nếu không thì vẫn cần truy cập report_url
            if not (hasattr(self, "_just_relogin") and self._just_relogin):
                log_func(f"Navigating to report URL: {report_url}")
                self.driver.get(report_url)
            # Đảm bảo cờ này luôn reset
            self._just_relogin = False

            # --- Check for 502 Bad Gateway and retry if needed ---
            max_502_retries = 3
            for attempt_502 in range(max_502_retries):
                page_source = self.driver.page_source
                if '<h1>502 Bad Gateway</h1>' in page_source:
                    log_func(f"Detected 502 Bad Gateway (attempt {attempt_502+1}/{max_502_retries}). Refreshing and retrying...")
                    time.sleep(3)
                    self.driver.refresh()
                    time.sleep(2)
                    continue
                else:
                    break
            else:
                log_func("ERROR: 502 Bad Gateway persists after retries. Aborting this report.")
                self.capture_screenshot("502_bad_gateway")
                raise DownloadFailedException("502 Bad Gateway after retries.")
            # --- End 502 check ---

            # --- Existing code ---
            sdate_locator = (By.ID, 'ctl00_MainContent_cbo_fromDate_dateInput')
            edate_locator = (By.ID, 'ctl00_MainContent_cbo_toDate_dateInput')
            download_button_locator = (By.ID, 'ctl00_MainContent_btnExportCSVDemo_input')
            log_func("Waiting for date input fields...")
            self.wait.until(EC.presence_of_element_located(sdate_locator))
            # --- Existing code ---
            if report_specific_setup:
                report_specific_setup()
            # --- Existing code ---
            log_func(f"Setting 'To Date': {to_date}")
            edate_input = self.wait.until(EC.element_to_be_clickable(edate_locator))
            edate_input.clear()
            edate_input.send_keys(format_date_ddmmyyyy(to_date))
            log_func(f"Setting 'From Date': {from_date}")
            sdate_input = self.wait.until(EC.element_to_be_clickable(sdate_locator))
            sdate_input.clear()
            sdate_input.send_keys(format_date_ddmmyyyy(from_date))
            # --- Existing code ---
            self.handle_alert(accept=True, status_callback=log_func)
            self.update_files_before_download()
            log_func("Locating and clicking download button...")
            print(f"[DEBUG] Attempting robust click on locator: {download_button_locator}")
            click_ok = self.robust_click_download_button(download_button_locator, description="CSV Download Button", status_callback=log_func)
            if not click_ok:
                log_error = f"Failed to click Download Button (Locator: {download_button_locator}) after all attempts."
                log_status = "Failed (Click Download)"
                self.capture_screenshot("download_click_failed")
                log_func(f"ERROR: {log_error}")
                raise DownloadFailedException(log_error)
            log_func("Download click initiated (or attempted). Checking for alerts...")
            self.handle_alert(accept=True, status_callback=log_func)
            downloaded_original_name = self.wait_for_download_to_finish(status_callback=log_func)
            if downloaded_original_name:
                log_func(f"Download detected: {downloaded_original_name}")
                # Chỉ giải nén file zip vừa tải về, không quét toàn bộ thư mục
                renamed_file = self.rename_downloaded_file(downloaded_original_name, from_date, to_date, file_suffix, log_func)
                log_file_name = renamed_file if renamed_file else downloaded_original_name
                if downloaded_original_name.lower().endswith('.zip'):
                    zip_path = os.path.join(self.download_folder, log_file_name)
                    if os.path.exists(zip_path):
                        try:
                            log_func(f"Extracting '{log_file_name}'...")
                            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                                zip_ref.extractall(self.download_folder)
                                extracted_names = zip_ref.namelist()
                                log_func(f"Extracted files from {log_file_name}: {extracted_names}")
                                for extracted_name in extracted_names:
                                    extracted_path = os.path.join(self.download_folder, extracted_name)
                                    self.rename_extract_file(extracted_path, from_date, to_date, file_suffix, log_func)
                        except zipfile.BadZipFile:
                            log_func(f"ERROR: Bad zip file '{log_file_name}'. Skipping.")
                        except Exception as e:
                            log_func(f"ERROR extracting '{log_file_name}': {e}")
                            traceback.print_exc()
                log_status = "Success" if renamed_file else "Success (Rename Failed)"
                log_func(f"Download and processing complete. Final state: {log_file_name}")
            else:
                log_error = "Download wait timed out or failed to detect completed file."
                log_status = "Failed (Download Wait)"
                self.capture_screenshot("download_wait_timeout")
                log_func(f"ERROR: {log_error}")
                raise DownloadFailedException(log_error)
            # --- Existing code ---
        # --- Existing code ---
        except DownloadFailedException as df_err: # Catch failures from click or wait
             log_status = log_status if log_status != "Failed (Initial)" else "Failed (Download Step)"
             log_error = str(df_err)
             log_func(f"DownloadFailedException caught: {log_error}")
             # Screenshot likely already taken by the failing function
             # No need to re-raise here, let finally block log

        except WebDriverException as e:
            log_status = "Failed (WebDriver Error)"
            log_error = f"WebDriver error during download steps: {type(e).__name__} - {str(e)[:150]}..."
            if "invalid session id" in str(e).lower():
                log_status = "Failed (Invalid Session)"
                log_error = f"WebDriver session invalid (browser closed?): {str(e)[:150]}..."
                log_func(f"FATAL ERROR: {log_error}")
                self.capture_screenshot("webdriver_session_invalid")
                raise # Re-raise critical session errors
            else:
                log_func(f"ERROR: {log_error}")
                self.capture_screenshot("download_webdriver_error")
                traceback.print_exc()
                # Consider re-raising non-session errors depending on desired behavior
        except Exception as e:
            log_status = "Failed (Unexpected Error)"
            log_error = f"Unexpected error during download steps: {type(e).__name__} - {e}"
            log_func(f"FATAL ERROR: {log_error}")
            self.capture_screenshot("download_unexpected_error")
            traceback.print_exc()
            # Do not re-raise, let finally log and the calling function decide

        finally:
            # Log result regardless of success or failure
            log_data = [
                self.session_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                log_file_name, from_date, log_status, to_date, log_error
            ]
            self.write_log_to_csv(log_data)
            log_func(f"Logged download status '{log_status}' for {from_date}-{to_date}.")

        # Return True on success, False on failure for the calling function
        return log_status.startswith("Success")


    def robust_click_download_button(self, download_button_locator, description="Download Button", status_callback=None):
        """Tries multiple methods to click the download button reliably."""
        log_func = status_callback or self._log
        log_func(f"[Robust Click] Attempting to click '{description}' (Locator: {download_button_locator})")

        try:
            # 1. Wait for element to be clickable
            log_func(f"[Robust Click] Waiting for '{description}' to be clickable...")
            btn = self.wait.until(EC.element_to_be_clickable(download_button_locator))
            log_func(f"[Robust Click] Element '{description}' found and deemed clickable.")

            # 2. Log element details for debugging
            try:
                btn_html = btn.get_attribute('outerHTML')
                btn_text = btn.text
                btn_tag = btn.tag_name
                btn_class = btn.get_attribute('class')
                btn_disabled = btn.get_attribute('disabled')
                btn_style = btn.get_attribute('style')
                log_func(f"[Robust Click Debug] Tag: {btn_tag}, Text: '{btn_text}', Class: '{btn_class}', Disabled: {btn_disabled}") #, Style: '{btn_style}', HTML: {btn_html[:100]}...")
                print(f"[DEBUG] Download button outerHTML: {btn_html}") # Keep console debug too
            except StaleElementReferenceException:
                log_func("[Robust Click Debug] Element went stale while getting attributes. Will retry finding.")
                # Let the outer retry handle finding it again if needed, or fail here
                raise # Re-raise stale element exception

            # 3. Scroll into view
            log_func(f"[Robust Click] Scrolling '{description}' into view...")
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", btn)
            time.sleep(0.5) # Small pause after scroll

            # 4. Try Selenium's native click
            try:
                log_func(f"[Robust Click] Trying Selenium native .click() on '{description}'...")
                btn.click()
                log_func(f"[Robust Click] Selenium native .click() successful for '{description}'.")
                return True
            except (ElementClickInterceptedException, ElementNotInteractableException) as native_click_err:
                log_func(f"[Robust Click] Selenium native .click() failed: {type(native_click_err).__name__}. Trying alternatives.")
            except StaleElementReferenceException:
                 log_func("[Robust Click] Element went stale before native click. Will let retry handle it.")
                 raise # Re-raise to trigger retry

            # 5. Try ActionChains click
            try:
                log_func(f"[Robust Click] Trying ActionChains click on '{description}'...")
                actions = ActionChains(self.driver)
                actions.move_to_element(btn).click().perform()
                log_func(f"[Robust Click] ActionChains click successful for '{description}'.")
                return True
            except Exception as action_click_err:
                log_func(f"[Robust Click] ActionChains click failed: {type(action_click_err).__name__}. Trying JavaScript.")

            # 6. Try JavaScript click
            try:
                log_func(f"[Robust Click] Trying JavaScript click on '{description}'...")
                self.driver.execute_script("arguments[0].click();", btn)
                log_func(f"[Robust Click] JavaScript click successful for '{description}'.")
                return True
            except Exception as js_click_err:
                log_func(f"[Robust Click] JavaScript click failed: {type(js_click_err).__name__}.")
                # All methods failed for this attempt
                log_func(f"[Robust Click] All click methods failed for '{description}'.")
                last_exception = js_click_err # Store last error

        except (TimeoutException, NoSuchElementException) as e:
            log_func(f"[Robust Click] ERROR: Could not find or wait for '{description}' (Locator: {download_button_locator}). {type(e).__name__}")
            self.capture_screenshot(f"{description.replace(' ','_')}_robust_find_fail")
            return False # Cannot proceed if not found
        except StaleElementReferenceException as e:
             log_func(f"[Robust Click] ERROR: Element '{description}' became stale during robust click process. {type(e).__name__}. Retrying needed.")
             # This exception should ideally be caught by the @retry_on_exception decorator if applied to the calling function
             # Returning False here might prevent a retry depending on how it's called. Raising it might be better.
             raise e # Raise stale exception to allow retry decorator to catch it
        except Exception as e:
            log_func(f"[Robust Click] ERROR: Unexpected error during robust click for '{description}': {type(e).__name__} - {e}")
            self.capture_screenshot(f"{description.replace(' ','_')}_robust_unexpected_fail")
            traceback.print_exc()
            return False # Failed due to unexpected error

        return False # All methods failed


    # --- Specific Report Download Methods ---

    @retry_on_exception()
    def download_report_001(self, report_url, from_date, to_date, status_callback=None):
        """Downloads report FAF001."""
        log_func = status_callback or self._log
        log_func("Executing specific setup for FAF001...")
        def setup_001():
             # !!! VERIFY THIS RADIO BUTTON LOCATOR !!!
             radio_locator = (By.ID, 'ctl00_MainContent_rblType_1')
             if not self.safe_click(radio_locator, "FAF001 Report Type Radio", retries=2, status_callback=log_func):
                 raise DownloadFailedException("Failed to click FAF001 report type radio button.")
             log_func("Clicked FAF001 specific radio button.")
             time.sleep(SHORT_WAIT) # Pause after click if needed
        return self._perform_download_steps(report_url, from_date, to_date, report_specific_setup=setup_001, file_suffix="", status_callback=log_func)

    @retry_on_exception()
    def download_report_004N(self, report_url, from_date, to_date, status_callback=None):
        """Downloads report FAF004N (Imports)."""
        log_func = status_callback or self._log
        log_func("Executing specific setup for FAF004N (Imports)...")
        def setup_004N():
             # !!! VERIFY THIS RADIO BUTTON LOCATOR !!!
             radio_locator = (By.ID, 'ctl00_MainContent_rblType_1') # Assume Imports type is index 1
             if not self.safe_click(radio_locator, "FAF004N Report Type Radio (Imports)", retries=2, status_callback=log_func):
                 raise DownloadFailedException("Failed to click FAF004N report type radio button (Imports).")
             log_func("Clicked FAF004N (Imports) specific radio button.")
             time.sleep(SHORT_WAIT)
        return self._perform_download_steps(report_url, from_date, to_date, report_specific_setup=setup_004N, file_suffix="N", status_callback=log_func)

    @retry_on_exception()
    def download_report_004X(self, report_url, from_date, to_date, status_callback=None):
        """Downloads report FAF004X (Exports)."""
        log_func = status_callback or self._log
        log_func("Executing specific setup for FAF004X (Exports)...")
        def setup_004X():
            # !!! VERIFY THIS RADIO BUTTON LOCATOR !!!
             radio_locator = (By.ID, 'ctl00_MainContent_rblType_0') # Assume Exports type is index 0
             if not self.safe_click(radio_locator, "FAF004X Report Type Radio (Exports)", retries=2, status_callback=log_func):
                 raise DownloadFailedException("Failed to click FAF004X report type radio button (Exports).")
             log_func("Clicked FAF004X (Exports) specific radio button.")
             time.sleep(SHORT_WAIT)
        return self._perform_download_steps(report_url, from_date, to_date, report_specific_setup=setup_004X, file_suffix="X", status_callback=log_func)

    @retry_on_exception()
    def download_generic_report(self, report_url, from_date, to_date, status_callback=None):
         """Downloads a generic report with no special setup."""
         log_func = status_callback or self._log
         log_func("Executing generic download logic...")
         # Pass None for setup, empty suffix
         return self._perform_download_steps(report_url, from_date, to_date, report_specific_setup=None, file_suffix="", status_callback=log_func)

    # --- Region Selection Logic ---
    def select_region(self, region_index, status_callback=None):
        """Selects a single region based on its index using XPath."""
        log_func = status_callback or self._log
        try:
            if region_index in regions_data:
                region = regions_data[region_index]
                xpath = region["xpath"]
                region_name = region["name"]
                locator = (By.XPATH, xpath)

                log_func(f"Selecting region '{region_name}' (Index: {region_index}) using XPath: {xpath}")
                if not self.safe_click(locator, f"Region '{region_name}' Checkbox", status_callback=log_func):
                    log_func(f"ERROR: Failed to click region '{region_name}'.")
                    self.capture_screenshot(f"region_{region_name}_select_fail")
                    return False
                time.sleep(SHORT_WAIT) # Pause after selecting region
                log_func(f"Successfully clicked region '{region_name}'.")
                return True
            else:
                log_func(f"ERROR: Invalid region index: {region_index}.")
                return False
        except Exception as e:
            log_func(f"ERROR selecting region index {region_index}: {e}")
            self.capture_screenshot(f"region_select_error_idx_{region_index}")
            traceback.print_exc()
            return False

    # --- Region Report Download Method (FAF030 example) ---
    # Use retry decorator for the whole operation
    # Now uses DownloadFailedException correctly as it's defined above
    @retry_on_exception(exceptions=(WebDriverException, DownloadFailedException), retries=2, delay=15)
    def download_report_for_region(self, report_url, from_date, to_date, region_index, status_callback=None):
        """Downloads a report requiring region selection (e.g., FAF030)."""
        log_func = status_callback or self._log
        if region_index not in regions_data:
             log_func(f"ERROR: Invalid region index {region_index} passed.")
             # Log this error clearly
             self.write_log_to_csv([self.session_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), from_date, f"Failed (Invalid Region Index: {region_index})", to_date, "Invalid index provided"], csv_filename)
             return False # Fail this specific region download attempt

        region_name = regions_data[region_index]["name"]
        log_func(f"--- Starting download for Region: {region_name} ({from_date} to {to_date}) ---")

        log_file_name = ""
        log_status = "Failed (Region Initial)"
        log_error = ""
        downloaded_original_name = None

        try:
            log_func(f"Navigating to report URL: {report_url}")
            self.driver.get(report_url)

            # --- Check for 502 Bad Gateway and retry if needed ---
            max_502_retries = 3
            for attempt_502 in range(max_502_retries):
                page_source = self.driver.page_source
                if '<h1>502 Bad Gateway</h1>' in page_source:
                    log_func(f"Detected 502 Bad Gateway (attempt {attempt_502+1}/{max_502_retries}). Refreshing and retrying...")
                    time.sleep(3)
                    self.driver.refresh()
                    time.sleep(2)
                    continue
                else:
                    break
            else:
                log_func("ERROR: 502 Bad Gateway persists after retries. Aborting this report.")
                self.capture_screenshot("502_bad_gateway")
                raise DownloadFailedException("502 Bad Gateway after retries.")
            # --- End 502 check ---

            # !!! VERIFY ALL LOCATORS FOR REGION REPORT PAGE !!!
            sdate_locator = (By.ID, 'ctl00_MainContent_cbo_fromDate_dateInput')
            edate_locator = (By.ID, 'ctl00_MainContent_cbo_toDate_dateInput')
            tree_arrow_locator = (By.ID, 'ctl00_MainContent_TreeShopThuoc1_cboDepartmentsThuoc_Arrow')
            # Tree expand might not be needed if regions visible after arrow click
            # tree_plus_locator = (By.CLASS_NAME, 'rtPlus') # Often unreliable
            # Click outside element (verify XPath)
            close_dropdown_locator = (By.XPATH, "//div[contains(@class,'RadWindow')]//span[contains(text(), 'Báo Cáo Nhập Xuất Tồn FAF')]") # Example, needs verification
            # !!! THIS IS THE DOWNLOAD BUTTON LOCATOR FOR REGION REPORTS - VERIFY !!!
            download_button_locator_region = (By.ID, 'ctl00_MainContent_btnExportExcel_input')

            log_func("Waiting for date inputs...")
            self.wait.until(EC.presence_of_element_located(sdate_locator))

            # --- Enter Dates ---
            log_func(f"Setting 'To Date': {to_date}")
            edate_input = self.wait.until(EC.element_to_be_clickable(edate_locator))
            edate_input.clear()
            edate_input.send_keys(format_date_ddmmyyyy(to_date))

            log_func(f"Setting 'From Date': {from_date}")
            sdate_input = self.wait.until(EC.element_to_be_clickable(sdate_locator))
            sdate_input.clear()
            sdate_input.send_keys(format_date_ddmmyyyy(from_date))

            # --- Open Region Tree and Select ---
            log_func("Opening region selection tree...")
            if not self.safe_click(tree_arrow_locator, "Region Tree Arrow", status_callback=log_func):
                 raise DownloadFailedException("Failed to click open region selection tree arrow.")

            # Select the specific region using its XPath
            if not self.select_region(region_index, status_callback=log_func):
                 # select_region already logged the error and took screenshot
                 raise DownloadFailedException(f"Failed to select region '{region_name}'.")

            # Click outside to close the tree (optional, but can help)
            log_func("Attempting to close region dropdown...")
            # Use safe_click, but failure might not be critical
            self.safe_click(close_dropdown_locator, "Report Title (to close dropdown)", retries=1, status_callback=log_func)
            time.sleep(SHORT_WAIT) # Wait after closing dropdown

            # --- Click Region Download Button ---
            log_func(f"Locating and clicking region download button (Locator: {download_button_locator_region})...")
            self.handle_alert(accept=True, status_callback=log_func)
            self.update_files_before_download()

            # Use robust click for the region download button as well
            if self.robust_click_download_button(download_button_locator_region, description=f"Region {region_name} Download Button", status_callback=log_func):
                log_func(f"Region {region_name} download click initiated. Checking alerts...")
                self.handle_alert(accept=True, status_callback=log_func)

                # --- Wait for Download ---
                downloaded_original_name = self.wait_for_download_to_finish(status_callback=log_func)

                if downloaded_original_name:
                    log_func(f"Download detected for region {region_name}: {downloaded_original_name}")
                    # --- Process File ---
                    # Rename using region name as suffix
                    renamed_file = self.rename_downloaded_file(downloaded_original_name, from_date, to_date, f"_{region_name}", log_func)
                    log_file_name = renamed_file if renamed_file else downloaded_original_name

                    if downloaded_original_name.lower().endswith('.zip'):
                        extracted_files = self.extract_zip_files(status_callback=log_func)
                        # Rename all extracted files after extraction
                        for extracted_path in extracted_files:
                            self.rename_extract_file(extracted_path, from_date, to_date, f"_{region_name}", log_func)

                    log_status = "Success" if renamed_file else "Success (Rename Failed)"
                    log_func(f"Region {region_name} download and processing complete. File: {log_file_name}")
                else: # wait_for_download_to_finish failed
                    log_error = f"Download wait timed out or failed for region {region_name}."
                    log_status = "Failed (Download Wait)"
                    log_func(f"ERROR: {log_error}")
                    self.capture_screenshot(f"region_{region_name}_wait_timeout")
                    raise DownloadFailedException(log_error) # Treat as failure
            else: # robust_click failed
                log_error = f"Failed to click download button for region {region_name} (Locator: {download_button_locator_region})."
                log_status = "Failed (Click Error)"
                log_func(f"ERROR: {log_error}")
                # Screenshot should be taken by robust_click method on failure
                raise DownloadFailedException(log_error)

        # --- Error Handling ---
        except DownloadFailedException as df_err:
             log_status = log_status if log_status != "Failed (Region Initial)" else "Failed (Region Setup/Select/Click)"
             log_error = str(df_err)
             log_func(f"DownloadFailedException caught for region {region_name}: {log_error}")
             # Allow finally block to log
        except WebDriverException as e: # Catch WebDriver errors specifically
             log_status = "Failed (WebDriver Error)"
             log_error = f"WebDriver error for region {region_name}: {type(e).__name__} - {str(e)[:150]}..."
             if "invalid session id" in str(e).lower():
                 log_status = "Failed (Invalid Session)"
                 log_error = f"WebDriver session invalid (region {region_name}): {str(e)[:150]}..."
                 log_func(f"FATAL: Session became invalid. Stopping.")
                 self.capture_screenshot(f"region_{region_name}_session_invalid")
                 raise # Re-raise critical session errors
             else:
                 log_func(f"ERROR: {log_error}")
                 self.capture_screenshot(f"region_{region_name}_webdriver_error")
                 traceback.print_exc()
                 # Let finally block log
        except Exception as e:
             log_status = "Failed (Unexpected Error)"
             log_error = f"Unexpected error for region {region_name}: {type(e).__name__} - {e}"
             log_func(f"FATAL ERROR: {log_error}")
             self.capture_screenshot(f"region_{region_name}_unexpected_error")
             traceback.print_exc()
             # Let finally block log

        finally:
            # --- Log Result ---
            log_data = [
                self.session_id,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                log_file_name, from_date, log_status, to_date, log_error
            ]
            self.write_log_to_csv(log_data)
            log_func(f"Logged region download status '{log_status}' for {from_date}-{to_date}, Region: {region_name}.")
            log_func(f"--- Finished processing Region: {region_name} ---")


        # Return True/False based on success status
        return log_status.startswith("Success")


    # --- Chunking Methods ---

    def split_date_range(self, start_date_str, end_date_str, chunk_size):
        """Splits a date range into smaller chunks."""
        log_func = self._log # Use internal logger
        try:
            start = datetime.strptime(start_date_str, '%Y-%m-%d')
            end = datetime.strptime(end_date_str, '%Y-%m-%d')
        except (ValueError, TypeError) as e:
             log_func(f"ERROR parsing date range: '{start_date_str}' to '{end_date_str}'. Invalid format or empty? Error: {e}")
             return []

        if start > end:
            log_func(f"Warning: Start date {start_date_str} is after end date {end_date_str}. No chunks generated.")
            return []

        date_ranges = []
        current_start = start

        while current_start <= end:
            chunk_end_date = end # Default to end if chunk_size is invalid
            if chunk_size == 'month':
                # End of the current month
                month_end = (current_start.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                chunk_end_date = min(month_end, end)
            elif isinstance(chunk_size, int) and chunk_size > 0:
                # Calculate end based on number of days
                chunk_end_date = min(current_start + timedelta(days=chunk_size - 1), end)
            else:
                 log_func(f"Warning: Invalid chunk size '{chunk_size}'. Processing range {current_start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')} as single chunk.")
                 chunk_end_date = end # Process remaining range as one chunk

            date_ranges.append((current_start.strftime('%Y-%m-%d'), chunk_end_date.strftime('%Y-%m-%d')))
            # Move to the next day after the current chunk ends
            current_start = chunk_end_date + timedelta(days=1)

            # Safety break
            if len(date_ranges) > 1000: # Limit chunks to prevent infinite loops
                log_func("ERROR: Exceeded maximum number of chunks (1000). Stopping split.")
                break

        return date_ranges

    def _download_chunks_base(self, download_method, report_url, start_date, end_date, chunk_size, status_callback=None, **kwargs):
        """Base function to handle downloading in chunks."""
        log_func = status_callback or self._log
        log_func(f"Splitting date range {start_date} to {end_date} with chunk size/mode: {chunk_size}.")
        date_ranges = self.split_date_range(start_date, end_date, chunk_size)
        total_chunks = len(date_ranges)
        success_count = 0
        fail_count = 0

        if not date_ranges:
             message = f"Could not split date range {start_date} to {end_date} or range is invalid. No download performed."
             log_func(f"WARNING: {message}")
             # Log failure for the whole range?
             self.write_log_to_csv([self.session_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "", start_date, "Failed (Date Split)", end_date, message], csv_filename)
             return # Cannot proceed

        log_func(f"Total chunks to process: {total_chunks}")

        for i, (from_date_chunk, to_date_chunk) in enumerate(date_ranges):
            chunk_num = i + 1
            log_func(f"--- Starting Chunk {chunk_num}/{total_chunks}: {from_date_chunk} to {to_date_chunk} ---")

            # Introduce a flag to check if the browser session is still valid
            if not self.is_session_valid():
                log_func("ERROR: WebDriver session is invalid before starting chunk. Stopping.")
                fail_count += (total_chunks - i) # Mark remaining chunks as failed
                break

            try:
                # Call the specific download method passed as argument
                # Pass kwargs which might include region_index for region downloads
                if download_method(report_url=report_url, from_date=from_date_chunk, to_date=to_date_chunk, status_callback=log_func, **kwargs):
                     success_count += 1
                     log_func(f"--- Completed Chunk {chunk_num}/{total_chunks} Successfully ---")
                else:
                     # Method returned False, indicating failure was logged internally
                     fail_count += 1
                     log_func(f"--- Completed Chunk {chunk_num}/{total_chunks} with FAILURE (Check Logs) ---")
                     # Optional: Add a longer pause after a failure
                     # time.sleep(RETRY_DELAY)

            # Catch exceptions that might occur *outside* the decorated download_method
            # (e.g., if download_method itself raises something unexpected or if session becomes invalid between chunks)
            except WebDriverException as wd_e:
                 fail_count += 1
                 error_msg = f"WebDriver ERROR in Chunk {chunk_num}/{total_chunks} ({from_date_chunk} to {to_date_chunk}): {type(wd_e).__name__} - {str(wd_e)[:150]}..."
                 log_func(error_msg)
                 traceback.print_exc()
                 self.write_log_to_csv([self.session_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "", from_date_chunk, f"Failed in Chunk (WebDriver)", to_date_chunk, error_msg], csv_filename)
                 if "invalid session id" in str(wd_e).lower():
                     log_func("FATAL: Session became invalid. Stopping further chunks.")
                     fail_count += (total_chunks - (i + 1)) # Mark remaining as failed
                     break # Stop processing chunks

            except Exception as e:
                fail_count += 1
                error_msg = f"UNEXPECTED ERROR in Chunk {chunk_num}/{total_chunks} ({from_date_chunk} to {to_date_chunk}): {type(e).__name__} - {e}"
                log_func(error_msg)
                traceback.print_exc()
                self.write_log_to_csv([self.session_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "", from_date_chunk, f"Failed in Chunk (Unexpected)", to_date_chunk, error_msg], csv_filename)
                # Consider stopping if errors are critical

            finally:
                # Pause between chunks
                if chunk_num < total_chunks:
                    log_func(f"Pausing {SHORT_WAIT * 2}s before next chunk...")
                    time.sleep(SHORT_WAIT * 2)

        log_func(f"Finished processing all {total_chunks} chunks. Success: {success_count}, Failed: {fail_count}.")


    # --- Public Chunking Wrappers (Called by app.py) ---

    def download_reports_in_chunks(self, report_url, start_date, end_date, chunk_size, status_callback=None):
        """Downloads generic reports in chunks."""
        self._download_chunks_base(self.download_generic_report, report_url, start_date, end_date, chunk_size, status_callback)

    def download_reports_in_chunks_1(self, report_url, start_date, end_date, chunk_size, status_callback=None):
        """Downloads FAF001 reports in chunks."""
        self._download_chunks_base(self.download_report_001, report_url, start_date, end_date, chunk_size, status_callback)

    def download_reports_in_chunks_4n(self, report_url, start_date, end_date, chunk_size, status_callback=None):
        """Downloads FAF004N reports in chunks."""
        self._download_chunks_base(self.download_report_004N, report_url, start_date, end_date, chunk_size, status_callback)

    def download_reports_in_chunks_4x(self, report_url, start_date, end_date, chunk_size, status_callback=None):
        """Downloads FAF004X reports in chunks."""
        self._download_chunks_base(self.download_report_004X, report_url, start_date, end_date, chunk_size, status_callback)

    # Add wrappers for other reports (2, 3, 5, 6, 28) using the generic method
    def download_reports_in_chunks_2(self, report_url, start_date, end_date, chunk_size, status_callback=None):
         self._download_chunks_base(self.download_generic_report, report_url, start_date, end_date, chunk_size, status_callback)

    def download_reports_in_chunks_3(self, report_url, start_date, end_date, chunk_size, status_callback=None):
         self._download_chunks_base(self.download_generic_report, report_url, start_date, end_date, chunk_size, status_callback)

    def download_reports_in_chunks_5(self, report_url, start_date, end_date, chunk_size, status_callback=None):
         self._download_chunks_base(self.download_generic_report, report_url, start_date, end_date, chunk_size, status_callback)

    def download_reports_in_chunks_6(self, report_url, start_date, end_date, chunk_size, status_callback=None):
         self._download_chunks_base(self.download_generic_report, report_url, start_date, end_date, chunk_size, status_callback)

    def download_reports_in_chunks_28(self, report_url, start_date, end_date, chunk_size, status_callback=None):
         self._download_chunks_base(self.download_generic_report, report_url, start_date, end_date, chunk_size, status_callback)

    # --- Region Report Chunking ---
    def download_reports_for_all_regions(self, report_url, start_date, end_date, chunk_size, region_indices, status_callback=None):
        """Downloads region-specific reports in chunks for specified regions."""
        log_func = status_callback or self._log
        log_func(f"Starting multi-region download for regions {region_indices} from {start_date} to {end_date}.")

        regions_to_process = [idx for idx in region_indices if idx in regions_data]
        if not regions_to_process:
            log_func("Warning: No valid region indices provided for multi-region download.")
            return

        # Chunking happens *outside* the region loop. Each chunk iterates through regions.
        log_func(f"Splitting date range {start_date} to {end_date} for region download.")
        date_ranges = self.split_date_range(start_date, end_date, chunk_size)
        total_chunks = len(date_ranges)

        if not date_ranges:
             message = f"Could not split date range {start_date} to {end_date} for region download. No download performed."
             log_func(f"WARNING: {message}")
             self.write_log_to_csv([self.session_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "", start_date, "Failed (Region Date Split)", end_date, message], csv_filename)
             return

        log_func(f"Total chunks: {total_chunks}, Regions per chunk: {len(regions_to_process)}")

        for i, (from_date_chunk, to_date_chunk) in enumerate(date_ranges):
            chunk_num = i + 1
            log_func(f"--- Starting Region Chunk {chunk_num}/{total_chunks}: {from_date_chunk} to {to_date_chunk} ---")

            chunk_success_count = 0
            chunk_fail_count = 0

            # Check session validity before starting the region loop for this chunk
            if not self.is_session_valid():
                log_func(f"ERROR: WebDriver session invalid before starting regions for chunk {chunk_num}. Stopping.")
                # Mark all regions in this chunk and subsequent chunks as failed?
                # This might be complex to log accurately per region. Log overall failure.
                break # Stop processing chunks

            for region_idx in regions_to_process:
                 region_name = regions_data[region_idx]['name']
                 log_func(f"--- Processing Region: {region_name} (Index: {region_idx}) for Chunk {chunk_num} ---")

                 # Call the single region download method (which includes retries)
                 try:
                     # Pass the single index, not the list
                     if self.download_report_for_region(report_url, from_date_chunk, to_date_chunk, region_idx, status_callback=log_func):
                          chunk_success_count += 1
                     else:
                          chunk_fail_count += 1
                          # Failure logged by download_report_for_region
                 except WebDriverException as wd_region_e:
                     # Catch session errors during the region loop
                     chunk_fail_count += 1
                     error_msg = f"WebDriver ERROR processing Region {region_name} in Chunk {chunk_num}: {type(wd_region_e).__name__} - {str(wd_region_e)[:150]}..."
                     log_func(error_msg)
                     traceback.print_exc()
                     # Log specific failure for this region/chunk
                     self.write_log_to_csv([self.session_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "", from_date_chunk, f"Failed (Region: {region_name}, WebDriver Error)", to_date_chunk, error_msg], csv_filename)
                     if "invalid session id" in str(wd_region_e).lower():
                         log_func("FATAL: Session became invalid during region processing. Stopping all.")
                         # Need a way to break out of outer loops or signal failure
                         raise wd_region_e # Re-raise to potentially stop everything

                 except Exception as e_region:
                     chunk_fail_count += 1
                     error_msg = f"UNEXPECTED ERROR processing Region {region_name} in Chunk {chunk_num}: {type(e_region).__name__} - {e_region}"
                     log_func(error_msg)
                     traceback.print_exc()
                     self.write_log_to_csv([self.session_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "", from_date_chunk, f"Failed (Region: {region_name}, Unexpected)", to_date_chunk, error_msg], csv_filename)
                     # Consider if unexpected errors should stop the whole process

                 finally:
                      # Pause briefly between regions within a chunk if needed
                      if len(regions_to_process) > 1:
                           log_func(f"Pausing {SHORT_WAIT}s before next region...")
                           time.sleep(SHORT_WAIT)
                           # Check session validity between regions too?
                           if not self.is_session_valid():
                               log_func(f"ERROR: WebDriver session invalid after processing region {region_name}. Stopping chunk.")
                               break # Stop processing regions for this chunk

            log_func(f"--- Completed Region Chunk {chunk_num}/{total_chunks}. Success: {chunk_success_count}, Failed: {chunk_fail_count} regions ---")

        log_func("Finished processing all chunks for selected regions.")


    # --- Session Check & Cleanup ---
    def is_session_valid(self):
        """Checks if the WebDriver session is still active."""
        if not self.driver:
            return False
        try:
            # Accessing a simple property like title or current_url
            # should throw an exception if the session is invalid.
            _ = self.driver.current_url
            return True
        except WebDriverException as e:
            # Check for specific session errors
            if "invalid session id" in str(e).lower() or \
               "session deleted because of page crash" in str(e).lower() or \
               "unable to connect to renderer" in str(e).lower():
                self._log(f"WebDriver session check failed: {e}")
                return False
            else:
                # Other WebDriver errors might not mean session is dead
                self._log(f"WebDriver check encountered non-session error: {e}")
                return True # Assume session is still valid unless explicitly invalid
        except Exception as e:
             self._log(f"Unexpected error during session check: {e}")
             return False # Assume invalid on unexpected errors

    def close(self):
        """Quits the WebDriver session gracefully."""
        if self.driver:
            try:
                self._log("Closing WebDriver session...")
                self.driver.quit()
                self._log("WebDriver session closed.")
            except WebDriverException as e:
                self._log(f"Error closing WebDriver session: {e}")
            except Exception as e:
                 self._log(f"Unexpected error closing WebDriver session: {e}")
            finally:
                self.driver = None
                self.wait = None
        else:
             self._log("WebDriver session already closed or not initialized.")


# --- Standalone Functionality (Removed or Commented Out if Not Used) ---
# class Functionality:
#    ... (Keep if needed for other purposes) ...
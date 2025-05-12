from flask import Blueprint, request, jsonify, Response, stream_with_context, current_app # type: ignore
import threading
import time
import os
import json
import traceback
from datetime import datetime, timezone, timedelta
from apscheduler.jobstores.base import JobLookupError # type: ignore
from apscheduler.triggers.date import DateTrigger # type: ignore
from selenium.common.exceptions import WebDriverException # Added
import csv # Import csv for get_download_logs fallback
import pandas as pd
import numpy as np

# --- Local Imports --- 
# Assuming these are in the root directory or accessible
# Adjust paths if necessary (e.g., from .. import config)
import config
import link_report
from logic_download import WebAutomation, regions_data, DownloadFailedException # Added
from utils import load_configs, save_configs, stream_status_update # Import from utils

# --- Remove direct import from app --- 
# from app import lock, status_messages, is_running 

# Placeholder cho các biến global - Cần cơ chế quản lý tốt hơn (app context, DI)
status_messages = []
is_running = False
lock = threading.Lock() # Mỗi blueprint có lock riêng? Hay dùng chung từ app?

# --- Blueprint Definition ---
download_bp = Blueprint('download', __name__, url_prefix='/download')

# --- Utility Functions (Cần xem xét vị trí đặt) ---
# Ví dụ: stream_status_update, load_configs, save_configs có thể ở module riêng

# --- Download Process Function (Uses current_app) ---
def run_download_process(params):
    """Main download function executed in a background thread."""
    # --- Remove global usage ---
    # global is_running, status_messages, lock 
    automation = None
    process_successful = True

    try:
        lock = current_app.lock
        shared_state = current_app.shared_state
        status_list = current_app.status_messages # Get the list reference

        # --- Setup within Lock ---
        with lock:
            if shared_state['is_running']: 
                print("Download process already running, exiting new thread request.")
                return
            shared_state['is_running'] = True # Modify shared state dict
            status_list.clear() # Clear the shared list

        # Use the utility function which now uses current_app
        stream_status_update("Starting report download process...")

        # --- Extract Parameters ---
        email = params['email']
        password = params['password']
        reports_to_download = params.get('reports', [])
        selected_regions_indices_str = params.get('regions', [])

        if not reports_to_download:
            raise ValueError("No reports configured for download.")

        # --- Prepare Download Folder ---
        timestamp_folder = "001" + datetime.now().strftime("%Y%m%d")
        specific_download_folder = os.path.join(config.DOWNLOAD_BASE_PATH, timestamp_folder)
        try:
            os.makedirs(specific_download_folder, exist_ok=True)
            stream_status_update(f"Download folder for this run: {specific_download_folder}")
        except OSError as e:
            raise RuntimeError(f"Failed to create download directory '{specific_download_folder}': {e}")

        # --- Initialize Automation ---
        stream_status_update("Initializing browser automation...")
        automation = WebAutomation(config.DRIVER_PATH, specific_download_folder, status_callback=stream_status_update)

        # --- Login ---
        stream_status_update(f"Logging in with user: {email}...")
        first_report_info = reports_to_download[0]
        first_report_url = link_report.get_report_url(first_report_info.get('report_type'))
        if not first_report_url:
            raise ValueError(f"Could not find URL for initial report type '{first_report_info.get('report_type')}' needed for login.")
        if not config.OTP_SECRET:
            raise ValueError("OTP_SECRET is not configured.")

        if not automation.login(first_report_url, email, password, config.OTP_SECRET, status_callback=stream_status_update):
            raise RuntimeError("Login failed after multiple attempts. Cannot proceed.")
        stream_status_update("Login successful.")

        # --- Download Reports Loop ---
        for report_info in reports_to_download:
            report_type_key = report_info.get('report_type')
            from_date = report_info.get('from_date')
            to_date = report_info.get('to_date')
            chunk_size_str = report_info.get('chunk_size', '5') 

            if not all([report_type_key, from_date, to_date]):
                 stream_status_update(f"Warning: Skipping report entry due to missing info: {report_info}")
                 process_successful = False
                 continue

            chunk_size = 5
            try:
                if isinstance(chunk_size_str, str) and chunk_size_str.lower() == 'month':
                    chunk_size = 'month'
                elif chunk_size_str:
                    chunk_size_days = int(chunk_size_str)
                    chunk_size = chunk_size_days if chunk_size_days > 0 else 5
            except (ValueError, TypeError):
                stream_status_update(f"Warning: Invalid chunk size '{chunk_size_str}' for '{report_type_key}'. Using default: 5 days.")
                chunk_size = 5

            report_url = link_report.get_report_url(report_type_key)
            if not report_url:
                stream_status_update(f"Error: Could not find URL for report type '{report_type_key}'. Skipping.")
                process_successful = False
                continue

            stream_status_update(f"--- Starting download for report: {report_type_key} ---")
            stream_status_update(f"Date Range: {from_date} to {to_date}, Chunk Size/Mode: {chunk_size}")

            report_failed = False
            try:
                if report_url in config.REGION_REQUIRED_REPORT_URLS:
                    if not selected_regions_indices_str:
                        stream_status_update(f"Error: Report '{report_type_key}' requires region selection, but none provided. Skipping.")
                        report_failed = True
                    else:
                        try:
                            selected_regions_indices_int = [int(idx) for idx in selected_regions_indices_str]
                            region_names = [regions_data[i]['name'] for i in selected_regions_indices_int if i in regions_data]
                            stream_status_update(f"Downloading '{report_type_key}' for regions: {', '.join(region_names)}")

                            if hasattr(automation, 'download_reports_for_all_regions'):
                                automation.download_reports_for_all_regions(
                                    report_url, from_date, to_date, chunk_size,
                                    region_indices=selected_regions_indices_int,
                                    status_callback=stream_status_update
                                )
                            else:
                                stream_status_update("ERROR: 'download_reports_for_all_regions' method missing.")
                                report_failed = True
                        except (ValueError, TypeError, KeyError) as region_err:
                            stream_status_update(f"Error processing region indices for '{report_type_key}': {region_err}. Skipping.")
                            report_failed = True
                elif report_type_key == "FAF001 - Sales Report" and hasattr(automation, 'download_reports_in_chunks_1'):
                    automation.download_reports_in_chunks_1(report_url, from_date, to_date, chunk_size, stream_status_update)
                elif report_type_key == "FAF004N - Internal Rotation Report (Imports)" and hasattr(automation, 'download_reports_in_chunks_4n'):
                     automation.download_reports_in_chunks_4n(report_url, from_date, to_date, chunk_size, stream_status_update)
                elif report_type_key == "FAF004X - Internal Rotation Report (Exports)" and hasattr(automation, 'download_reports_in_chunks_4x'):
                     automation.download_reports_in_chunks_4x(report_url, from_date, to_date, chunk_size, stream_status_update)
                elif report_type_key == "FAF002 - Dosage Report" and hasattr(automation, 'download_reports_in_chunks_2'):
                     automation.download_reports_in_chunks_2(report_url, from_date, to_date, chunk_size, stream_status_update)
                elif report_type_key == "FAF003 - Report Of Other Imports And Exports" and hasattr(automation, 'download_reports_in_chunks_3'):
                     automation.download_reports_in_chunks_3(report_url, from_date, to_date, chunk_size, stream_status_update)
                elif report_type_key == "FAF005 - Detailed Report Of Imports" and hasattr(automation, 'download_reports_in_chunks_5'):
                     automation.download_reports_in_chunks_5(report_url, from_date, to_date, chunk_size, stream_status_update)
                elif report_type_key == "FAF006 - Supplier Return Report" and hasattr(automation, 'download_reports_in_chunks_6'):
                     automation.download_reports_in_chunks_6(report_url, from_date, to_date, chunk_size, stream_status_update)
                elif report_type_key == "FAF028 - Detailed Import - Export Transaction Report" and hasattr(automation, 'download_reports_in_chunks_28'):
                     automation.download_reports_in_chunks_28(report_url, from_date, to_date, chunk_size, stream_status_update)
                elif hasattr(automation, 'download_reports_in_chunks'):
                    stream_status_update(f"Using generic chunking download logic for '{report_type_key}'.")
                    automation.download_reports_in_chunks(report_url, from_date, to_date, chunk_size, stream_status_update)
                else:
                    stream_status_update(f"ERROR: No suitable download method found for report type '{report_type_key}'. Skipping.")
                    report_failed = True

            except DownloadFailedException as report_err:
                 stream_status_update(f"ERROR downloading report {report_type_key}: {report_err}")
                 report_failed = True
            except WebDriverException as wd_err:
                 stream_status_update(f"ERROR (WebDriver) during download of {report_type_key}: {wd_err}")
                 report_failed = True
                 traceback.print_exc()
                 if "invalid session id" in str(wd_err).lower():
                     stream_status_update("FATAL: Session invalid. Stopping further report downloads for this run.")
                     process_successful = False
                     break 
            except Exception as generic_err:
                 stream_status_update(f"FATAL UNEXPECTED ERROR during processing of {report_type_key}: {generic_err}")
                 report_failed = True
                 traceback.print_exc()

            if report_failed:
                process_successful = False
                stream_status_update(f"--- Download FAILED for report: {report_type_key} ---")
            else:
                stream_status_update(f"--- Download COMPLETED for report: {report_type_key} ---")
        # --- End of Reports Loop ---

    except (RuntimeError, ValueError, WebDriverException, AttributeError, KeyError) as setup_err:
        # Added AttributeError/KeyError for current_app access issues
        error_message = f"A critical error occurred during setup or login: {setup_err}"
        # Use stream_status_update carefully here, as current_app might be the problem
        print(f"FATAL ERROR: {error_message}") 
        traceback.print_exc()
        process_successful = False
    except Exception as e:
        error_message = f"An unexpected critical error occurred: {e}"
        print(f"FATAL ERROR: {error_message}")
        traceback.print_exc()
        process_successful = False

    finally:
        if automation:
            try:
                stream_status_update("Attempting to close browser...")
                automation.close()
            except Exception as close_e:
                stream_status_update(f"CRITICAL ERROR: Failed to close browser session properly: {close_e}")
                traceback.print_exc()

        final_message = "PROCESS FINISHED: "
        final_message += "All requested reports attempted."
        if not process_successful:
             final_message += " One or more errors occurred. Please review logs and CSV file."
        else:
             final_message += " Check logs and CSV file for individual report status."
        stream_status_update(f"--- {final_message} ---")

        try:
            # Reset running state using current_app
            with current_app.lock:
                current_app.shared_state['is_running'] = False
        except (AttributeError, KeyError) as final_e:
             print(f"Error resetting running state via current_app: {final_e}")

# --- Scheduled Task Trigger (Uses current_app implicitly via load_configs) ---
def trigger_scheduled_download(config_name):
    """Loads a saved configuration and starts the download process."""
    # This function runs outside a normal request context, but APScheduler 
    # might run it in a way current_app is available, or load_configs/run_download might fail.
    # A more robust approach might pass the app instance or necessary config.
    print(f"Scheduler attempting job for config: {config_name}")
    
    try:
        lock = current_app.lock
        shared_state = current_app.shared_state
        # Check if already running
        with lock:
            if shared_state['is_running']:
                print(f"Scheduler: Download process already running. Skipping job for '{config_name}'.")
                return

        # load_configs uses current_app implicitly now
        configs = load_configs() 
        params = configs.get(config_name)

        if not params:
            print(f"Scheduler: Configuration '{config_name}' not found.")
            return

        required_keys = ['email', 'password', 'reports']
        if not all(key in params for key in required_keys) or not isinstance(params['reports'], list):
             print(f"Scheduler: Config '{config_name}' missing required keys or 'reports' is not a list.")
             return
        if not params['reports']:
            print(f"Scheduler: Config '{config_name}' has no reports defined.")
            return

        print(f"Scheduler: Starting download thread for config '{config_name}'...")
        thread_params = params.copy()
        # run_download_process needs an app context to work now.
        # We need to ensure the thread runs within an app context.
        app = current_app._get_current_object() # Get the actual app instance
        
        def run_with_context(app, params):
             with app.app_context():
                 run_download_process(params)

        scheduled_thread = threading.Thread(target=run_with_context, args=(app, thread_params,))
        scheduled_thread.daemon = True
        scheduled_thread.start()

    except Exception as e:
        # Catch potential errors accessing current_app outside context
        print(f"Scheduler ERROR for job '{config_name}': {e}")
        traceback.print_exc()

# --- Routes (Use current_app) ---

@download_bp.route('/get-reports-regions', methods=['GET'])
def get_reports_regions():
    from link_report import get_report_url
    report_urls = get_report_url()
    report_types = list(report_urls.keys())
    report_urls_map = report_urls
    region_required_urls = []  # Bổ sung logic nếu cần
    regions = {"1": "North", "2": "South"}
    return jsonify({
        "reports": report_types,
        "report_urls_map": report_urls_map,
        "region_required_urls": region_required_urls,
        "regions": regions
    })

@download_bp.route('/start-download', methods=['POST'])
def handle_start_download():
    """Handles the request to start the download process."""
    # --- Remove global --- 
    # global is_running, lock
    try:
        lock = current_app.lock
        shared_state = current_app.shared_state
        with lock:
            if shared_state['is_running']:
                return jsonify({"status": "error", "message": "Download process already running."}), 409

        params = request.get_json()
        if not params:
            return jsonify({"status": "error", "message": "Missing request data."}) , 400

        if not all(k in params for k in ('email', 'password', 'reports')):
            return jsonify({"status": "error", "message": "Missing required parameters (email, password, reports)."}), 400
        if not isinstance(params['reports'], list) or not params['reports']:
            return jsonify({"status": "error", "message": "'reports' must be a non-empty list."}), 400

        # Run download in a separate thread within app context
        app = current_app._get_current_object()
        def run_with_context(app, params):
             with app.app_context():
                 run_download_process(params)
        
        thread = threading.Thread(target=run_with_context, args=(app, params,), daemon=True)
        thread.start()

        return jsonify({"status": "success", "message": "Download process started in background."}) , 202
    except Exception as e:
        current_app.logger.error(f"Error starting download: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": "Failed to start download process"}), 500

@download_bp.route('/stream-status')
def stream_status_events():
    """Streams status messages using Server-Sent Events (SSE)."""
    # --- Remove global --- 
    # global status_messages, lock
    def event_stream():
        last_sent_count = 0
        while True:
            try:
                # Access shared state via current_app within the loop
                lock = current_app.lock
                status_messages_list = current_app.status_messages
                shared_state = current_app.shared_state
                
                with lock:
                    current_count = len(status_messages_list)
                    new_messages = status_messages_list[last_sent_count:]
                    is_process_active = shared_state['is_running']

                if new_messages:
                    for msg in new_messages:
                        yield f"data: {json.dumps({'message': msg})}\n\n"
                    last_sent_count = current_count
                
                # Check finish condition
                if not is_process_active and last_sent_count == current_count:
                    time.sleep(0.1) # Brief pause
                    with lock:
                         final_process_check = shared_state['is_running']
                         final_message_count = len(status_messages_list)
                    if not final_process_check and last_sent_count == final_message_count:
                         yield f"data: FINISHED\n\n"
                         break # Exit loop
            except (AttributeError, KeyError, RuntimeError) as e:
                 print(f"SSE Error accessing current_app: {e}. Stream might stop.")
                 # Decide how to handle context loss - maybe break?
                 yield f"data: {json.dumps({'error': 'Server stream error'})}\n\n"
                 break # Stop streaming on error
            except Exception as e:
                 print(f"Unexpected SSE Error: {e}")
                 yield f"data: {json.dumps({'error': 'Unexpected server stream error'})}\n\n"
                 break # Stop streaming on error

            time.sleep(1)

    resp = Response(stream_with_context(event_stream()), mimetype='text/event-stream')
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'
    return resp

@download_bp.route('/get-logs', methods=['GET'])
def get_download_logs():
    """Retrieves download log entries, handling potential NaN values."""
    try:
        log_file = current_app.config['LOG_FILE_PATH'] 
        logs = []
        max_logs = int(request.args.get('limit', 100))
        if os.path.exists(log_file):
            try:
                # Read CSV, explicitly handle potential NaNs
                df = pd.read_csv(log_file, keep_default_na=True) # keep_default_na=True is default, but explicit
                # Replace NaN/NaT values with None (which becomes JSON null)
                df = df.replace({pd.NA: None, pd.NaT: None})
                # Replace numpy.nan just in case
                df = df.replace({np.nan: None})
                
                # Get the last N logs
                logs = df.tail(max_logs).to_dict('records')
                 # Optional: Sort logs if needed (client-side might be better for performance)
                # try:
                #     df['TimestampParsed'] = pd.to_datetime(df['Timestamp'], errors='coerce')
                #     df_sorted = df.sort_values(by='TimestampParsed', ascending=False, na_position='last')
                #     logs = df_sorted.drop(columns=['TimestampParsed']).tail(max_logs).to_dict('records')
                # except KeyError: # Handle if Timestamp column doesn't exist
                #     logs = df.tail(max_logs).to_dict('records')
            except ImportError:
                current_app.logger.warning("Pandas not installed. Falling back to basic CSV reading.")
                # Fallback might still have issues if CSV contains literal 'NaN'
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        all_logs = list(reader)
                        # Manually replace potential string 'NaN' or empty strings if needed
                        cleaned_logs = []
                        for row in all_logs[-max_logs:]:
                            cleaned_row = {k: (None if v in ['NaN', ''] else v) for k, v in row.items()}
                            cleaned_logs.append(cleaned_row)
                        logs = cleaned_logs
                except Exception as e:
                     current_app.logger.error(f"Error reading log file {log_file}: {e}")
                     return jsonify({"error": f"Could not read log file: {e}"}), 500
            except Exception as e:
                 current_app.logger.error(f"Error processing log file {log_file}: {e}")
                 traceback.print_exc() # Log full traceback for pandas errors
                 return jsonify({"error": f"Could not process log file: {e}"}), 500
        else:
            current_app.logger.info(f"Log file not found at {log_file}")
        # Return the list directly, which jsonify handles correctly
        return jsonify(logs) 
    except Exception as e:
        current_app.logger.error(f"Error in get_download_logs: {e}")
        traceback.print_exc()
        return jsonify({"error": "Failed to retrieve logs"}), 500

@download_bp.route('/get-configs', methods=['GET'])
def get_configs():
    config_path = os.path.join(current_app.root_path, 'configs.json')
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            configs = json.load(f)
        return jsonify(list(configs.keys()))
    return jsonify([])

@download_bp.route('/save-config', methods=['POST'])
def save_config():
    """Saves a new configuration or updates an existing one."""
    data = request.get_json()
    if not data or 'name' not in data or 'config' not in data:
        return jsonify({'status': 'error', 'message': 'Invalid data. Required: {"name": "config_name", "config": {...}}'}), 400
    config_name = data['name']
    config_data = data['config']
    if not isinstance(config_data, dict) or not all(k in config_data for k in ('email', 'password', 'reports')):
         return jsonify({'status': 'error', 'message': 'Config data must include email, password, and reports.'}), 400
    try:
        configs = load_configs()
        configs[config_name] = config_data
        save_configs(configs) # Uses current_app implicitly
        return jsonify({'status': 'success', 'message': f'Configuration "{config_name}" saved.'})
    except Exception as e:
        current_app.logger.error(f"Error saving config '{config_name}': {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f'Failed to save config: {e}'}), 500

@download_bp.route('/load-config/<config_name>', methods=['GET'])
def load_config(config_name):
    """Loads a specific saved configuration."""
    try:
        configs = load_configs()
        config_data = configs.get(config_name)
        if config_data:
            return jsonify(config_data)
        else:
            return jsonify({'status': 'error', 'message': 'Configuration not found.'}), 404
    except Exception as e:
        current_app.logger.error(f"Error loading config '{config_name}': {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f'Failed to load config: {e}'}), 500

@download_bp.route('/delete-config/<config_name>', methods=['DELETE'])
def delete_config(config_name):
    """Deletes a saved configuration."""
    try:
        configs = load_configs()
        if config_name in configs:
            del configs[config_name]
            save_configs(configs)
            return jsonify({'status': 'success', 'message': f'Configuration "{config_name}" deleted.'})
        else:
            return jsonify({'status': 'error', 'message': 'Configuration not found.'}), 404
    except Exception as e:
        current_app.logger.error(f"Error deleting config '{config_name}': {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f'Failed to delete config: {e}'}), 500

@download_bp.route('/schedule-job', methods=['POST'])
def schedule_job():
    """Schedules a download job."""
    data = request.get_json()
    if not data or 'config_name' not in data or 'run_datetime' not in data:
        return jsonify({'status': 'error', 'message': 'Missing config_name or run_datetime.'}), 400
    config_name = data['config_name']
    run_datetime_str = data['run_datetime']
    try:
        lock = current_app.lock
        scheduler = current_app.scheduler # Access scheduler via context
        
        if not run_datetime_str: return jsonify({'status': 'error', 'message': 'Run date/time required.'}), 400
        configs = load_configs()
        if config_name not in configs:
             return jsonify({'status': 'error', 'message': f'Configuration "{config_name}" not found.'}), 404

        job_id = f"sched_{config_name.replace(' ','_').lower()}_{int(time.time())}"
        try:
            run_datetime_naive = datetime.fromisoformat(run_datetime_str)
            if run_datetime_naive <= datetime.now() + timedelta(seconds=60):
                return jsonify({'status': 'error', 'message': 'Scheduled time must be > 1 min in the future.'}), 400
            trigger = DateTrigger(run_date=run_datetime_naive)
        except ValueError:
             return jsonify({'status': 'error', 'message': 'Invalid date/time format (YYYY-MM-DDTHH:MM).'}), 400

        with lock: 
            scheduler.add_job(
                func=trigger_scheduled_download, trigger=trigger, args=[config_name],
                id=job_id, name=f"Download: {config_name}", replace_existing=False,
                misfire_grace_time=600 
            )
        current_app.logger.info(f"Successfully added job {job_id} to scheduler.")
        return jsonify({'status': 'success', 'message': f'Job scheduled for config "{config_name}".', 'job_id': job_id})

    except Exception as e:
        current_app.logger.error(f"Error scheduling job: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f'Failed to schedule job: {e}'}), 500

@download_bp.route('/get-schedules', methods=['GET'])
def get_schedules():
    """Gets the list of currently scheduled jobs."""
    try:
        lock = current_app.lock
        scheduler = current_app.scheduler
        jobs_info = []
        with lock: 
            jobs = scheduler.get_jobs()
            for job in jobs:
                next_run_iso = None
                if job.next_run_time:
                    try: 
                        next_run_iso = job.next_run_time.isoformat()
                    except Exception as fmt_e:
                        current_app.logger.error(f"Error formatting next_run_time for job {job.id}: {fmt_e}")
                        next_run_iso = str(job.next_run_time)
                jobs_info.append({
                    'id': job.id, 'name': job.name,
                    'next_run_time': next_run_iso,
                    'trigger': str(job.trigger),
                    'args': job.args 
                })
        return jsonify({'status': 'success', 'schedules': jobs_info})
    except Exception as e:
        current_app.logger.error(f"Error getting schedules: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f'Failed to get schedules: {e}'}), 500

@download_bp.route('/cancel-schedule/<job_id>', methods=['DELETE'])
def cancel_schedule(job_id):
    """Cancels (removes) a scheduled job."""
    try:
        lock = current_app.lock
        scheduler = current_app.scheduler
        current_app.logger.info(f"Received request to cancel job: {job_id}")
        with lock: 
            scheduler.remove_job(job_id)
        current_app.logger.info(f"Removed job {job_id} from scheduler.")
        return jsonify({'status': 'success', 'message': f'Job "{job_id}" cancelled.'})
    except JobLookupError:
        current_app.logger.warning(f"Job {job_id} not found for cancellation.")
        return jsonify({'status': 'success', 'message': f'Job "{job_id}" not found (already run or cancelled).'})
    except Exception as e:
        current_app.logger.error(f"Error cancelling job {job_id}: {e}")
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f'Failed to cancel job "{job_id}": {e}'}), 500

@download_bp.route('/get-advanced-settings', methods=['GET'])
def get_advanced_settings():
    return jsonify({
        'otp_secret': getattr(config, 'OTP_SECRET', ''),
        'driver_path': getattr(config, 'DRIVER_PATH', ''),
        'download_base_path': getattr(config, 'DOWNLOAD_BASE_PATH', '')
    })

# --- Other necessary functions/logic for download ---
# (Could add more helper functions specific to download here if needed)

# --- Other necessary functions/logic for download ---
# Ví dụ: Các hàm xử lý logic download cụ thể nếu không đặt trong run_download_process
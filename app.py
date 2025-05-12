# filename: app.py
import flask # type: ignore
from flask import Flask, render_template, request, jsonify, Response, session, flash, redirect, url_for, current_app # Added current_app just in case
import threading
import time
import csv
import os
# import pyotp # No longer used directly in app.py?
from datetime import datetime, timezone, timedelta
# import pandas as pd # No longer used directly in app.py?
import json
import traceback
import atexit
from selenium.common.exceptions import WebDriverException # Keep for now, might be needed elsewhere

# Scheduling Imports
from apscheduler.schedulers.background import BackgroundScheduler # type: ignore
from apscheduler.jobstores.memory import MemoryJobStore # type: ignore
from apscheduler.triggers.date import DateTrigger # type: ignore
from apscheduler.executors.pool import ThreadPoolExecutor # type: ignore
from apscheduler.jobstores.base import JobLookupError # Keep for now

# Local Imports
import config
# from logic_download import WebAutomation, regions_data, DownloadFailedException # Moved to blueprint
# import link_report # Moved to blueprint

# Import utility functions
from utils import load_configs, save_configs, stream_status_update

# --- Define Constants and Shared Globals BEFORE app creation ---
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'configs.json')
LOG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'download_log.csv')

lock = threading.Lock() # Shared lock
status_messages = []    # Shared status list (mutable)
scheduler = BackgroundScheduler( # Shared scheduler
    jobstores={'default': MemoryJobStore()},
    executors={'default': ThreadPoolExecutor(2)},
    job_defaults={'coalesce': True, 'max_instances': 1},
    timezone=timezone.utc
)

# Use a dictionary for shared mutable state like booleans
shared_state = {
    'is_running': False
}

# --- Create Flask App ---
app = Flask(__name__)
app.secret_key = 'your_secret_key_here' # Đặt secret key cho session/flash

# --- Attach Shared Resources to App Context ---
app.config['CONFIG_FILE_PATH'] = CONFIG_FILE_PATH
app.config['LOG_FILE_PATH'] = LOG_FILE_PATH
app.lock = lock # Attach the lock object
app.scheduler = scheduler # Attach the scheduler object
app.status_messages = status_messages # Attach the actual status list
app.shared_state = shared_state # Attach the shared state dictionary

# --- Import Blueprints AFTER app is created and configured ---
from blueprints.email.routes_email import email_bp
from blueprints.download import download_bp # Import the new download blueprint

# --- Register Blueprints ---
app.register_blueprint(email_bp, url_prefix='/email')
app.register_blueprint(download_bp) # url_prefix='/download' is defined in the blueprint itself

# --- Import Google Sheet Auth (AFTER app creation if needed) ---
from auth_google_sheet import is_user_allowed, check_user_credentials, update_user_password, get_user_auth_data

# --- Flask Routes (Core App Routes) ---
# Auth routes remain here
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        # Check credentials first
        if check_user_credentials(email, password):
            # Credentials OK, now fetch auth data (role/permissions)
            auth_data = get_user_auth_data(email)
            if auth_data:
                session['user_email'] = email
                session['user_role'] = auth_data.get('role')
                session['user_permissions'] = auth_data.get('permissions', []) # Store permissions list
                print(f"Login successful for {email}. Role: {session['user_role']}, Permissions: {session['user_permissions']}")
                return redirect(url_for('index'))
            else:
                # Should not happen if check_user_credentials passed, but handle defensively
                flash('Could not retrieve user authorization data after login.', 'error')
                print(f"Error: Could not get auth data for {email} even after credentials check.")
        else:
            flash('Invalid email or password.', 'danger') # Changed category for consistency
    # GET request or failed login
    return render_template('login.html')

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if request.method == 'POST':
        email = request.form['email']
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        if not (email and old_password and new_password):
            flash('Please fill in all fields.')
            return render_template('change_password.html')

        if not check_user_credentials(email, old_password):
             flash('Incorrect old password or email.')
        return render_template('change_password.html')

        try:
            update_user_password(email, new_password)
            flash('Password changed successfully!')
            return redirect(url_for('login'))
        except ValueError as e:
             flash(str(e))
             return render_template('change_password.html')
        except Exception as e:
             flash(f'An error occurred: {e}')
             return render_template('change_password.html')
    return render_template('change_password.html')

@app.route('/logout')
def logout():
    session.pop('user_email', None)
    return redirect(url_for('login'))

# Index route remains here
@app.route('/')
def index():
    if 'user_email' not in session:
        return redirect(url_for('login'))
    
    # Check permission using session data
    user_role = session.get('user_role')
    user_permissions = session.get('user_permissions', []) # Default to empty list
    required_permission = 'web_access' # Permission needed for this page

    # Grant access if role is owner OR specific permission exists
    if not (user_role == 'owner' or required_permission in user_permissions):
        flash("You don't have permission to access this page.", 'danger')
        print(f"Access denied for {session['user_email']} to /. Role: {user_role}, Permissions: {user_permissions}")
        return redirect(url_for('login')) 

    import config
    return render_template(
        'index.html',
        templates={},
        default_email=getattr(config, 'DEFAULT_EMAIL', ''),
        default_password=getattr(config, 'DEFAULT_PASSWORD', '')
    )

# --- Download Routes Moved to blueprints/download.py ---

# --- Main Execution ---
if __name__ == '__main__':
    # Initial Setup using app context where possible (though app context isn't fully active yet)
    # Use the config directly for initial path check
    try:
        os.makedirs(config.DOWNLOAD_BASE_PATH, exist_ok=True)
    except OSError as e:
        print(f"CRITICAL ERROR: Could not create base download directory '{config.DOWNLOAD_BASE_PATH}': {e}")
        exit(1)
    # Use constant path here, save_configs uses current_app later if needed within context
    if not os.path.exists(CONFIG_FILE_PATH):
        print(f"Configuration file not found at {CONFIG_FILE_PATH}. Creating empty file.")
        # Directly create empty file, avoid utils needing app context here
        try:
            with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump({}, f)
        except IOError as e:
             print(f"CRITICAL ERROR: Could not create initial config file: {e}")
             exit(1)

    # Start Scheduler
    # Use the global scheduler object directly
    if not scheduler.running:
        try:
            scheduler.start(paused=False) 
            print("APScheduler started successfully.")
            atexit.register(lambda: scheduler.shutdown())
            print("Registered APScheduler shutdown hook.")
        except Exception as e:
            print(f"CRITICAL ERROR: Failed to start APScheduler: {e}")
            traceback.print_exc()

    # Run Flask App
    print("Starting Flask application...")
    HOST = '127.0.0.1'
    PORT = 5000
    try:
        from waitress import serve
        print(f"Running with Waitress WSGI server on http://{HOST}:{PORT}")
        serve(app, host=HOST, port=PORT, threads=10, channel_timeout=1800)
    except ImportError:
        print("\n--- WARNING ---")
        print("Waitress not found (pip install waitress). Using Flask's development server.")
        print("Flask's development server is NOT suitable for production.")
        print("---------------\n")
        app.run(debug=False, host=HOST, port=PORT, threaded=True, use_reloader=False)
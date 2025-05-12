import os 
import json
from datetime import datetime
import threading # Keep for type hinting if needed, but lock comes from current_app
from flask import current_app # Import current_app

# --- Remove direct import from app ---
# from app import lock, status_messages, CONFIG_FILE_PATH

def load_configs():
    """Loads configurations safely using app context."""
    config_path = current_app.config['CONFIG_FILE_PATH']
    if not os.path.exists(config_path): return {}
    try:
        # Access lock from the app context
        with current_app.lock: 
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content: return {}
                return json.loads(content)
    except (json.JSONDecodeError, IOError, AttributeError, KeyError) as e:
        # Added AttributeError/KeyError for cases where current_app isn't fully loaded or configured
        print(f"Error loading config file via current_app ({config_path}): {e}")
        return {}

def save_configs(configs):
    """Saves configurations safely using app context."""
    config_path = current_app.config['CONFIG_FILE_PATH']
    try:
        # Access lock from the app context
        with current_app.lock: 
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(configs, f, indent=4, ensure_ascii=False)
    except (IOError, AttributeError, KeyError) as e:
        print(f"Error saving config file via current_app ({config_path}): {e}")

def stream_status_update(message):
    """Adds a message to the status list via app context."""
    # --- Remove global usage ---
    # global status_messages, lock 
    try:
        # Access lock and status_messages list from the app context
        lock = current_app.lock
        status_list = current_app.status_messages 
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_message = f"{timestamp}: {message}"
        print(full_message) # Log to console
        with lock:
            status_list.append(full_message)
            MAX_LOG_MESSAGES = 500 # Consider moving to app.config
            if len(status_list) > MAX_LOG_MESSAGES:
                # Modify the list attached to the app directly
                current_app.status_messages = status_list[-MAX_LOG_MESSAGES:] 
    except (AttributeError, KeyError) as e:
         print(f"Error updating status via current_app: {e}. App context might not be available.") 
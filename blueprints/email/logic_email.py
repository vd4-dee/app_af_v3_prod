import csv
import os
import time
from datetime import datetime
import win32com.client as win32

# Note: Assuming config.py is in the root directory
# If not, adjust the import path accordingly (e.g., from .. import config)
from config import DEFAULT_SENDER, EMAIL_BATCH_SIZE, EMAIL_PAUSE_SECONDS, EMAIL_LOG_PATH

def send_bulk_email(csv_file_path, subject, body):
    """
    Send bulk emails via local Outlook COM.
    Reads recipients from the first column of the CSV (skips header if 'email').
    Logs each send to EMAIL_LOG_PATH and returns summary.
    """
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = EMAIL_LOG_PATH # Use path from config
    
    # Ensure log directory exists
    log_dir = os.path.dirname(log_file_path)
    if log_dir and not os.path.exists(log_dir):
        try: os.makedirs(log_dir)
        except OSError as e:
             return {'error': f'Failed to create log directory {log_dir}: {e}'}
    
    # Ensure log file with header exists
    if not os.path.exists(log_file_path):
        try:
            with open(log_file_path, 'w', newline='', encoding='utf-8') as logf:
                writer = csv.writer(logf)
                writer.writerow(['SessionID', 'Timestamp', 'Recipient', 'Status', 'ErrorMessage'])
        except IOError as e:
             return {'error': f'Failed to create log file {log_file_path}: {e}'}

    # Read recipients
    recipients = []
    try:
        with open(csv_file_path, newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            header_skipped = False
            for i, row in enumerate(reader):
                if not row:
                    continue # Skip empty rows
                val = row[0].strip()
                # Skip header row if it looks like 'email' (case-insensitive)
                if i == 0 and val.lower() == 'email':
                    header_skipped = True
                    continue
                if not val: continue # Skip rows with empty first column
                recipients.append(val)
    except FileNotFoundError:
         return {'error': f'CSV file not found: {csv_file_path}'}
    except Exception as e:
        return {'error': f'Read CSV failed: {e}'}

    if not recipients:
        return {'error': 'No valid recipients found in CSV file.'}

    # Initialize Outlook
    try:
        outlook = win32.Dispatch('Outlook.Application')
        # Optional: Check if Outlook is running or needs to be started
        # namespace = outlook.GetNamespace("MAPI")
    except Exception as e:
        return {'error': f'Outlook COM dispatch failed. Is Outlook installed and configured? Error: {e}'}

    results = []
    success_count = 0
    failure_count = 0

    batch_size = EMAIL_BATCH_SIZE if EMAIL_BATCH_SIZE > 0 else len(recipients) # Handle 0 or negative
    pause_seconds = EMAIL_PAUSE_SECONDS if EMAIL_PAUSE_SECONDS >= 0 else 0

    # Send in batches
    for i in range(0, len(recipients), batch_size):
        batch = recipients[i:i + batch_size]
        current_batch_num = (i // batch_size) + 1
        total_batches = (len(recipients) + batch_size - 1) // batch_size
        print(f"Processing batch {current_batch_num}/{total_batches}...")

        for recipient in batch:
            timestamp = datetime.now().isoformat()
            status = 'Success'
            error_message = ''
            try:
                mail = outlook.CreateItem(0) # 0: olMailItem
                mail.To = recipient
                mail.Subject = subject
                # Use HTMLBody for better formatting potential
                # mail.Body = body # Use this for plain text
                mail.HTMLBody = body 
                
                # Optional: Set sender based on config (requires mailbox permission)
                # if DEFAULT_SENDER:
                #    mail.SentOnBehalfOfName = DEFAULT_SENDER
                # Or set the sending account if multiple are configured:
                # sending_account = None
                # for acc in outlook.Session.Accounts:
                #     if acc.SmtpAddress == DEFAULT_SENDER:
                #         sending_account = acc
                #         break
                # if sending_account:
                #     mail.SendUsingAccount = sending_account
                # else:
                #     print(f"Warning: Sending account {DEFAULT_SENDER} not found in Outlook.")
                
                mail.Send()
                success_count += 1
                print(f"  Sent to: {recipient}")
            except Exception as e:
                status = 'Failed'
                error_message = str(e)
                failure_count += 1
                print(f"  FAILED to send to: {recipient} - Error: {error_message}")
                
            # Record result
            results.append({'recipient': recipient, 'status': status, 'error': error_message})
            # Append to log file immediately
            try:
                 with open(log_file_path, 'a', newline='', encoding='utf-8') as logf:
                    writer = csv.writer(logf)
                    writer.writerow([session_id, timestamp, recipient, status, error_message])
            except IOError as log_e:
                 print(f"CRITICAL: Failed to write to log file {log_file_path}: {log_e}")
                 # Continue sending but maybe flash a warning later?

        # Pause between batches if not the last batch
        if pause_seconds > 0 and (i + batch_size) < len(recipients):
            print(f"Pausing for {pause_seconds} seconds before next batch...")
            time.sleep(pause_seconds)

    print("Email sending process finished.")
    return {
        'session_id': session_id,
        'total': len(recipients),
        'success': success_count,
        'failed': failure_count,
        'details': results # Optionally truncate details if too large
    } 
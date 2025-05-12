from . import email_bp
from flask import render_template, request, redirect, url_for, flash, current_app
import os
import re
from .logic_email import send_bulk_email
from werkzeug.utils import secure_filename
import tempfile

# Helper function to load templates (can be improved)
def load_email_templates():
    # Consider moving 'file' dir path to config or app.config
    file_dir = os.path.join(os.getcwd(), 'file') 
    templates = {}
    if os.path.isdir(file_dir):
        for fname in os.listdir(file_dir):
            if not fname.lower().endswith('.html'): continue # Ensure it's html
            path = os.path.join(file_dir, fname)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                current_app.logger.error(f"Error reading email template {fname}: {e}")
                continue
            if not content.strip().lower().startswith('<!doctype'): 
                continue # Basic check if it looks like HTML
            m = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE)
            subject = m.group(1) if m else os.path.splitext(fname)[0]
            key = os.path.splitext(fname)[0]
            templates[key] = {'subject': subject, 'body': content}
    return templates

@email_bp.route('/bulk', methods=['GET', 'POST'])
# Renamed function and route
def bulk_email(): 
    email_templates = load_email_templates()
    
    if request.method == 'POST':
        file = request.files.get('email_list')
        scenario = request.form.get('scenario')
        
        if scenario and scenario in email_templates:
            subject = email_templates[scenario]['subject']
            body = email_templates[scenario]['body']
        else:
            subject = request.form.get('subject')
            body = request.form.get('body')
            
        if not file or not file.filename:
            flash('Email list CSV file is required.', 'danger')
            return redirect(url_for('email.bulk_email')) # Redirect back to bulk email page
        if not subject or not body:
             flash('Subject and body are required.', 'danger')
             return redirect(url_for('email.bulk_email'))
             
        filename = secure_filename(file.filename)
        if not filename.lower().endswith('.csv'):
             flash('Please upload a CSV file.', 'danger')
             return redirect(url_for('email.bulk_email'))
             
        # Use tempfile for secure temporary storage
        temp_dir = tempfile.gettempdir()
        filepath = os.path.join(temp_dir, f"bulk_email_{os.urandom(8).hex()}_{filename}")
        result = None # Initialize result

        try:
            file.save(filepath)
            result = send_bulk_email(filepath, subject, body)
        except Exception as e:
            current_app.logger.error(f"Error processing uploaded file or sending emails: {e}", exc_info=True)
            flash(f'An error occurred during processing: {e}', 'danger')
        finally:
            # Ensure temp file is removed even on error
            if os.path.exists(filepath):
                 try: 
                     os.remove(filepath)
                     print(f"Removed temp file: {filepath}")
                 except OSError as e:
                     current_app.logger.error(f"Error removing temp file {filepath}: {e}")
        
        if result:
             if 'error' in result:
                 flash(f"Error sending emails: {result['error']}", 'danger')
             else:
                 flash(f"Email sending process completed. Session: {result.get('session_id', 'N/A')}. Total: {result.get('total',0)}, Success: {result.get('success',0)}, Failed: {result.get('failed',0)}", 'success')
        # Always redirect back to the bulk email page after POST
        return redirect(url_for('email.bulk_email'))
            
    # GET request: render the bulk email form page
    return render_template('bulk_email.html', templates=email_templates)

# Optional: Add route for viewing send history if needed
# @email_bp.route('/history')
# def history():
#    # Logic to read and display EMAIL_LOG_PATH
#    try:
#        # Read EMAIL_LOG_PATH (defined in config)
#        # Paginate or limit results
#        # Pass logs to a template email/history.html
#        pass
#    except Exception as e:
#        flash(f'Error loading email history: {e}', 'danger')
#        return render_template('email/history.html', logs=[]) 
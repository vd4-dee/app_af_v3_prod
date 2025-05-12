import gspread
from google.oauth2.service_account import Credentials
import traceback

# Thay bằng tên Google Sheet thật sự của bạn
GOOGLE_SHEET_ID = '19XJsntpyJXJRYGuXMIgr6yBsw4_jT1zZ9lI8ERTCOFg'
# GOOGLE_SHEET_NAME = 'allowed_users'  # Không dùng nữa
# Đường dẫn tới file credentials JSON đã tải về
GOOGLE_CREDENTIALS_FILE = 'google-credentials.json'

# Lấy danh sách user từ Google Sheet (theo cột email)
def get_allowed_users():
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scopes)
        print("Using credentials file:", GOOGLE_CREDENTIALS_FILE)
        print("Service account email:", creds.service_account_email)
        print("Scopes:", creds.scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        worksheet = sh.worksheet('allowed_users')
        rows = worksheet.get_all_records()
        allowed_emails = set()
        for row in rows:
            email = row.get('email')
            if email:
                allowed_emails.add(email.strip().lower())
        return allowed_emails
    except Exception as e:
        print("ERROR in get_allowed_users:", e)
        raise

# Password authentication helpers

def get_user_password(email):
    """
    Returns the password for a given email from Google Sheet (plain text).
    Returns None if not found.
    """
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        worksheet = sh.worksheet('allowed_users')
        rows = worksheet.get_all_records()
        for row in rows:
            row_email = row.get('email')
            if row_email and row_email.strip().lower() == email.strip().lower():
                return row.get('password')
        return None
    except Exception as e:
        print("ERROR in get_user_password:", e)
        raise

def check_user_credentials(email, password):
    """
    Returns True if email exists and password matches (plain text).
    """
    user_password = get_user_password(email)
    if user_password is None:
        return False
    return str(password) == str(user_password)

def update_user_password(email, new_password):
    """
    Update the password for the given email in Google Sheet.
    Returns True if updated, False if not found.
    """
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        worksheet = sh.worksheet('allowed_users')
        rows = worksheet.get_all_records()
        for idx, row in enumerate(rows, start=2):  # Row 1 is header
            row_email = row.get('email')
            if row_email and row_email.strip().lower() == email.strip().lower():
                # Find the column index for 'password'
                header = worksheet.row_values(1)
                if 'password' in header:
                    col_idx = header.index('password') + 1
                    worksheet.update_cell(idx, col_idx, new_password)
                    return True
        return False
    except Exception as e:
        print("ERROR in update_user_password:", e)
        raise

def get_user_auth_data(email):
    """
    Fetches role and permissions for a given email from the Google Sheet.
    Returns a dictionary like {'role': 'owner', 'permissions': ['permission1', 'permission2']} 
    or None if the user is not found.
    """
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        worksheet = sh.worksheet('allowed_users')
        
        header = worksheet.row_values(1) 
        if 'email' not in header:
            print(f"ERROR: Column 'email' not found in sheet header.")
            return None
            
        email_col_index = header.index('email') + 1 
        permissions_col_index = header.index('permissions') + 1 if 'permissions' in header else None
        role_col_index = header.index('role') + 1 if 'role' in header else None

        user_email_lower = email.strip().lower()
        cell = worksheet.find(user_email_lower, in_column=email_col_index)
        
        if not cell:
             return None # User not found
        
        user_data = {'role': None, 'permissions': []}
        
        # Get Role
        if role_col_index:
            role_value = worksheet.cell(cell.row, role_col_index).value
            if role_value and isinstance(role_value, str):
                 user_data['role'] = role_value.strip().lower()

        # Get Permissions
        if permissions_col_index:
            permissions_string = worksheet.cell(cell.row, permissions_col_index).value
            if permissions_string and isinstance(permissions_string, str):
                 # Split, strip whitespace, convert to lower, and remove empty strings
                 user_data['permissions'] = [p.strip().lower() for p in permissions_string.split(',') if p.strip()]
        
        return user_data

    except Exception as e:
        print(f"ERROR in get_user_auth_data for {email}: {e}")
        traceback.print_exc()
        return None # Return None on error

# Hàm kiểm tra quyền (có thể giữ lại hoặc thay thế bằng kiểm tra session)
def is_user_allowed(email, permission_name):
    """
    Checks if the given email has the specified permission in the Google Sheet.
    First checks the 'role' column. If 'owner', grants access.
    Otherwise, looks for the permission string within the 'permissions' column.
    NOTE: This function will be called less often after implementing session-based checks.
    """
    user_data = get_user_auth_data(email) # Use the new function
    
    if not user_data:
        return False # User not found or error fetching data
        
    # Check Role First
    if user_data.get('role') == 'owner':
        print(f"User {email} has role 'owner', granting permission '{permission_name}'.")
        return True
        
    # Check specific permissions
    required_permission = permission_name.strip().lower()
    has_permission = required_permission in user_data.get('permissions', [])
    print(f"Checking permission '{required_permission}' for user {email}: {'Granted' if has_permission else 'Denied'} (Role: {user_data.get('role')}, Permissions list: {user_data.get('permissions')})")
    return has_permission

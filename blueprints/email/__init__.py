from flask import Blueprint

# Blueprint for Email Module
email_bp = Blueprint(
    'email', __name__,
    template_folder='templates',
    static_folder='static'
)

# Register routes
from . import routes_email
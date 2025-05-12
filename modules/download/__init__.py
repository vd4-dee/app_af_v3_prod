from flask import Blueprint

# Blueprint for Download Module

download_bp = Blueprint(
    'download', __name__,
    template_folder='templates',
    static_folder='static'
)

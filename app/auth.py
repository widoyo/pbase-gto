import functools

from flask import (Blueprint, flask, g, redirect, render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

bp = Blueprint('auth', __name__, url_prefix='/auth', template_folder='templates/auth')


@bp.route('/login', method=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db

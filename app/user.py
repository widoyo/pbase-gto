import functools

from flask import (Blueprint, flask, g, redirect, render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

bp = Blueprint('user', __name__, url_prefix='/user', template_folder='templates/auth')


@bp.route('/')
def index():


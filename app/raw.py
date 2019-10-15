from flask import Blueprint, render_template, abort, request, flash
from flask_login import login_required

from app import db
from app.models import Raw

bp = Blueprint('raw', __name__, template_folder='templates')

@bp.route('/')
@login_required
def index():
    page = int(request.args.get('p', 1))
    per_page = int(request.args.get('n', 25))
    paginate = Raw.query.paginate(page, per_page)
    return render_template('raw/index.html', pagination=paginate)



import datetime
from urllib.parse import urlparse, urljoin
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import desc

from app import app
from app.models import User, Lokasi, Periodik
from app.forms import LoginForm


@app.route('/')
def index():
    '''Menampilkan hujan terjadi terakhir
    dikelompokkan hari'''
    sejak = int(request.args.get('sejak', 90))
    mulai = (datetime.datetime.now() - datetime.timedelta(days=sejak)).replace(hour=7, minute=0)
    hujans = Periodik.query.filter(Periodik.sampling > mulai,
                                   Periodik.rain > 0).order_by(
                                       desc(Periodik.sampling))
    hujan_list = dict()
    # for h in hujans:
    #     if h.sampling.hour < 7:
    #         tg = h.sampling.date() - datetime.timedelta(days=1)
    #     else:
    #         tg = h.sampling.date()
    #     if tg not in hujan_list.keys():
    #         hujan_list[tg] = {h.device: [h.rain]}
    #     else:
    #         if h.device not in hujan_list[tg]:
    #             hujan_list[tg] = {h.device: [h.rain]}
    #         else:
    #             hujan_list[tg][h.device].append(h.rain)
    for h in hujans:
        sample = h.sampling - datetime.timedelta(hours=7)
        tg = sample.date()
        if tg not in hujan_list:
            hujan_list[tg] = {h.device: []}
        if h.device not in hujan_list[tg]:
            hujan_list[tg][h.device] = []
        hujan_list[tg][h.device].append(h.rain)

    print(hujan_list)
    return render_template('index.html', hujan_list=hujan_list,
                           hujan_sejak=sejak,
                           title='primaBase')

@app.route('/map')
@login_required
def map():
    lokasis = Lokasi.query.all()
    return render_template('map.html', lokasis=lokasis)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username/Password')
            return redirect(url_for('index'))
        login_user(user, remember=form.remember_me.data)
        next = request.args.get('next')
        if not is_safe_url(next):
            return abort(400)
        return redirect(url_for('index'))
    return render_template('auth/login.html', title='Login', form=form)


def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and \
            ref_url.netloc == test_url.netloc

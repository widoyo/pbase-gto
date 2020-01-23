import datetime
import requests
import os
from flask import Blueprint, render_template, abort, request, flash, redirect
from flask_login import login_required

from app import db
from app.models import Lokasi, Periodik, Device
from app.forms import LokasiForm

bp = Blueprint('pos', __name__, template_folder='templates')

@bp.route('/')
@login_required
def index():
    all_lokasi = Lokasi.query.all()
    return render_template('pos/index.html', all_lokasi=all_lokasi)


@bp.route('/<lokasi_id>/delete', methods=['GET', 'POST'])
@login_required
def delete(lokasi_id):
    pos = Lokasi.query.get(lokasi_id)
    form = LokasiForm(obj=pos)
    if form.validate_on_submit():
        db.session.delete(pos)
        db.session.commit()
        flash("Sukses menghapus")
        return redirect('/pos')
    return render_template('pos/delete.html', pos=pos, form=form)



@bp.route('/<lokasi_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(lokasi_id):
    pos = Lokasi.query.get(lokasi_id)
    form = LokasiForm(obj=pos)
    if form.validate_on_submit():
        pos.nama = form.nama.data
        pos.ll = form.ll.data
        db.session.commit()

        # sent post to update pweb
        post_url = f"{os.environ['PWEB_URL']}/api/lokasi"
        post_data = {
            'id': pos.id,
            'nama': pos.nama,
            'll': pos.ll,
            'jenis': pos.jenis
        }
        res = requests.post(post_url, data=post_data)
        result = res.json()
        print(result)

        flash("Sukses mengedit")
        return redirect('/pos')
    return render_template('pos/edit.html', form=form)



@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    form = LokasiForm()
    if form.validate_on_submit():
        lokasi = Lokasi(nama=form.nama.data, ll=form.ll.data)
        db.session.add(lokasi)
        db.session.commit()

        # sent post to update pweb
        post_url = f"{os.environ['PWEB_URL']}/api/lokasi"
        post_data = {
            'id': lokasi.id,
            'nama': lokasi.nama,
            'll': lokasi.ll,
            'jenis': lokasi.jenis
        }
        res = requests.post(post_url, data=post_data)
        result = res.json()
        print(result)

        flash("Sukses menambah Lokasi Pos")
        return redirect('/pos')
    return render_template('pos/add.html', form=form)


@bp.route('/<lokasi>')
@login_required
def show(lokasi):
    samp = request.args.get('sampling')
    try:
        sampling = datetime.datetime.strptime(samp, '%Y-%m-%d').date()
    except:
        sampling = datetime.date.today()
    lokasi = Lokasi.query.filter_by(id=lokasi).first_or_404()
    if lokasi.jenis == '1': # Pos Curah Hujan
        template_name = 'show_ch.html'
        try:
            hourly_rain = lokasi.hujan_hari(sampling).popitem()[1].get('hourly')
        except:
            hourly_rain = {}
        periodik = [(k, v) for k, v in hourly_rain.items()]
    elif lokasi.jenis == '2':
        template_name = 'show_tma.html'
        periodik = [l for l in lokasi.periodik]
    elif lokasi.jenis == '4':
        template_name = 'show_klim.html'
        periodik = []
    else:
        template_name = 'show.html'
        periodik = []
    return render_template('pos/' + template_name,
                           sampling=sampling,
                           lokasi=lokasi, periodik=periodik)

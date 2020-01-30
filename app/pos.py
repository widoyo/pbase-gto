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


@bp.route('/<lokasi_id>/sync', methods=['GET', 'POST'])
@login_required
def sync(lokasi_id):
    pos = Lokasi.query.get(lokasi_id)

    # sent post to update pweb
    send2primaweb(pos)

    return redirect('/pos')


@bp.route('/<lokasi_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(lokasi_id):
    pos = Lokasi.query.get(lokasi_id)
    form = LokasiForm(obj=pos)
    if form.validate_on_submit():
        pos.nama = form.nama.data
        pos.ll = form.ll.data
        pos.siaga1 = form.siaga1.data
        pos.siaga2 = form.siaga2.data
        pos.siaga3 = form.siaga3.data
        pos.jenis = form.jenis.data
        db.session.commit()

        # sent post to update pweb
        send2primaweb(pos)

        flash("Sukses mengedit")
        return redirect('/pos')
    return render_template('pos/edit.html', form=form, pos=pos)


@bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    form = LokasiForm()
    if form.validate_on_submit():
        lokasi = Lokasi(
            nama=form.nama.data,
            ll=form.ll.data,
            jenis=form.jenis.data,
            siaga1=form.siaga1.data,
            siaga2=form.siaga2.data,
            siaga3=form.siaga3.data
        )
        db.session.add(lokasi)
        db.session.commit()

        # sent post to update pweb
        send2primaweb(lokasi)

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


def send2primaweb(pos):
    # sent post to update pweb
    try:
        post_url = f"{os.environ['PWEB_URL']}/api/lokasi"
        post_data = {
            'id': pos.id,
            'nama': pos.nama,
            'll': pos.ll,
            'siaga1': pos.siaga1,
            'siaga2': pos.siaga2,
            'siaga3': pos.siaga3,
            'jenis': pos.jenis
        }
        res = requests.post(post_url, data=post_data)
        result = res.json()
        print("Update Sukses")
        print(result)
        flash("Update Sukses")
    except Exception as e:
        print(f"Update Error : {e}")
        flash(f"Update Error : {e}")

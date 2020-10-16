'''
logger module

Widoyo <widoyo@gmail.com>
'''
import datetime
import requests
import csv
import io
import os

from flask import Blueprint, jsonify, render_template, request, redirect, url_for, Response
from flask_login import login_required

from sqlalchemy import text, func, extract

from app.models import Device, Periodik, Lokasi
from app.forms import LoggerSettingForm
from app import db

bp = Blueprint('logger', __name__)


@bp.route('/')
@login_required
def index():
    '''Showing all logger'''
    all_devices = Device.query.order_by('sn').all()
    return render_template('logger/index.html', all_devices=all_devices)

@bp.route('/sync')
@login_required
def sync():
    '''Showing all logger'''
    url = "https://prinus.net/api/sensor"
    username = os.environ['PRINUS_USER']
    password = os.environ['PRINUS_PASS']
    response = requests.get(url, auth=(username, password))

    devices = Device.query.all()
    raw = response.json()
    sn_list = [key['sn'] for key in raw]

    for dev in devices:
        if dev.sn in sn_list:
            sn_list.remove(dev.sn)

    # update device and lokasi in pbase, and
    # send new device and lokasi to pweb
    for sn in sn_list:
        # update device
        device = Device(sn=f"{sn}")
        db.session.add(device)
        db.session.commit()

        # send post data
        try:
            post_url = f"{os.environ['PWEB_URL']}/api/device"
            post_data = {
                'sn': f"{sn}",
                'id': device.id
            }
            res = requests.post(post_url, data=post_data)
            result = res.json()
            print(result)
        except Exception as e:
            print(e)

    return redirect(url_for('logger.index'))


@bp.route('/<device_id>/sync')
@login_required
def syncpweb(device_id):
    '''Showing all logger'''
    log = Device.query.get(device_id)

    # send post data
    try:
        post_url = f"{os.environ['PWEB_URL']}/api/device"
        post_data = {
            'sn': f"{log.sn}",
            'id': log.id,
            'tipe': log.tipe
        }
        res = requests.post(post_url, data=post_data)
        result = res.json()
        print(result)
    except Exception as e:
        print(e)
    return redirect(url_for('logger.index'))


@bp.route('/sehat')
@login_required
def sehat():
    '''Showing number incoming data each hour'''
    all_devices = []
    sql = text("SELECT sampling::date, date_part('hour', sampling) AS hour, COUNT(*) \
               FROM periodik \
               WHERE device_sn=:sn AND sampling::date=:sampling \
               GROUP BY sampling::date, date_part('hour', sampling) \
               ORDER BY sampling")
    sampling = datetime.datetime.strptime(request.args.get('sampling'),
                                          '%Y-%m-%d').date() if request.args.get('sampling') else datetime.date.today()
    prev = sampling - datetime.timedelta(days=1)
    i_next = sampling + datetime.timedelta(days=1)
    for d in Device.query.filter(Device.lokasi!=None).order_by('sn'):
        res = db.engine.execute(sql, sn=d.sn, sampling=str(sampling))
        hourly = dict([r[1:] for r in res])
        hourly_count = [(i, hourly.get(i, 0)) for i in range(0, 24)]
        all_devices.append({'device': d, 'hourly_count': hourly_count})
    return render_template('logger/sehat.html', sampling=sampling,
                           all_devices=all_devices, prev=prev,
                          next=i_next)

@bp.route('/<sn>/sampling')
@login_required
def sampling(sn):
    '''Showing specific Periodic data on such logger'''
    device = Device.query.filter_by(sn=sn).first_or_404()
    return render_template('logger/sampling.html', device=device)

@bp.route('/<sn>', methods=["GET", "POST"])
@login_required
def show(sn):
    page = int(request.args.get('p', 1))
    per_page = int(request.args.get('n', 25))
    device = Device.query.filter_by(sn=sn).first_or_404()
    now = datetime.datetime.now()
    paginate = Periodik.query.filter(
        Periodik.device_sn == device.sn,
        Periodik.sampling <= now).order_by(
            Periodik.sampling.desc()).paginate(page, per_page)
    init_data = {'temp_cor': device.temp_cor or 0,
                 'humi_cor': device.humi_cor or 0,
                 'batt_cor': device.batt_cor or 0}
    if device.tipe == 'arr':
        init_data.update({'tipp_fac': device.tipp_fac or 1})
    form = LoggerSettingForm(obj=device)
    form.lokasi_id.choices = [(l.id, l.nama) for l in Lokasi.query.all()]
    monthly_download_list = db.engine.execute(text(
        "SELECT DISTINCT(TO_CHAR(sampling, 'YYYY-mm-01')) \
        FROM periodik \
        WHERE device_sn=:sn"), sn=device.sn)
    #print('monthly_download_list:', [r[0] for r in monthly_download_list])
    if form.validate_on_submit():
        if device.tipe == 'arr':
            device.tipp_fac = form.tipp_fac.data
        else:
            device.ting_son = form.ting_son.data
        device.temp_cor = form.temp_cor.data
        device.humi_cor = form.humi_cor.data
        device.batt_cor = form.batt_cor.data
        device.lokasi_id = int(form.lokasi_id.data)
        db.session.commit()
        return redirect(url_for('logger.show', sn=sn))
    return render_template('logger/show.html', device=device, form=form,
                           pagination=paginate,
                           month_list=[r[0] for r in monthly_download_list])

@bp.route('/<sn>/csv')
@login_required
def download_csv(sn):
    device = Device.query.filter_by(sn=sn).first_or_404()
    sampling = request.args.get('sampling', None)
    if sampling:
        sampling = datetime.datetime.strptime(sampling, "%Y-%m-%d")
    else:
        sampling = datetime.datetime.now()

    pre_csv = []
    pre_csv.append([f"Data Periodik Logger {sn}"])
    pre_csv.append([sampling.strftime("%d %B %Y")])
    pre_csv.append([
        'no', 'sampling',
        'hujan (mm)' if device.tipe == 'arr' else 'TMA (M)',
        'suhu','kelembaban','batt','sinyal'
    ])

    periodik = Periodik.query.filter(
            Periodik.device_sn==sn,
            extract('day', Periodik.sampling) == sampling.day,
            extract('month', Periodik.sampling) == sampling.month,
            extract('year', Periodik.sampling) == sampling.year
        ).all()

    for i, per in enumerate(periodik):
        telemetri = per.rain if device.tipe == 'arr' else per.wlev
        pre_csv.append([
            i+1, per.sampling,
            round(telemetri, 2) if telemetri else None,
            per.temp, per.humi, per.batt, per.sq
        ])

    output = io.StringIO()
    writer = csv.writer(output, delimiter='\t')
    for l in pre_csv:
        writer.writerow(l)
    output.seek(0)
    return Response(output,
                    mimetype="text/csv",
                    headers={
                        "Content-Disposition": f"attachment;filename=periodik_{sn}_{sampling.strftime('%d %B %Y')}.csv"
                    })

@bp.route('/add')
def add():
    return render_template('logger/add.html')

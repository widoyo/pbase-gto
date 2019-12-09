import click
import logging
import requests
import datetime
import json
import daemonocle
import paho.mqtt.subscribe as subscribe

from sqlalchemy import func, or_, desc
from sqlalchemy.exc import IntegrityError

from telegram import Bot

from app import app, db
from app.models import Device, Raw, Periodik, Lokasi

bws_sul2 = ("bwssul2", "limboto1029")

URL = "https://prinus.net/api/sensor"
MQTT_HOST = "mqtt.bbws-bsolo.net"
MQTT_PORT = 14983
MQTT_TOPIC = "bws-sul2"
MQTT_CLIENT = "primabase_bwssul2"

logging.basicConfig(
        filename='/tmp/primabaselistener.log',
        level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')

@app.cli.command()
@click.argument('command')
def telegram(command):
    tgl = datetime.date.today() - datetime.timedelta(days=1)
    if command == 'test':
        print(persentase_hadir_data(tgl))
    elif command == 'test_ch_tma':
        print(info_ch_tma())
    elif command == 'info_ch':
        info = info_ch()
        bot = Bot(token=app.config.get('BWSSUL2BOT_TOKEN'))
        bot.sendMessage(app.config.get('BWS_SUL2_TELEMETRY_GROUP'),
                        text=info,
                        parse_mode='Markdown')
    elif command == 'info_tma':
        info = info_tma()
        bot = Bot(token=app.config.get('BWSSUL2BOT_TOKEN'))
        bot.sendMessage(app.config.get('BWS_SUL2_TELEMETRY_GROUP'),
                        text=(info),
                        parse_mode='Markdown')
    elif command == 'send':
        bot = Bot(token=app.config.get('BWSSUL2BOT_TOKEN'))
        bot.sendMessage(app.config.get('BWS_SUL2_TELEMETRY_GROUP'),
                        text=(persentase_hadir_data(tgl)),
                        parse_mode='Markdown')


def info_ch():
    ret = "*BWS Sulawesi 2*\n\n"
    ch = build_ch()
    ret += ch
    return ret


def info_tma():
    ret = "*BWS Sulawesi 2*\n\n"
    tma = build_tma()
    ret += tma
    return ret


def build_ch():
    now = datetime.datetime.now()
    dari = now.replace(hour=7, minute=0, second=0, microsecond=0)
    if now.hour < 7:
        dari -= datetime.timedelta(days=1)
    ret = "*Curah Hujan %s*\n" % (dari.strftime('%d %b %Y'))
    dari_fmt = dari.date() != now.date() and '%d %b %Y %H:%M' or '%H:%M'
    ret += "Akumulasi: %s sd %s (%.1f jam)\n\n" % (dari.strftime(dari_fmt),
                                                 now.strftime('%H:%M'),
                                                 (now - dari).seconds / 3600)
    i = 1
    for pos in Lokasi.query.filter(or_(Lokasi.jenis == '1', Lokasi.jenis ==
                                      '4')):
        ret += "%s. %s" % (i, pos.nama)
        j = 1
        durasi = 0
        ch = 0
        for p in Periodik.query.filter(Periodik.lokasi_id == pos.id,
                                       Periodik.rain > 0,
                                       Periodik.sampling > dari):
            durasi += 5
            ch += p.rain
        if ch > 0:
            ret += " *%.1f mm (%s menit)*" % (ch, durasi)
        else:
            ret += " _tidak hujan_"
        ret += "\n"
        i += 1
    return ret


def build_tma():
    ret = '\n*Tinggi Muka Air*\n\n'
    i = 1
    now = datetime.datetime.now()
    for pos in Lokasi.query.filter(Lokasi.jenis == '2'):
        ret += "%s. %s" % (i, pos.nama)
        periodik = Periodik.query.filter(Periodik.lokasi_id ==
                              pos.id, Periodik.sampling <= now).order_by(desc(Periodik.sampling)).first()
        ret +=  " *TMA: %.2f Meter* jam %s\n" % (periodik.wlev * 0.01,
                                  periodik.sampling.strftime('%H:%M %d %b %Y'))
        i += 1
    return ret


def persentase_hadir_data(tgl):
    out = '''*BWS Sulawesi 2*

*Kehadiran Data*
%(tgl)s (0:0 - 23:55)
''' % {'tgl': tgl.strftime('%d %b %Y')}
    pos_list = Lokasi.query.filter(Lokasi.jenis == '1')
    if pos_list.count():
        str_pos = ''
        j_data = 0
        i = 1
        for l in pos_list:
            banyak_data = Periodik.query.filter(Periodik.lokasi_id == l.id,
                                                func.DATE(Periodik.sampling) == tgl).count()
            persen_data = (banyak_data/288) * 100
            j_data += persen_data
            str_pos += '%s. %s ' % (i, l.nama + ': *%.1f%%*\n' % (persen_data))
            i += 1
        str_pos = '\n*Pos Hujan: %.1f%%*\n\n' % (j_data/(i-1)) + str_pos
        out += str_pos
    # end pos_hujan

    pos_list = Lokasi.query.filter(Lokasi.jenis == '2')
    if pos_list.count():
        str_pos = ''
        i = 1
        j_data = 0
        persen_data = 0
        for l in pos_list:
            banyak_data = Periodik.query.filter(Periodik.lokasi_id == l.id,
                                                func.DATE(Periodik.sampling) == tgl).count()
            persen_data = (banyak_data/288) * 100
            j_data += persen_data
            str_pos += '%s. %s ' % (i, l.nama + ': *%.1f%%*\n' % (persen_data))
            i += 1
        str_pos = '\n*Pos TMA: %.1f%%*\n\n' % (j_data/(i-1)) + str_pos
        out += str_pos
    # end pos_tma_list

    pos_list = Lokasi.query.filter(Lokasi.jenis == '4')
    if pos_list.count():
        str_pos = ''
        i = 1
        j_data = 0
        persen_data = 0
        for l in pos_list:
            banyak_data = Periodik.query.filter(Periodik.lokasi_id == l.id,
                                                func.DATE(Periodik.sampling) == tgl).count()
            persen_data = (banyak_data/288) * 100
            j_data += persen_data
            str_pos += '%s. %s ' % (i, l.nama + ': *%.1f%%*\n' % (persen_data))
            i += 1
            str_pos = '\n*Pos Klimatologi: %.1f%%*\n\n' % (j_data/(i-1)) + str_pos
        out += str_pos
    return out


@app.cli.command()
@click.argument('command')
def listen(command):
    daemon = daemonocle.Daemon(worker=subscribe_topic,
                              pidfile='listener.pid')
    daemon.do_action(command)


def on_mqtt_message(client, userdata, msg):
    data = json.loads(msg.payload.decode('utf-8'))
    periodik = raw2periodic(data)
    periodik2pweb(periodik)
    logging.debug(data.get('device'))


def subscribe_topic():
    logging.debug('Start listen...')
    subscribe.callback(on_mqtt_message, MQTT_TOPIC,
                       hostname=MQTT_HOST, port=MQTT_PORT,
                       client_id=MQTT_CLIENT)


@app.cli.command()
def fetch_logger():
    res = requests.get(URL, auth=bws_sul2)

    if res.status_code == 200:
        logger = json.loads(res.text)
        local_logger = [d.sn for d in Device.query.all()]
        if len(local_logger) != len(logger):
            for l in logger:
                if l.get('sn') not in local_logger:
                    new_logger = Device(sn=l.get('sn'))
                    db.session.add(new_logger)
                    db.session.commit()
                    print('Tambah:', new_logger.sn)
    else:
        print(res.status_code)


@app.cli.command()
@click.argument('sn')
@click.option('-s', '--sampling', default='', help='Awal waktu sampling')
def fetch_periodic(sn, sampling):
    sampling_param = ''
    if sampling:
        sampling_param = '&sampling=' + sampling
    res = requests.get(URL + '/' + sn + '?robot=1' + sampling_param, auth=bws_sul2)
    data = json.loads(res.text)
    for d in data:
        content = Raw(content=d)
        db.session.add(content)
        try:
            db.session.commit()
            periodik = raw2periodic(d)
            periodik2pweb(periodik)
        except Exception as e:
            db.session.rollback()
            print("ERROR:", e)
        print(d.get('sampling'), d.get('temperature'))


def raw2periodic(raw):
    '''Menyalin data dari Raw ke Periodik'''
    sn = raw.get('device').split('/')[1]
    session = db.session
    session.rollback()
    device = session.query(Device).filter_by(sn=sn).first()
    obj = {'device_sn': device.sn, 'lokasi_id': device.lokasi.id if
           device.lokasi else None}
    if raw.get('tick'):
        rain = (device.tipp_fac or 0.2) * raw.get('tick')
        obj.update({'rain': rain})
    if raw.get('distance'):
        # dianggap distance dalam milimeter
        # 'distance' MB7366(mm) di centimeterkan
        wlev = (device.ting_son or 100) - raw.get('distance') * 0.1
        obj.update({'wlev': wlev})
    time_to = {'sampling': 'sampling',
               'up_since': 'up_s',
               'time_set_at': 'ts_a'}
    direct_to = {'altitude': 'mdpl',
                 'signal_quality': 'sq',
                 'pressure': 'apre'}
    apply_to = {'humidity': 'humi',
                'temperature': 'temp',
                'battery': 'batt'}
    for k, v in time_to.items():
        obj.update({v: datetime.datetime.fromtimestamp(raw.get(k))})
    for k, v in direct_to.items():
        obj.update({v: raw.get(k)})
    for k, v in apply_to.items():
        if k in raw:
            corr = getattr(device, v + '_cor', 0) or 0
            obj.update({v: raw.get(k) + corr})

    try:
        d = Periodik(**obj)
        db.session.add(d)
        device.update_latest()
        if device.lokasi:
            device.lokasi.update_latest()
        db.session.commit()
        return d.__dict__
    except IntegrityError:
        print(obj.get('device_sn'), obj.get('lokasi_id'), obj.get('sampling'))
        db.session.rollback()
        return {}


def periodik2pweb(data):
    # sending periodik to primaweb gto using api
    url = "https://bwssul2-gorontalo.net/api/periodik"
    print("Post new Periodik")
    req = requests.post(url, data=data)
    print(req)
    print(req.json())


if __name__ == '__main__':
    import datetime
    tgl = datetime.date(2018,12,20)
    print(persentase_hadir_data(tgl))

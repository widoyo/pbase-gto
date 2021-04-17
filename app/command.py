import click
import logging
import requests
import datetime
import os
import json
import daemonocle
import paho.mqtt.subscribe as subscribe

from sqlalchemy import func, or_, desc
from sqlalchemy.exc import IntegrityError

from telegram import Bot

from app import app, db
from app.models import Device, Raw, Periodik, Lokasi, Curahujan, Tma

bws_sul2 = (os.environ['PRINUS_USER'], os.environ['PRINUS_PASS'])

PBASE_API = "https://bwssul2-gorontalo.net/api"
URL = "https://prinus.net/api/sensor"
MQTT_HOST = os.environ["MQTT_HOST"]
MQTT_PORT = int(os.environ["MQTT_PORT"])
MQTT_TOPIC = os.environ["MQTT_TOPIC"]
MQTT_CLIENT = ""

logging.basicConfig(
        filename='/tmp/primabaselistener.log',
        level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')


'''----New Code from prinus python----'''


def getstarttime(time):
    ''' get starting time of the data '''
    res = time.hour < 7 and (time - datetime.timedelta(days=1)) or time
    return res.replace(hour=7, minute=0, second=0)


def prettydate(d):
    diff = datetime.datetime.utcnow() - d
    s = diff.seconds
    if diff.days > 30:
        return f"Lebih dari Sebulan Lalu"
    elif diff.days > 7 and diff.days < 30:
        return f"Lebih dari Seminggu Lalu"
    elif diff.days >= 1 and diff.days < 7:
        return f"{diff.days} Hari Lalu"
    elif s < 3600:
        return f"{round(s/60)} Menit Lalu"
    else:
        return f"{round(s/3600)} Jam Lalu"


def send_telegram(bot, id, name, message, debug_text):
    debug_text = f"Sending Telegram to {name}"
    try:
        bot.sendMessage(id, text=message)
        logging.debug(f"{debug_text}")
    except Exception as e:
        logging.debug(f"{debug_text} Error : {e}")


def periodik_report(time):
    ''' Message Tenants about last 2 hour rain and water level '''
    bot = Bot(token=app.config['PRINUSBOT_TOKEN'])

    ch_report(time, bot)
    tma_report(time, bot)

    # bot.sendMessage(app.config['TELEGRAM_TEST_ID'], text="Sending 2-Hourly Reports to All Tenants")


def ch_report(time, bot):
    tenants = Tenant.query.order_by(Tenant.id).all()

    for ten in tenants:
        tz = ten.timezone or "Asia/Jakarta"
        localtime = utc2local(time, tz=tz)
        end = datetime.datetime.strptime(f"{localtime.strftime('%Y-%m-%d')} {localtime.hour}:00:00", "%Y-%m-%d %H:%M:%S")
        start = getstarttime(end)

        final = f"*Curah Hujan {end.strftime('%d %b %Y')}*\n"
        final += f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}\n"
        message = ""

        locations = Location.query.filter(
                                    or_(Location.tipe == '1', Location.tipe == '4'),
                                    Location.tenant_id == ten.id).all()

        i = 0
        for pos in locations:
            result = get_periodik_sum(pos, start, end)
            latest = get_latest_telemetri(pos)

            i += 1
            rain = f"{round(result['rain'], 2)} mm selama {result['duration']} menit" if result['rain'] > 0 else '-'
            message += f"\n{i}. {pos.nama} : {rain}"
            message += f"\n     {result['percent']}%, data terakhir {latest['latest']}\n"

        if message:
            final += message
        else:
            final += "\nBelum Ada Lokasi yg tercatat"

        send_telegram(bot, ten.telegram_info_id, ten.nama, final, f"TeleRep-send {ten.nama}")

        print(f"{ten.nama}")
        print(final)
        print()


def tma_report(time, bot):
    tenants = Tenant.query.order_by(Tenant.id).all()

    for ten in tenants:
        locations = Location.query.filter(
                                    Location.tipe == '2',
                                    Location.tenant_id == ten.id).all()

        final = f"*TMA*\n"
        message = ""
        i = 0
        for pos in locations:
            latest = get_latest_telemetri(pos)

            i += 1
            if latest['periodik']:
                info = f"{latest['periodik'].wlev or '-'}, {latest['latest']}"
                tgl = f"\n     ({latest['periodik'].sampling.strftime('%d %b %Y, %H:%M')})\n"
            else:
                info = "Belum Ada Data"
                tgl = "\n"
            message += f"\n{i}. {pos.nama} : {info}"
            message += tgl

        if message:
            final += message
        else:
            final += "\nBelum Ada Lokasi yg tercatat"

        send_telegram(bot, ten.telegram_info_id, ten.nama, final, f"TeleRep-send {ten.nama}")

        print(final)
        print()


def get_periodik_sum(pos, start, end):
    periodics = Periodik.query.filter(
                                Periodik.sampling.between(start, end),
                                Periodik.location_id == pos.id).all()
    result = {
        'pos': pos,
        'rain': 0,
        'duration': 0,
        'percent': 0
    }
    for period in periodics:
        result['rain'] += period.rain
        result['duration'] += 5
        result['percent'] += 1

    diff = end - start
    percent = (result['percent']/(diff.seconds/300)) * 100
    result['percent'] = round(percent, 2)

    return result


def get_latest_telemetri(pos):
    latest = Periodik.query.filter(Periodik.location_id == pos.id).order_by(desc(Periodik.sampling)).first()

    result = {
        'periodik': latest,
        'lastest': ""
    }
    if latest:
        result['latest'] = prettydate(latest.sampling)
    else:
        result['latest'] = "Belum Ada Data"
    return result


def periodik_count_report(time):
    ''' Message Tenants about last day periodic counts '''
    bot = Bot(token=app.config['PRINUSBOT_TOKEN'])

    tenants = Tenant.query.order_by(Tenant.id).all()

    for ten in tenants:
        # param tz should be entered if tenant have timezone
        # log.tenant.timezone
        tz = ten.timezone or "Asia/Jakarta"  # "Asia/Jakarta"
        localtime = utc2local(time, tz=tz)
        end = datetime.datetime.strptime(f"{localtime.year}-{localtime.month}-{time.day} 23:56:00", "%Y-%m-%d %H:%M:%S")
        start = datetime.datetime.strptime(f"{localtime.year}-{localtime.month}-{time.day} 00:00:00", "%Y-%m-%d %H:%M:%S")

        final = '''*%(ten)s*\n*Kehadiran Data*\n%(tgl)s (0:0 - 23:55)
        ''' % {'ten': ten.nama, 'tgl': start.strftime('%d %b %Y')}
        message = ""

        locations = Location.query.filter(
                                    # Location.tipe == '1',
                                    Location.tenant_id == ten.id).all()

        i = 0
        for pos in locations:
            i += 1
            result = get_periodic_arrival(pos, start, end)
            message += f"\n{i} {pos.nama} ({result['tipe']}) : {result['percent']}%"

        if message:
            final += message
        else:
            final += "\nBelum Ada Lokasi yg tercatat"

        send_telegram(bot, ten.telegram_info_id, ten.nama, final, f"TeleCount-send {ten.nama}")
        print(f"{localtime} : {final}")
        print()
    # bot.sendMessage(app.config['TELEGRAM_TEST_ID'], text="Sending Daily Count Reports to All Tenants")


def get_periodic_arrival(pos, start, end):
    periodics = Periodik.query.filter(
                                Periodik.sampling.between(local2utc(start), local2utc(end)),
                                Periodik.location_id == pos.id).all()
    tipe = POS_NAME[pos.tipe] if pos.tipe else "Lain-lain"
    result = {
        'pos': pos,
        'tipe': tipe,
        'percent': 0
    }
    for period in periodics:
        result['percent'] += 1

    diff = end - start
    percent = (result['percent']/(diff.seconds/300)) * 100
    result['percent'] = round(percent, 2)

    return result


'''----End of New Code from prinus python----'''


@app.cli.command()
@click.argument('command')
def telegram(command):
    tgl = datetime.date.today() - datetime.timedelta(days=1)
    if command == 'test':
        print(persentase_hadir_data(tgl))
    elif command == 'test_ch_tma':
        print(info_ch_tma())
    elif command == 'info_ch':
        logging.debug(f"Preparing Info Curah Hujan")
        info = info_ch()
        bot = Bot(token=app.config.get('BWSSUL2BOT_TOKEN'))
        bot.sendMessage(app.config.get('BWS_SUL2_TELEMETRY_GROUP'),
                        text=info,
                        parse_mode='Markdown')
        logging.debug(f"Info Curah Hujan Sent")
    elif command == 'info_tma':
        logging.debug(f"Preparing Info TMA")
        info = info_tma()
        bot = Bot(token=app.config.get('BWSSUL2BOT_TOKEN'))
        bot.sendMessage(app.config.get('BWS_SUL2_TELEMETRY_GROUP'),
                        text=(info),
                        parse_mode='Markdown')
        logging.debug(f"Info TMA Sent")
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

    loggers = Device.query.all()
    lokasi_ids = []
    for l in loggers:
        lokasi_ids.append(l.lokasi_id)

    i = 1
    for pos in Lokasi.query.filter(or_(Lokasi.jenis == '1', Lokasi.jenis == '4')):
        if pos.id not in lokasi_ids:
            continue
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
    print(ret)
    return ret


def build_tma():
    ret = '\n*Tinggi Muka Air*\n\n'
    i = 1
    now = datetime.datetime.now()

    loggers = Device.query.all()
    lokasi_ids = []
    for l in loggers:
        lokasi_ids.append(l.lokasi_id)

    for pos in Lokasi.query.filter(Lokasi.jenis == '2'):
        if pos.id not in lokasi_ids:
            continue

        ret += "%s. %s" % (i, pos.nama)
        periodik = Periodik.query.filter(Periodik.lokasi_id ==
                              pos.id, Periodik.sampling <= now).order_by(desc(Periodik.sampling)).first()
        if not periodik:
            ret += " *TMA: Belum Ada Data\n"
        ret +=  " *TMA: %.2f Meter* jam %s\n" % (periodik.wlev * 0.01,
                                  periodik.sampling.strftime('%H:%M %d %b %Y'))
        i += 1
    print(ret)
    return ret


def persentase_hadir_data(tgl):
    out = '''*BWS Sulawesi 2*

*Kehadiran Data*
%(tgl)s (0:0 - 23:55)
''' % {'tgl': tgl.strftime('%d %b %Y')}

    loggers = Device.query.all()
    lokasi_ids = []
    for l in loggers:
        lokasi_ids.append(l.lokasi_id)

    pos_list = Lokasi.query.filter(Lokasi.jenis == '1')
    if pos_list.count():
        str_pos = ''
        j_data = 0
        i = 1
        for l in pos_list:
            if l.id not in lokasi_ids:
                continue
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
            if l.id not in lokasi_ids:
                continue
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
            if l.id not in lokasi_ids:
                continue
            banyak_data = Periodik.query.filter(Periodik.lokasi_id == l.id,
                                                func.DATE(Periodik.sampling) == tgl).count()
            persen_data = (banyak_data/288) * 100
            j_data += persen_data
            str_pos += '%s. %s ' % (i, l.nama + ': *%.1f%%*\n' % (persen_data))
            i += 1
        str_pos = '\n*Pos Klimatologi: %.1f%%*\n\n' % (j_data/(i-1)) + str_pos
        out += str_pos
    print(out)
    return out


@app.cli.command()
@click.argument('command')
def listen(command):
    daemon = daemonocle.Daemon(worker=subscribe_topic,
                              pidfile='listener.pid')
    daemon.do_action(command)


def on_mqtt_message(client, userdata, msg):
    data = json.loads(msg.payload.decode('utf-8'))
    try:
        periodik = raw2periodic(data)
        if periodik:
            periodik2pweb(periodik)
            logging.debug(f"{data.get('device')}, data recorded")
    except Exception as e:
        logging.debug(f"Listen Error : {e}")


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
    try:
        res = requests.get(URL + '/' + sn + '?robot=1' + sampling_param, auth=bws_sul2)
    except Exception as e:
        logging.debug(f"Fetch Periodic Error : {e}")
        return
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


@app.cli.command()
@click.option('-s', '--sampling', default='', help='Awal waktu sampling')
def fetch_periodic_today(sampling):
    devices = Device.query.all()
    today = datetime.datetime.today()
    if not sampling:
        sampling = today.strftime("%Y/%m/%d")
    for d in devices:
        try:
            print(f"Fetch Periodic for {d.sn}")
            logging.debug(f"Fetch Periodic for {d.sn}")
            os.system(f"flask fetch-periodic {d.sn} -s {sampling}")
        except Exception as e:
            print(f"!!Fetch Periodic ({d.sn}) ERROR : {e}")
            logging.debug(f"!!Fetch Periodic ({d.sn}) ERROR : {e}")


@app.cli.command()
@click.option('-s', '--sampling', default='', help='Awal waktu sampling')
def fetch_manual_ch(sampling):
    lokasi = Lokasi.query.all()
    today = datetime.datetime.today()
    sampling = sampling or today.strftime("%Y-%m-%d")
    # print(f"Fetching Manual Data at {sampling}")

    ch_api = requests.get(f"{PBASE_API}/curahhujan")
    ch = json.loads(ch_api.text)
    ch_sorted = {}

    for c in ch['data']:
        if c['manual']['ch'] is not None:
            ch_sorted[c['lokasi']] = {
                'sampling': datetime.datetime.strptime(c['manual']['sampling'], "%Y-%m-%d"),
                'ch': c['manual']['ch'],
            }

    for l in lokasi:
        if l.nama in ch_sorted:
            print("inserting data")
            sampling = ch_sorted[l.nama]['sampling']
            ch = ch_sorted[l.nama]['ch']
            new_ch = Curahujan(
                sampling=sampling,
                manual=ch,
                lokasi_id=l.id
            )
            db.session.add(new_ch)
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print("ERROR:", e)


@app.cli.command()
@click.option('-s', '--sampling', default='', help='Awal waktu sampling')
def fetch_manual_tma(sampling):
    lokasi = Lokasi.query.all()
    today = datetime.datetime.today()
    sampling = sampling or today.strftime("%Y-%m-%d")
    # print(f"Fetching Manual Data at {sampling}")

    tma_api = requests.get(f"{PBASE_API}/tma")
    tma = json.loads(tma_api.text)
    tma_sorted = {}

    for t in tma['data']:
        if t['manual']['tma'] is not None:
            tma_sorted[t['lokasi']] = {
                'samplitng': datetime.datetime.strptime(t['manual']['sampling'], "%Y-%m-%d"),
                'tma': t['manual']['tma']
            }

    for l in lokasi:
        if l.nama in tma_sorted:
            print("inserting data")
            sampling = tma_sorted[l.nama]['sampling']
            tma = tma_sorted[l.nama]['tma']
            new_tma = Curahujan(
                sampling=sampling,
                manual=tma,
                lokasi_id=l.id
            )
            db.session.add(new_tma)
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print("ERROR:", e)


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
    obj = 'wind_speed' in raw and obj.update({'wind_speed': raw.get('wind_speed')}) or obj
    obj = 'wind_direction' in raw and obj.update({'wind_dir': raw.get('wind_direction')}) or obj
    obj = 'sun_radiation' in raw and obj.update({'sun_rad': raw.get('sun_radiation')}) or obj

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
        obj = k in raw and obj.update({v: datetime.datetime.fromtimestamp(raw.get(k))}) or obj
    for k, v in direct_to.items():
        obj = k in raw and obj.update({v: raw.get(k)}) or obj
    for k, v in apply_to.items():
        if k in raw:
            corr = getattr(device, v + '_cor', 0) or 0
            obj = k in raw and obj.update({v: raw.get(k) + corr}) or obj

    try:
        d = Periodik(**obj)
        db.session.add(d)
        device.update_latest()
        if device.lokasi:
            device.lokasi.update_latest()
        db.session.commit()
        return obj
    except IntegrityError:
        print(obj.get('device_sn'), obj.get('lokasi_id'), obj.get('sampling'))
        logging.debug(f"{raw.get('device')}, IntegrityError ({obj.get('lokasi_id')}, {obj.get('sampling')})")
        db.session.rollback()
        return {}


def periodik2pweb(data):
    # sending periodik to primaweb gto using api
    url = f"{os.environ['PWEB_URL']}/api/periodik"
    logging.debug("Sending data to primaweb")

    # format the datetime into string first
    data['sampling'] = data['sampling'].strftime("%Y-%m-%d %H:%M:%S")
    data['up_s'] = data['up_s'].strftime("%Y-%m-%d %H:%M:%S")
    data['ts_a'] = data['ts_a'].strftime("%Y-%m-%d %H:%M:%S")
    # logging.debug(f"Data : {data}")
    try:
        res = requests.post(url, data=data)
        logging.debug(f"[{res.status_code}] : {res.text}")
    except Exception as e:
        logging.debug(f"Error at sending data : {e}")
        # logging.debug(f"Data : {data}")


@app.cli.command()
@click.option('-s', '--sampling', default='', help='Awal waktu sampling')
def send_periodic_today(sampling):
    # sending periodik to primaweb gto using api
    url = f"{os.environ['PWEB_URL']}/api/periodik/bulk"

    today = datetime.datetime.today()
    datestr = sampling or today.strftime("%Y-%m-%d")
    date = datetime.datetime.strptime(f"{datestr}", '%Y-%m-%d')
    start = f"{date.year}-{date.month}-{date.day} 00:00:00"
    end = f"{date.year}-{date.month}-{date.day} 23:56:00"

    print(f"PeriodicBulk on {date.strftime('%d %B %Y')}\n")
    logging.debug(f"PeriodicBulk - Sending {datestr} periodics data")

    devices = Device.query.all()
    lokasi_list = [dev.lokasi_id for dev in devices]
    lokasis = Lokasi.query.all()
    for lok in lokasis:
        if lok.id not in lokasi_list:
            continue

        message = {
            'tenant': "BWSSUL2",
            'count': 0,
            'data': []
        }
        periodics = Periodik.query.filter(
            Periodik.lokasi_id == lok.id,
            Periodik.sampling.between(start, end)
        ).all()

        for per in periodics:
            message['data'].append({
                'sampling': per.sampling.strftime("%Y-%m-%d %H:%M:%S"),
                'device_sn': per.device_sn,
                'lokasi_id': per.lokasi_id,
                'sq': per.sq,
                'temp': per.temp,
                'humi': per.humi,
                'batt': per.batt,
                'rain': per.rain,
                'wlev': per.wlev,
                'up_s': per.up_s.strftime("%Y-%m-%d %H:%M:%S") if per.up_s else None,
                'ts_a': per.ts_a.strftime("%Y-%m-%d %H:%M:%S") if per.ts_a else None,
                'apre': per.apre,
                'mdpl': per.mdpl
            })
            message['count'] += 1

        if message['count'] == 0:
            continue

        logging.debug(f"--PerBulk - Sending {lok.nama} periodics data")
        print(f"{lok.nama}")
        print(f"----periodic count = {message['count']}")
        try:
            res = requests.post(url, json=message)
            print(f"----Success ({res.text})")
            logging.debug(f"---- Success ({res.text})")
        except Exception as e:
            print(f"---- Error : {e}")
            logging.debug(f"---- Error: {e}")
        print()


if __name__ == '__main__':
    import datetime
    tgl = datetime.date(2018,12,20)
    print(persentase_hadir_data(tgl))

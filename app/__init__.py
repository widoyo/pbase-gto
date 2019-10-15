import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_socketio import SocketIO

app = Flask(__name__)
app.config.from_object(os.environ['APP_SETTINGS'])
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
socketio = SocketIO(app)

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login = LoginManager(app)
login.login_view = 'login'

from app.logger import bp as logger_bp
app.register_blueprint(logger_bp, url_prefix='/logger')

from app.pos import bp as lokasi_bp
app.register_blueprint(lokasi_bp, url_prefix='/pos')

from app.raw import bp as raw_bp
app.register_blueprint(raw_bp, url_prefix='/raw')

from app import routes, models, command

if __name__ == '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
    socketio.run(app)

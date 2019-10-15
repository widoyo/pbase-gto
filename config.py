import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config(object):
    DEBUG = False
    TESTING = False
    CSRF_ENABLED = True
    SECRET_KEY = 'golekono-dewe-sak-temune'
    SQLALCHEMY_DATABASE_URI = os.environ['DATABASE_URL']
    BWSSUL2BOT_TOKEN = '705378977:AAEPkaIYvMLEMiJWOtSNG8P-8RPO4IBPDf8'
    BWS_SUL2_TELEMETRY_GROUP = -301074579


class ProductionConfig(Config):
    DEBUG = True


class StagingConfig(Config):
    DEVELOPMENT = True
    DEBUG = True


class DevelopmentConfig(Config):
    DEVELOPMENT = True
    DEBUG = True


class TestingConfig(Config):
    TESTING = True

# -*- coding: utf-8 -*-
# Copyright (c) 2015 Gluu
#
# All rights reserved.

import os


class Config(object):
    DEBUG = False
    TESTING = False

    # This directory
    APP_DIR = os.path.abspath(os.path.dirname(__file__))

    HOST = os.environ.get("HOST", "127.0.0.1")
    PORT = os.environ.get("PORT", 8080)

    #DATA_DIR = os.environ.get("DATA_DIR", "/var/lib/gluu-cluster")
    DATA_DIR = os.environ.get("DATA_DIR", "/tmp")
    DATABASE_URI = os.path.join(DATA_DIR, "db", "db.json")
    TEMPLATES_DIR = os.path.join(APP_DIR, "templates")
    LOG_DIR = os.environ.get("LOG_DIR", "/var/log/gluu")
    INSTANCE_DIR = os.path.join(DATA_DIR, "instance")
    CUSTOM_LDAP_SCHEMA_DIR = os.path.join(
        DATA_DIR, "custom", "opendj", "schema",
    )
    OXAUTH_OVERRIDE_DIR = os.path.join(DATA_DIR, "override", "oxauth")
    OXTRUST_OVERRIDE_DIR = os.path.join(DATA_DIR, "override", "oxtrust")
    OXIDP_OVERRIDE_DIR = os.path.join(DATA_DIR, "override", "oxidp")
    #DRIVERS = ['generic','amazonec2','digitalocean', 'google']


class ProdConfig(Config):
    """Production configuration.
    """


class DevConfig(Config):
    """Development configuration.
    """
    DEBUG = True
    DATA_DIR = Config.APP_DIR + '/data'
    DATABASE_URI = os.path.join(Config.DATA_DIR, "db", "db_dev.json")


class TestConfig(Config):
    TESTING = True
    DEBUG = True
    DATABASE_URI = os.path.join(Config.DATA_DIR, "db", "db_test.json")

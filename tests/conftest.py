import os

import pytest


@pytest.fixture(scope="session")
def config():
    from gluuapi.settings import TestConfig
    return TestConfig


@pytest.fixture(scope="session")
def app(request):
    from gluuapi.app import create_app

    os.environ["API_ENV"] = "test"
    app = create_app()
    return app


@pytest.fixture()
def db(request, app):
    from gluuapi.database import db

    db.init_app(app)

    def teardown():
        try:
            os.unlink(app.config["DATABASE_URI"])
        except OSError:
            pass

    request.addfinalizer(teardown)
    return db


@pytest.fixture()
def cluster():
    from gluuapi.model import GluuCluster

    cluster = GluuCluster({
        "ox_cluster_hostname": "ox.example.com",
        "weave_ip_network": "10.20.10.0/24",
    })
    return cluster


@pytest.fixture()
def ldap_node(cluster, provider):
    from gluuapi.model import LdapNode

    node = LdapNode()
    node.id = "ldap_{}_123".format(cluster.id)
    node.cluster_id = cluster.id
    node.provider_id = provider.id
    return node


@pytest.fixture()
def oxauth_node(cluster, provider):
    from gluuapi.model import OxauthNode

    node = OxauthNode()
    node.id = "oxauth_{}_123".format(cluster.id)
    node.cluster_id = cluster.id
    node.provider_id = provider.id
    return node


@pytest.fixture()
def oxtrust_node(cluster, provider):
    from gluuapi.model import OxtrustNode

    node = OxtrustNode()
    node.id = "oxtrust_{}_123".format(cluster.id)
    node.cluster_id = cluster.id
    node.provider_id = provider.id
    return node


@pytest.fixture()
def provider():
    from gluuapi.model import Provider

    provider = Provider({
        "docker_base_url": "unix:///var/run/docker.sock",
        "hostname": "local",
    })
    return provider


@pytest.fixture()
def httpd_node(cluster, provider):
    from gluuapi.model import HttpdNode

    node = HttpdNode()
    node.id = "httpd_{}_123".format(cluster.id)
    node.cluster_id = cluster.id
    node.provider_id = provider.id
    return node


@pytest.fixture()
def license():
    from gluuapi.model import License
    from gluuapi.utils import timestamp_millis

    license = License({
        "code": "code_abc",
        "signed_license": "signed_license_abc",
        "valid": True,
        "billing_email": "admin@example.com",
        "metadata": {
            "license_features": None,
            "thread_count": 9,
            "license_name": None,
            "multi_server": True,
            "license_count_limit": 0,
            "expiration_date": timestamp_millis(),
            "license_type": "PAID",
        },
    })
    return license

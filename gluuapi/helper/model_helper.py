# -*- coding: utf-8 -*-
# The MIT License (MIT)
#
# Copyright (c) 2015 Gluu
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
import time
from random import randrange

from crochet import run_in_reactor

from gluuapi.database import db
from gluuapi.model import LdapNode
from gluuapi.model import OxauthNode
from gluuapi.model import OxtrustNode
from gluuapi.model import HttpdNode
from gluuapi.helper.docker_helper import DockerHelper
from gluuapi.helper.salt_helper import SaltHelper
from gluuapi.helper.prometheus_helper import PrometheusHelper
from gluuapi.setup import LdapSetup
from gluuapi.setup import OxauthSetup
from gluuapi.setup import OxtrustSetup
from gluuapi.setup import HttpdSetup
from gluuapi.log import create_file_logger
from gluuapi.log import create_tempfile
from gluuapi.utils import exc_traceback


class BaseModelHelper(object):
    #: Node setup class. Must be overriden in subclass.
    setup_class = None

    #: Node model class. Must be overriden in subclass.
    node_class = None

    #: Docker image name. Must be overriden in subclass.
    image = ""

    #: URL to image's Dockerfile. Must be overriden in subclass.
    dockerfile = ""

    def __init__(self, cluster, provider, salt_master_ipaddr,
                 template_dir, log_dir):
        assert self.setup_class, "setup_class must be set"
        assert self.node_class, "node_class must be set"
        assert self.image, "image attribute cannot be empty"
        assert self.dockerfile, "dockerfile attribute cannot be empty"

        self.salt_master_ipaddr = salt_master_ipaddr
        self.cluster = cluster
        self.provider = provider

        self.node = self.node_class()
        self.node.cluster_id = cluster.id
        self.node.provider_id = provider.id
        self.node.name = "{}_{}_{}".format(self.image, self.cluster.id,
                                           randrange(101, 999))

        self.logpath = create_tempfile(
            suffix=".log",
            prefix=self.image + "-build-",
            dir_=log_dir,
        )
        self.logger = create_file_logger(self.logpath, name=self.node.name)
        self.docker = DockerHelper(
            logger=self.logger, base_url=self.provider.docker_base_url)
        self.salt = SaltHelper()
        self.template_dir = template_dir

    def prepare_node_attrs(self):
        """Prepares changes to node's attributes (if any).

        It's worth noting that changing ``id`` attribute in this method
        should be avoided.
        """

    def prepare_minion(self, connect_delay=10, exec_delay=15):
        """Waits for minion to connect before doing any remote execution.
        """
        # wait for 10 seconds to make sure minion connected
        # and sent its key to master
        # TODO: there must be a way around this
        self.logger.info("Waiting for minion to connect; sleeping for "
                         "{} seconds".format(connect_delay))
        time.sleep(connect_delay)

        # register the container as minion
        self.salt.register_minion(self.node.id)

        # delay the remote execution
        # see https://github.com/saltstack/salt/issues/13561
        # TODO: there must be a way around this
        self.logger.info("Preparing remote execution; sleeping for "
                         "{} seconds".format(exec_delay))
        time.sleep(exec_delay)

    def before_save(self):
        """Callback before saving to database.

        Typical usage is to remove or protect sensitive field such as
        password or secret.
        """

    def save(self):
        """Saves node.
        """
        # Runs pre-save callback
        self.before_save()
        db.persist(self.node, "nodes")

    @run_in_reactor
    def setup(self, connect_delay=10, exec_delay=15):
        """Runs the node setup.
        """
        try:
            container_id = self.docker.setup_container(
                self.node.name, self.image,
                self.dockerfile, self.salt_master_ipaddr,
            )

            if container_id:
                # container ID in short format
                self.node.id = container_id[:12]

                # attach weave IP to container
                self.logger.info("assigning weave IP address")
                addr, prefixlen = self.cluster.reserve_ip_addr()
                self.salt.cmd(
                    self.provider.hostname,
                    "cmd.run",
                    ["weave attach {}/{} {}".format(addr, prefixlen,
                                                    self.node.id)],
                )
                db.update(self.cluster.id, self.cluster, "clusters")

                self.node.weave_ip = addr
                self.node.weave_prefixlen = prefixlen

                # runs callback to prepare node attributes;
                # warning: don't override node.id attribute!
                self.prepare_node_attrs()

                self.prepare_minion(connect_delay, exec_delay)
                if self.salt.is_minion_registered(self.node.id):
                    setup_obj = self.setup_class(self.node, self.cluster, self.logger, self.template_dir)

                    self.logger.info("{} setup is started".format(self.image))
                    start = time.time()

                    setup_obj.before_setup()

                    if setup_obj.setup():
                        self.logger.info("saving to database")
                        self.save()

                    setup_obj.after_setup()
                    setup_obj.remove_build_dir()
                    #updating prometheus
                    prometheus = PrometheusHelper(template_dir=self.template_dir)
                    prometheus.update()

                    elapsed = time.time() - start
                    self.logger.info(
                        "{} setup is finished ({} seconds)".format(
                            self.image, elapsed))

                # minion is not connected
                else:
                    self.logger.error("minion {} is unreachable".format(self.node.id))
                    self.on_setup_error()

            # container is not running
            else:
                self.logger.error("Failed to start the {!r} container".format(self.node.name))
        except Exception:
            self.logger.error(exc_traceback())
            self.on_setup_error()

    def on_setup_error(self):
        self.logger.info("destroying minion {}".format(self.node.id))

        # detach container from weave network
        if self.node.weave_ip:
            self.salt.cmd(
                self.provider.hostname,
                "cmd.run",
                ["weave detach {}/{} {}".format(self.node.weave_ip,
                                                self.node.weave_prefixlen,
                                                self.node.id)],
            )
            self.cluster.unreserve_ip_addr(self.node.weave_ip)
            self.node.weave_ip = ""
            db.update(self.cluster.id, self.cluster, "clusters")

        self.docker.remove_container(self.node.id)
        self.salt.unregister_minion(self.node.id)


class LdapModelHelper(BaseModelHelper):
    setup_class = LdapSetup
    node_class = LdapNode
    image = "gluuopendj"
    dockerfile = "https://raw.githubusercontent.com/GluuFederation" \
                 "/gluu-docker/master/ubuntu/14.04/gluuopendj/Dockerfile"

    def prepare_node_attrs(self):
        # For replication, you will need
        # to use the ip address of docker instance as hostname--not the cluster
        # ldap hostname. For the four ports (ldap, ldaps, admin, jmx),
        # try to use the default
        # ports unless they are already in use, at which point it should chose
        # a random port over 10,000. Note these ports will need to be
        # open between the ldap docker instances
        container_ip = self.docker.get_container_ip(self.node.id)
        self.node.ip = container_ip


class OxauthModelHelper(BaseModelHelper):
    setup_class = OxauthSetup
    node_class = OxauthNode
    image = "gluuoxauth"
    dockerfile = "https://raw.githubusercontent.com/GluuFederation" \
                 "/gluu-docker/master/ubuntu/14.04/gluuoxauth/Dockerfile"

    def prepare_node_attrs(self):
        container_ip = self.docker.get_container_ip(self.node.id)
        self.node.ip = container_ip


class OxtrustModelHelper(BaseModelHelper):
    setup_class = OxtrustSetup
    node_class = OxtrustNode
    image = "gluuoxtrust"
    dockerfile = "https://raw.githubusercontent.com/GluuFederation" \
                 "/gluu-docker/master/ubuntu/14.04/gluuoxtrust/Dockerfile"

    def prepare_node_attrs(self):
        container_ip = self.docker.get_container_ip(self.node.id)
        # self.node.hostname = container_ip
        self.node.ip = container_ip


class HttpdModelHelper(BaseModelHelper):
    setup_class = HttpdSetup
    node_class = HttpdNode
    image = "gluuhttpd"
    dockerfile = "https://raw.githubusercontent.com/GluuFederation" \
                 "/gluu-docker/master/ubuntu/14.04/gluuhttpd/Dockerfile"

    def prepare_node_attrs(self):
        container_ip = self.docker.get_container_ip(self.node.id)
        # self.node.hostname = container_ip
        self.node.ip = container_ip

# -*- coding: utf-8 -*-
# Copyright (c) 2015 Gluu
#
# All rights reserved.

import os
import time
from crochet import run_in_reactor

from ..database import db
from ..machine import Machine
from ..log import create_file_logger

REMOTE_DOCKER_CERT_DIR = "/opt/gluu/docker/certs"
CERT_FILES = ['ca.pem', 'cert.pem', 'key.pem']

FSWATCHER_SCRIPT = "https://github.com/GluuFederation/cluster-tools/raw/master/fswatcher/fswatcher.py"
FSWATCHER_CONF = "https://github.com/GluuFederation/cluster-tools/raw/master/fswatcher/fswatcher.conf"
RECOVERY_SCRIPT = "https://github.com/GluuFederation/cluster-tools/raw/master/recovery/recovery.py"
RECOVERY_CONF = "https://github.com/GluuFederation/cluster-tools/raw/master/recovery/recovery.conf"
RNG_TOOLS_CONF = "https://raw.githubusercontent.com/GluuFederation/cluster-tools/master/rng_tools"


class DeployNode(object):
    def __init__(self, node_model_obj, app):
        self.app = app
        self.node = node_model_obj
        self.logger = create_file_logger(app.config['NODE_LOG_PATH'], name=self.node.name)
        self.machine = Machine()
        with self.app.app_context():
            self.provider = db.get(self.node.provider_id, 'providers')

    def _rng_tools(self):
        try:
            self.logger.info("installing rng-tools in {} node".format(self.node.name))
            cmd_list = [
                "sudo wget {} -O /etc/default/rng-tools".format(RNG_TOOLS_CONF),
                """sudo apt-get -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold" install -y rng-tools""",
            ]
            self.machine.ssh(self.node.name, ' && '.join(cmd_list))
            self.node.state_rng_tools = True
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')
        except RuntimeError as e:
            self.logger.error('failed to install rng-tools')
            self.logger.error(e)

    def _pull_images(self):
        try:
            self.logger.info("pulling gluu images in {} node".format(self.node.name))
            cmd_list = [
                'sudo docker pull gluufederation/oxauth:{}'.format(self.app.config["GLUU_IMAGE_TAG"]),
                'sudo docker pull gluufederation/nginx:{}'.format(self.app.config["GLUU_IMAGE_TAG"]),
            ]
            self.machine.ssh(self.node.name, ' && '.join(cmd_list))
            self.node.state_pull_images = True
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')
        except RuntimeError as e:
            self.logger.error('failed to pull images')
            self.logger.error(e)

    def _recovery(self):
        try:
            self.logger.info("installing recovery in {} node".format(self.node.name))
            cmd_list = [
                "sudo wget {} -P /usr/bin".format(RECOVERY_SCRIPT),
                "sudo chmod +x /usr/bin/recovery.py",
                "sudo apt-get -qq install -y --force-yes supervisor",
                "sudo wget {} -P /etc/supervisor/conf.d".format(RECOVERY_CONF),
                "sudo supervisorctl reload",
            ]
            self.machine.ssh(self.node.name, ' && '.join(cmd_list))
            self.node.state_recovery = True
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')
        except RuntimeError as e:
            self.logger.error('failed to install recovery script')
            self.logger.error(e)

    def _install_weave(self):
        try:
            self.logger.info('installing weave')
            self.machine.ssh(self.node.name, 'sudo curl -L git.io/weave -o /usr/local/bin/weave')
            self.node.state_install_weave = True
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')
        except RuntimeError as e:
            self.logger.error('failed to install weave')
            self.logger.error(e)

    def _weave_permission(self):
        try:
            self.logger.info('adding exec permission of weave')
            self.machine.ssh(self.node.name, 'sudo chmod +x /usr/local/bin/weave')
            self.node.state_weave_permission = True
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')
        except RuntimeError as e:
            self.logger.error('failed to set weave permission')
            self.logger.error(e)


class DeployDiscoveryNode(DeployNode):
    def __init__(self, node_model_obj, app):
        super(DeployDiscoveryNode, self).__init__(node_model_obj, app)

    @run_in_reactor
    def deploy(self):
        if not self.node.state_node_create:
            self._node_create()
            time.sleep(1)
        if self.node.state_node_create and not self.node.state_install_consul:
            self._install_consul()
            time.sleep(1)
        self._is_completed()

        for handler in self.logger.handlers:
            handler.close()
            self.logger.removeHandler(handler)

    def _node_create(self):
        try:
            self.logger.info('creating discovery node')
            self.machine.create(self.node, self.provider, None)
            self.node.state_node_create = True
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')
        except RuntimeError as e:
            self.logger.error('failed to create node')
            self.logger.error(e)

    def _install_consul(self):
        self.logger.info('installing consul')
        try:
            self.machine.ssh(self.node.name, 'sudo docker run -d --name=consul -p 8500:8500 -h consul --restart=always -v /opt/gluu/consul/data:/data progrium/consul -server -bootstrap')
            self.node.state_install_consul = True
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')
        except RuntimeError as e:
            self.logger.error('failed to install consul')
            self.logger.error(e)

    def _is_completed(self):
        if self.node.state_node_create and self.node.state_install_consul:
            self.node.state_complete = True
            self.logger.info('node deployment is done')
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')


class DeployMasterNode(DeployNode):
    def __init__(self, node_model_obj, discovery, app):
        super(DeployMasterNode, self).__init__(node_model_obj, app)
        self.discovery = discovery

    @run_in_reactor
    def deploy(self):
        if not self.node.state_node_create:
            self._node_create()
            time.sleep(1)
        if self.node.state_node_create:
            if not self.node.state_install_weave:
                self._install_weave()
                time.sleep(1)
            if not self.node.state_weave_permission:
                self._weave_permission()
                time.sleep(1)
            if not self.node.state_weave_launch:
                self._weave_launch()
                time.sleep(1)
            if not self.node.state_docker_cert:
                self._docker_cert()
                time.sleep(1)
            if not self.node.state_fswatcher:
                self._fswatcher()
                time.sleep(1)
            if not self.node.state_recovery:
                self._recovery()
                time.sleep(1)
            if not self.node.state_rng_tools:
                self._rng_tools()
                time.sleep(1)
            if not self.node.state_pull_images:
                self._pull_images()
                time.sleep(1)
        self._is_completed()

        for handler in self.logger.handlers:
            handler.close()
            self.logger.removeHandler(handler)

    def _is_completed(self):
        if all([self.node.state_node_create, self.node.state_install_weave,
                self.node.state_weave_permission, self.node.state_weave_launch,
                self.node.state_docker_cert, self.node.state_fswatcher,
                self.node.state_recovery, self.node.state_rng_tools,
                self.node.state_pull_images]):
            self.node.state_complete = True
            self.logger.info('node deployment is done')
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')

    def _node_create(self):
        try:
            self.logger.info('creating {} node ({})'.format(self.node.name, self.node.type))
            self.machine.create(self.node, self.provider, self.discovery)
            self.node.state_node_create = True
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')
        except RuntimeError as e:
            self.logger.error('failed to create node')
            self.logger.error(e)

    def _weave_launch(self):
        try:
            self.logger.info('launching weave')
            self.machine.ssh(self.node.name, 'sudo weave launch')
            self.node.state_weave_launch = True
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')
        except RuntimeError as e:
            self.logger.error('failed to launch weave')
            self.logger.error(e)

    #pushing docker cert so that fswatcher script can work
    def _docker_cert(self):
        try:
            self.logger.info("pushing docker client cert into master node")
            local_cert_path = os.path.join(os.getenv('HOME'), '.docker/machine/certs')
            self.machine.ssh(self.node.name, 'sudo mkdir -p {}'.format(REMOTE_DOCKER_CERT_DIR))
            for cf in CERT_FILES:
                self.machine.scp(
                    os.path.join(local_cert_path, cf),
                    "{}:{}".format(self.node.name, REMOTE_DOCKER_CERT_DIR),
                )
            self.node.state_docker_cert = True
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')
        except RuntimeError as e:
            self.logger.error('failed to push docker client cert into master node')
            self.logger.error(e)

    def _fswatcher(self):
        try:
            self.logger.info("installing fswatcher in {} node".format(self.node.name))
            cmd_list = [
                "sudo wget {} -P /usr/bin".format(FSWATCHER_SCRIPT),
                "sudo chmod +x /usr/bin/fswatcher.py",
                "sudo apt-get -qq install -y --force-yes supervisor python-pip",
                "sudo pip -q install --upgrade pip",
                "sudo pip -q install virtualenv",
                "sudo mkdir -p /root/.virtualenvs",
                "sudo virtualenv /root/.virtualenvs/fswatcher",
                "sudo /root/.virtualenvs/fswatcher/bin/pip -q install watchdog",
                "sudo wget {} -P /etc/supervisor/conf.d".format(FSWATCHER_CONF),
                "sudo supervisorctl reload",
            ]
            self.machine.ssh(self.node.name, ' && '.join(cmd_list))
            self.node.state_fswatcher = True
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')
        except RuntimeError as e:
            self.logger.error('failed to install fswatcher script')
            self.logger.error(e)


class DeployWorkerNode(DeployNode):
    def __init__(self, node_model_obj, discovery, app):
        super(DeployWorkerNode, self).__init__(node_model_obj, app)
        self.discovery = discovery

    @run_in_reactor
    def deploy(self):
        if not self.node.state_node_create:
            self._node_create()
            time.sleep(1)
        if self.node.state_node_create:
            if not self.node.state_install_weave:
                self._install_weave()
                time.sleep(1)
            if not self.node.state_weave_permission:
                self._weave_permission()
                time.sleep(1)
            if not self.node.state_weave_launch:
                self._weave_launch()
                time.sleep(1)
            if not self.node.state_recovery:
                self._recovery()
                time.sleep(1)
            if not self.node.state_rng_tools:
                self._rng_tools()
                time.sleep(1)
            if not self.node.state_pull_images:
                self._pull_images()
                time.sleep(1)
        self._is_completed()

        for handler in self.logger.handlers:
            handler.close()
            self.logger.removeHandler(handler)

    def _is_completed(self):
        if all([self.node.state_node_create, self.node.state_install_weave,
                self.node.state_weave_permission, self.node.state_weave_launch,
                self.node.state_recovery, self.node.state_rng_tools,
                self.node.state_pull_images]):
            self.node.state_complete = True
            self.logger.info('node deployment is done')
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')

    def _node_create(self):
        try:
            self.logger.info('creating {} node ({})'.format(self.node.name, self.node.type))
            self.machine.create(self.node, self.provider, self.discovery)
            self.node.state_node_create = True
            with self.app.app_context():
                db.update(self.node.id, self.node, 'nodes')
        except RuntimeError as e:
            self.logger.error('failed to create node')
            self.logger.error(e)

    def _weave_launch(self):
        try:
            self.logger.info('launching weave')
            with self.app.app_context():
                master = db.search_from_table('nodes', {'type': 'master'})[0]
                ip = self.machine.ip(master.name)
                self.machine.ssh(self.node.name, 'sudo weave launch {}'.format(ip))
                self.node.state_weave_launch = True
                db.update(self.node.id, self.node, 'nodes')
        except RuntimeError as e:
            self.logger.error('failed to launch weave')
            self.logger.error(e)

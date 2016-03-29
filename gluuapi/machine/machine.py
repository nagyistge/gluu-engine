# -*- coding: utf-8 -*-
# Copyright (c) 2015 Gluu
#
# All rights reserved.

import os
from functools import wraps
import json
from ..utils import run

class Machine(object):

    def config(self, machine_name):
        conf = run('docker-machine config {}'.format(machine_name))
        return conf.strip().replace('\n', ' ')

    # this method is only for swarm master
    def swarm_config(self, machine_name):
        conf = run('docker-machine config --swarm {}'.format(machine_name))
        return conf.strip().replace('\n', ' ')

    def create(self, provider=None):
        pass

    def inspect(self, machine_name):
        data = run('docker-machine inspect {}'.format(machine_name))
        return json.loads(data)

    # Expects a list of machine names
    def ip(self, machine_name=None):
        machine_name = machine_name or []
        if machine_name:
            if isinstance(machine_name, (list, tuple)):
                template = 'docker-machine ip ' + ' '.join(['{}']*len(machine_name))
                ip = run(template.format(*machine_name))
                return ip.strip()

    # Expects a list of machine names
    def kill(self, machine_name=None):
        machine_name = machine_name or []
        if machine_name:
            if isinstance(machine_name, (list, tuple)):
                template = 'docker-machine kill ' + ' '.join(['{}']*len(machine_name))
                run(template.format(*machine_name))

    def ls(self):
        pass

    def provision(self):
        pass

    def regenerate_certs(self):
        pass

    def restart(self, machine_name):
        run('docker-machine restart {}'.format(machine_name))

    def rm(self, machine_name=None):
        machine_name = machine_name or []
        if machine_name:
            if isinstance(machine_name, (list, tuple)):
                template = 'docker-machine rm -y ' + ' '.join(['{}']*len(machine_name))
                run(template.format(*machine_name))

    def scp(self):
        pass

    def status(self, machine_name):
        status = run('docker-machine status {}'.format(machine_name))
        return status.strip()

    # Expects a list of machine names
    def start(self, machine_name=None):
        machine_name = machine_name or []
        if machine_name:
            if isinstance(machine_name, (list, tuple)):
                template = 'docker-machine start ' + ' '.join(['{}']*len(machine_name))
                run(template.format(*machine_name))

    # Expects a list of machine names
    def stop(self, machine_name=None):
        machine_name = machine_name or []
        if machine_name:
            if isinstance(machine_name, (list, tuple)):
                template = 'docker-machine stop ' + ' '.join(['{}']*len(machine_name))
                run(template.format(*machine_name))

    def upgrade(self):
        pass

    def url(self, machine_name):
        url = run('docker-machine url {}'.format(machine_name))
        return url.strip()

    def version(self):
        return run('docker-machine version')

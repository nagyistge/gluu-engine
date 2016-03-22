# -*- coding: utf-8 -*-
# Copyright (c) 2015 Gluu
#
# All rights reserved.

from kvdb import kv

def get_generic_driver_param(id = ''):
    param = kv['providers']['generic'][id]
    '--driver generic' \
 '--generic-ip-address=ec2-52-90-77-127.compute-1.amazonaws.com \
 --generic-ssh-key=/home/themonk/.ssh/astanaKP.pem \
 --generic-ssh-user="ubuntu" \
 '--generic-ssh-port=22'
 format.(**param)
    return 
def get_aws_driver():
    pass

def get_do_driver():
    pass

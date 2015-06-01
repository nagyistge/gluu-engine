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
import base64
import hashlib
import json
import os
import random
import string
import subprocess
import sys
import traceback
import uuid
import time
from datetime import datetime

from M2Crypto.EVP import Cipher

# Default charset
_DEFAULT_CHARS = "".join([string.ascii_uppercase,
                          string.digits,
                          string.lowercase])


def run(command, exit_on_error=True, cwd=None):
    try:
        # print("Shell command called (blocking): {}".format(command))
        return subprocess.check_output(command, stderr=subprocess.STDOUT,
                                       shell=True, cwd=cwd)
    except subprocess.CalledProcessError, e:
        if exit_on_error:
            sys.exit(e.returncode)
        else:
            raise


def get_random_chars(size=12, chars=_DEFAULT_CHARS):
    return ''.join(random.choice(chars) for _ in range(size))


def ldap_encode(password):
    # borrowed from https://github.com/GluuFederation/community-edition-setup
    # /blob/c23aa9a4353867060fc9faf674c72708059ae3bb/setup.py#L960-L966
    salt = os.urandom(4)
    sha = hashlib.sha1(password)
    sha.update(salt)
    b64encoded = '{0}{1}'.format(sha.digest(), salt).encode('base64').strip()
    encrypted_password = '{{SSHA}}{0}'.format(b64encoded)
    return encrypted_password

# backward-compat
encrypt_password = ldap_encode


def get_quad():
    # borrowed from community-edition-setup project
    # see http://git.io/he1p
    return str(uuid.uuid4())[:4].upper()


def generate_passkey():
    return "".join([get_random_chars(), get_random_chars()])


def encrypt_text(text, key):
    # Porting from pyDes-based encryption (see http://git.io/htxa)
    # to use M2Crypto instead (see https://gist.github.com/mrluanma/917014)
    cipher = Cipher(alg="des_ede3_ecb", key=b"{}".format(key), op=1, iv="\0" * 16)
    encrypted_text = cipher.update(b"{}".format(text))
    encrypted_text += cipher.final()
    return base64.b64encode(encrypted_text)


def decrypt_text(encrypted_text, key):
    # Porting from pyDes-based encryption (see http://git.io/htpk)
    # to use M2Crypto instead (see https://gist.github.com/mrluanma/917014)
    cipher = Cipher(alg="des_ede3_ecb", key=b"{}".format(key), op=0, iv="\0" * 16)
    decrypted_text = cipher.update(base64.b64decode(b"{}".format(encrypted_text)))
    decrypted_text += cipher.final()
    return decrypted_text


# backward-compat
ox_encode_password = encrypt_text
ox_decode_password = decrypt_text


def exc_traceback():
    """Get exception traceback as string.
    """
    exc_info = sys.exc_info()
    exc_string = ''.join(
        traceback.format_exception_only(*exc_info[:2]) +
        traceback.format_exception(*exc_info))
    return exc_string


def decode_signed_license(signed_license, public_key,
                          public_password, license_password,
                          validator="/opt/gluu/oxd-license-validator.jar"):
    """Gets license's metadata from a signed license.
    """
    cmd_output = run("java -jar {} {} {} {} {}".format(
        validator,
        signed_license,
        public_key,
        public_password,
        license_password,
    ), exit_on_error=False)

    # output example:
    #
    #   Validator expects: java org.xdi.oxd.license.validator.LicenseValidator
    #   {"valid":true,"metadata":{}}
    #
    # but we only care about the last line
    meta = cmd_output.splitlines()[-1]

    decoded_license = {}
    try:
        decoded_license = json.loads(meta)
    except ValueError:
        # validator may throws exception as the output,
        # which is not a valid JSON
        raise ValueError("Error parsing JSON output of {}".format(validator))
    return decoded_license


def timestamp_millis():
    """Time in milliseconds since the EPOCH.
    """
    return time.time() * 1000


def datetime_to_timestamp_millis(dt):
    """Converts datetime to time in milliseconds since the EPOCH.
    """
    return time.mktime(dt.timetuple()) * 1000


def timestamp_millis_to_datetime(ts):
    """Converts time in milliseconds since the EPOCH to datetime object.
    """
    return datetime.utcfromtimestamp(ts / 1000)

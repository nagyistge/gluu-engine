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
import re

from flask_restful import reqparse

# regex pattern for hostname as defined by RFC 952 and RFC 1123
HOSTNAME_RE = re.compile('^(?![0-9]+$)(?!-)[a-zA-Z0-9-]{,63}(?<!-)$')


def hostname_type(value, name):
    # some provider like AWS uses dotted hostname,
    # e.g. ip-172-31-24-54.ec2.internal
    if all(HOSTNAME_RE.match(v) for v in value.split(".")):
        return value

    raise ValueError(
        "{} is not a valid value for {} parameter".format(value, name))


provider_req = reqparse.RequestParser()
provider_req.add_argument(
    "hostname", type=hostname_type, location="form", required=True,
    help="Hostname FQDN of the provider",
)
provider_req.add_argument(
    "docker_base_url", location="form", required=True,
    help="URL to Docker API, could be unix socket or tcp",
)
provider_req.add_argument("license_id", location="form", default="")
# provider_req.add_argument("public_key", location="form", default="")
# provider_req.add_argument("public_password", location="form", default="")
# provider_req.add_argument("license_password", location="form", default="")

edit_provider_req = provider_req.copy()

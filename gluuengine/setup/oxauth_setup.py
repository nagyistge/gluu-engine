# -*- coding: utf-8 -*-
# Copyright (c) 2015 Gluu
#
# All rights reserved.

import os.path

from blinker import signal

from .base import OxSetup


class OxauthSetup(OxSetup):
    def render_server_xml_template(self):
        """Copies rendered Tomcat's server.xml into the container.
        """
        src = "_shared/server.xml"
        dest = os.path.join(self.container.tomcat_conf_dir, os.path.basename(src))
        ctx = {
            "shib_jks_pass": self.cluster.decrypted_admin_pw,
            "shib_jks_fn": self.cluster.shib_jks_fn,
        }
        self.copy_rendered_jinja_template(src, dest, ctx)

    def add_auto_startup_entry(self):
        """Adds supervisor program for auto-startup.
        """
        src = "_shared/tomcat.conf"
        dest = "/etc/supervisor/conf.d/tomcat.conf"
        self.logger.debug("adding supervisord entry")
        self.copy_rendered_jinja_template(src, dest)

    def setup(self):
        hostname = self.container.hostname

        # render config templates
        self.render_ldap_props_template()
        self.render_server_xml_template()
        self.render_oxauth_context()
        self.write_salt_file()
        self.gen_cert("shibIDP", self.cluster.decrypted_admin_pw,
                      "tomcat", "tomcat", hostname)

        self.gen_keystore(
            "shibIDP",
            self.cluster.shib_jks_fn,
            self.cluster.decrypted_admin_pw,
            "{}/shibIDP.key".format(self.container.cert_folder),
            "{}/shibIDP.crt".format(self.container.cert_folder),
            "tomcat",
            "tomcat",
            hostname,
        )

        self.pull_oxauth_override()
        self.add_auto_startup_entry()
        self.change_cert_access("tomcat", "tomcat")
        self.reload_supervisor()
        return True

    def teardown(self):
        """Teardowns the container.
        """
        complete_sgn = signal("ox_teardown_completed")
        complete_sgn.send(self)

    def after_setup(self):
        """Post-setup callback.
        """
        complete_sgn = signal("ox_setup_completed")
        complete_sgn.send(self)

    def render_oxauth_context(self):
        """Renders oxAuth context file for Tomcat.
        """
        src = "oxauth/oxauth.xml"
        dest = "/opt/tomcat/conf/Catalina/localhost/oxauth.xml"
        ctx = {
            "oxauth_jsf_salt": os.urandom(16).encode("hex"),
        }
        self.copy_rendered_jinja_template(src, dest, ctx)

    def pull_oxauth_override(self):
        for root, _, files in os.walk(self.app.config["OXAUTH_OVERRIDE_DIR"]):
            for fn in files:
                src = os.path.join(root, fn)
                dest = src.replace(self.app.config["OXAUTH_OVERRIDE_DIR"],
                                   "/var/gluu/webapps/oxauth")
                self.logger.debug("copying {} to {}:{}".format(
                    src, self.container.name, dest,
                ))
                self.docker.exec_cmd(
                    self.container.cid,
                    "mkdir -p {}".format(os.path.dirname(dest)),
                )
                self.docker.copy_to_container(self.container.cid, src, dest)

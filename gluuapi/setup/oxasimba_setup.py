# -*- coding: utf-8 -*-
# Copyright (c) 2015 Gluu
#
# All rights reserved.

import os.path
import time
from glob import iglob

from .base import SSLCertMixin
from .base import HostFileMixin
from .oxauth_setup import OxauthSetup


class OxasimbaSetup(HostFileMixin, SSLCertMixin, OxauthSetup):
    def setup(self):
        hostname = self.node.domain_name

        # render config templates
        self.copy_selector_template()
        self.render_ldap_props_template()
        self.render_server_xml_template()
        self.render_httpd_conf()
        self.configure_vhost()

        # customize asimba and rebuild
        self.unpack_jar()
        self.copy_props_template()
        self.render_config_template()

        self.gen_cert("asimba", self.cluster.decrypted_admin_pw,
                      "tomcat", "tomcat", hostname)
        self.gen_cert("httpd", self.cluster.decrypted_admin_pw,
                      "www-data", "www-data", hostname)

        # Asimba keystore
        self.gen_keystore(
            "asimbaIDP",
            self.cluster.asimba_jks_fn,
            self.cluster.decrypted_admin_pw,
            "{}/asimba.key".format(self.node.cert_folder),
            "{}/asimba.crt".format(self.node.cert_folder),
            "tomcat",
            "tomcat",
            hostname,
        )

        # add auto startup entry
        self.add_auto_startup_entry()
        self.change_cert_access("tomcat", "tomcat")
        self.reconfigure_asimba()
        self.reload_supervisor()
        return True

    def add_auto_startup_entry(self):
        payload = """
[program:tomcat]
command=/opt/tomcat/bin/catalina.sh run
environment=CATALINA_PID="/var/run/tomcat.pid"

[program:httpd]
command=/usr/bin/pidproxy /var/run/apache2/apache2.pid /bin/bash -c "source /etc/apache2/envvars && /usr/sbin/apache2ctl -DFOREGROUND"
"""

        self.logger.info("adding supervisord entry")
        jid = self.salt.cmd_async(
            self.node.id,
            'cmd.run',
            ["echo '{}' >> /etc/supervisor/conf.d/supervisord.conf".format(payload)],
        )
        self.salt.subscribe_event(jid, self.node.id)

    def render_server_xml_template(self):
        src = "nodes/oxasimba/server.xml"
        dest = os.path.join(self.node.tomcat_conf_dir, os.path.basename(src))
        ctx = {
            "asimba_jks_pass": self.cluster.decrypted_admin_pw,
            "asimba_jks_fn": self.cluster.asimba_jks_fn,
        }
        self.copy_rendered_jinja_template(src, dest, ctx)

    def render_httpd_conf(self):
        src = "nodes/oxasimba/gluu_httpd.conf"
        file_basename = os.path.basename(src)
        dest = os.path.join("/etc/apache2/sites-available", file_basename)

        ctx = {
            "hostname": self.node.domain_name,
            "weave_ip": self.node.weave_ip,
            "httpd_cert_fn": "/etc/certs/httpd.crt",
            "httpd_key_fn": "/etc/certs/httpd.key",
        }
        self.copy_rendered_jinja_template(src, dest, ctx)

    def unpack_jar(self):
        unpack_cmd = "unzip -qq /opt/tomcat/webapps/oxasimba.war " \
                     "-d /tmp/asimba"
        jid = self.salt.cmd_async(self.node.id, "cmd.run", [unpack_cmd])
        self.salt.subscribe_event(jid, self.node.id)
        time.sleep(5)

    def copy_selector_template(self):
        src = self.get_template_path("nodes/oxasimba/asimba-selector.xml")
        dest = "{}/asimba-selector.xml".format(self.node.tomcat_conf_dir)
        self.salt.copy_file(self.node.id, src, dest)

    def copy_props_template(self):
        src = self.get_template_path("nodes/oxasimba/asimba.properties")
        dest = "/tmp/asimba/WEB-INF/asimba.properties"
        self.salt.copy_file(self.node.id, src, dest)

    def render_config_template(self):
        src = self.get_template_path("nodes/oxasimba/asimba.xml")
        dest = "/tmp/asimba/WEB-INF/conf/asimba.xml"
        ctx = {
            "ox_cluster_hostname": self.cluster.ox_cluster_hostname,
            "asimba_jks_fn": self.cluster.asimba_jks_fn,
            "asimba_jks_pass": self.cluster.decrypted_admin_pw,
            "inum_org_fn": self.cluster.inum_org_fn,
        }
        self.render_template(src, dest, ctx)

    def reconfigure_asimba(self):
        self.logger.info("reconfiguring asimba")

        # rebuild jar
        jar_cmd = "/usr/bin/jar cmf /tmp/asimba/META-INF/MANIFEST.MF " \
                  "/tmp/asimba.war -C /tmp/asimba ."
        jid = self.salt.cmd_async(self.node.id, "cmd.run", [jar_cmd])
        self.salt.subscribe_event(jid, self.node.id)

        # remove oxasimba.war
        rm_cmd = "rm /opt/tomcat/webapps/oxasimba.war"
        jid = self.salt.cmd_async(self.node.id, "cmd.run", [rm_cmd])
        self.salt.subscribe_event(jid, self.node.id)

        # install reconfigured asimba.jar
        mv_cmd = "mv /tmp/asimba.war /opt/tomcat/webapps/asimba.war"
        jid = self.salt.cmd_async(self.node.id, "cmd.run", [mv_cmd])
        self.salt.subscribe_event(jid, self.node.id)

        # remove temporary asimba
        rm_cmd = "rm -rf /tmp/asimba"
        jid = self.salt.cmd_async(self.node.id, "cmd.run", [rm_cmd])
        self.salt.subscribe_event(jid, self.node.id)

    def pull_idp_metadata(self):
        files = iglob("{}/metadata/*-idp-metadata.xml".format(
            self.app.config["OXIDP_OVERRIDE_DIR"],
        ))

        for src in files:
            fn = os.path.basename(src)
            dest = "/opt/idp/metadata/{}".format(fn)
            self.logger.info("copying {}".format(fn))
            self.salt.copy_file(self.node.id, src, dest)

    def discover_nginx(self):
        """Discovers nginx node.
        """
        self.logger.info("discovering available nginx node")
        try:
            # if we already have nginx node in the the cluster,
            # add entry to /etc/hosts and import the cert
            nginx = self.provider.get_node_objects(type_="nginx")[0]
            self.add_nginx_entry(nginx)
            self.import_nginx_cert()
        except IndexError:
            pass

    def after_setup(self):
        """Post-setup callback.
        """
        self.pull_idp_metadata()
        self.discover_nginx()
        self.notify_nginx()

    def teardown(self):
        """Teardowns the node.
        """
        self.notify_nginx()
        self.after_teardown()

    def render_ldap_props_template(self):
        """Copies rendered jinja template for LDAP connection.
        """
        src = "nodes/oxasimba/oxasimba-ldap.properties"
        dest = os.path.join(self.node.tomcat_conf_dir, os.path.basename(src))

        ldap_hosts = ",".join([
            "{}:{}".format(ldap.domain_name, ldap.ldaps_port)
            for ldap in self.cluster.get_ldap_objects()
        ])
        ctx = {
            "ldap_binddn": self.node.ldap_binddn,
            "encoded_ox_ldap_pw": self.cluster.encoded_ox_ldap_pw,
            "ldap_hosts": ldap_hosts,
            "inum_appliance": self.cluster.inum_appliance,
            # "cert_folder": self.node.cert_folder,
        }
        self.copy_rendered_jinja_template(src, dest, ctx)
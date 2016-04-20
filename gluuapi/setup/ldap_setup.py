# -*- coding: utf-8 -*-
# Copyright (c) 2015 Gluu
#
# All rights reserved.

import codecs
import json
import os.path
import time
from glob import iglob
from random import randint

from .base import BaseSetup
from .oxidp_setup import OxidpSetup
from ..utils import generate_base64_contents
from ..utils import get_sys_random_chars
from ..model import STATE_SUCCESS


class LdapSetup(BaseSetup):
    @property
    def ldif_files(self):  # pragma: no cover
        """List of initial ldif files.
        """
        templates = [
            'nodes/opendj/ldif/base.ldif',
            'nodes/opendj/ldif/appliance.ldif',
            'nodes/opendj/ldif/attributes.ldif',
            'nodes/opendj/ldif/scopes.ldif',
            'nodes/opendj/ldif/clients.ldif',
            'nodes/opendj/ldif/people.ldif',
            'nodes/opendj/ldif/groups.ldif',
            'nodes/opendj/ldif/scripts.ldif',
            'nodes/opendj/ldif/asimba.ldif',
        ]
        return map(self.get_template_path, templates)

    def write_ldap_pw(self):
        """Writes temporary LDAP password into a file.

        It is recommended to remove the file after finishing
        any operation that requires password. Calling ``delete_ldap_pw``
        method will remove this password file.
        """
        self.logger.info("writing temporary LDAP password")

        local_dest = os.path.join(self.build_dir, ".pw")
        with codecs.open(local_dest, "w", encoding="utf-8") as fp:
            fp.write(self.cluster.decrypted_admin_pw)

        self.docker.exec_cmd(
            self.container.id,
            "mkdir -p {}".format(os.path.dirname(self.container.ldap_pass_fn)),
        )
        self.docker.copy_to_container(self.container.id, local_dest, self.container.ldap_pass_fn)

    def delete_ldap_pw(self):
        """Removes temporary LDAP password.
        """
        self.logger.info("deleting temporary LDAP password")
        self.docker.exec_cmd(
            self.container.id,
            'rm -f {}'.format(self.container.ldap_pass_fn)
        )

    def add_ldap_schema(self):
        """Renders and copies predefined LDAP schema files into minion.
        """
        ctx = {
            "inum_org_fn": self.cluster.inum_org_fn,
        }
        src = self.get_template_path("nodes/opendj/schema/100-user.ldif")
        dest = os.path.join(self.container.schema_folder, "100-user.ldif")
        self.render_template(src, dest, ctx)

    def setup_opendj(self):
        """Setups OpenDJ server without actually running the server
        in post-installation step.
        """
        src = self.get_template_path("nodes/opendj/opendj-setup.properties")
        dest = os.path.join(self.container.ldap_base_folder, os.path.basename(src))
        ctx = {
            "ldap_hostname": "ldap.gluu.local",
            "ldap_port": self.container.ldap_port,
            "ldaps_port": self.container.ldaps_port,
            "ldap_jmx_port": self.container.ldap_jmx_port,
            "ldap_admin_port": self.container.ldap_admin_port,
            "ldap_binddn": self.container.ldap_binddn,
            "ldap_pass_fn": self.container.ldap_pass_fn,
            "ldap_backend_type": "local-db",  # we're still using OpenDJ 2.6
        }
        self.render_template(src, dest, ctx)

        setupCmd = " ".join([
            self.container.ldap_setup_command,
            '--no-prompt', '--cli', '--doNotStart', '--acceptLicense',
            '--propertiesFilePath', dest,
        ])

        self.logger.info("running opendj setup")
        self.docker.exec_cmd(self.container.id, setupCmd)

        # Use predefined dsjavaproperties
        self.logger.info("running dsjavaproperties")
        self.docker.exec_cmd(self.container.id, self.container.ldap_ds_java_prop_command)

    def configure_opendj(self):
        """Configures OpenDJ.
        """
        config_changes = [
            "set-global-configuration-prop --set single-structural-objectclass-behavior:accept",
            "set-attribute-syntax-prop --syntax-name 'Directory String' --set allow-zero-length-values:true",
            "set-password-policy-prop --policy-name 'Default Password Policy' --set allow-pre-encoded-passwords:true",
            "set-log-publisher-prop --publisher-name 'File-Based Audit Logger' --set enabled:true",
            "create-backend --backend-name site --set base-dn:o=site --type local-db --set enabled:true",
            "set-connection-handler-prop --handler-name 'LDAP Connection Handler' --set enabled:false",
            'set-access-control-handler-prop --remove global-aci:\'(targetattr!=\\"userPassword||authPassword||changes||changeNumber||changeType||changeTime||targetDN||newRDN||newSuperior||deleteOldRDN||targetEntryUUID||changeInitiatorsName||changeLogCookie||includedAttributes\\")(version 3.0; acl \\"Anonymous read access\\"; allow (read,search,compare) userdn=\\"ldap:///anyone\\";)\'',
            "set-global-configuration-prop --set reject-unauthenticated-requests:true",
            "set-password-policy-prop --policy-name 'Default Password Policy' --set default-password-storage-scheme:'Salted SHA-512'",
        ]

        for changes in config_changes:
            dsconfigCmd = " ".join([
                self.container.ldap_dsconfig_command, '--trustAll', '--no-prompt',
                '--hostname', self.container.domain_name,
                '--port', self.container.ldap_admin_port,
                '--bindDN', "'{}'".format(self.container.ldap_binddn),
                '--bindPasswordFile', self.container.ldap_pass_fn,
                changes,
            ])
            self.logger.info("configuring opendj config changes: {}".format(dsconfigCmd))

            dsconfigCmd = '''sh -c "{}"'''.format(dsconfigCmd)
            self.docker.exec_cmd(self.container.id, dsconfigCmd)

    def index_opendj(self, backend):
        """Creates required index in OpenDJ server.
        """

        resp = self.docker.exec_cmd(self.container.id, "cat /opt/opendj/opendj_index.json")  # noqa
        try:
            index_json = json.loads(resp.retval)
        except ValueError:
            self.logger.warn("unable to read JSON string from opendj_index.json")
            index_json = []

        for attr_map in index_json:
            attr_name = attr_map['attribute']

            for index_type in attr_map["index"]:
                for backend_name in attr_map["backend"]:
                    if backend_name != backend:
                        continue

                    self.logger.info(
                        "creating {} attribute for {} index "
                        "in {} backend".format(attr_name, index_type, backend)
                    )

                    index_cmd = " ".join([
                        self.container.ldap_dsconfig_command,
                        'create-local-db-index',
                        '--backend-name', backend,
                        '--type', 'generic',
                        '--index-name', attr_name,
                        '--set', 'index-type:%s' % index_type,
                        '--set', 'index-entry-limit:4000',
                        '--hostName', self.container.domain_name,
                        '--port', self.container.ldap_admin_port,
                        '--bindDN', "'{}'".format(self.container.ldap_binddn),
                        '-j', self.container.ldap_pass_fn,
                        '--trustAll', '--noPropertiesFile', '--no-prompt',
                    ])
                    self.docker.exec_cmd(self.container.id, index_cmd)

    def import_ldif(self):
        """Renders and imports predefined ldif files.
        """

        # template's context
        ctx = {
            "oxauth_client_id": self.cluster.oxauth_client_id,
            "oxauth_client_encoded_pw": self.cluster.oxauth_client_encoded_pw,
            "encoded_ldap_pw": self.cluster.encoded_ldap_pw,
            "encoded_ox_ldap_pw": self.cluster.encoded_ox_ldap_pw,
            "inum_appliance": self.cluster.inum_appliance,
            "hostname": "ldap.gluu.local",
            "ox_cluster_hostname": self.cluster.ox_cluster_hostname,
            "ldaps_port": self.container.ldaps_port,
            "ldap_binddn": self.container.ldap_binddn,
            "inum_org": self.cluster.inum_org,
            "inum_org_fn": self.cluster.inum_org_fn,
            "org_name": self.cluster.org_name,
            "scim_rp_client_id": self.cluster.scim_rp_client_id,
            "oxtrust_hostname": "localhost:8443",
        }

        ldifFolder = '%s/ldif' % self.container.ldap_base_folder
        self.docker.exec_cmd(self.container.id, "mkdir -p {}".format(ldifFolder))

        # render templates
        for ldif_file in self.ldif_files:
            src = ldif_file
            file_basename = os.path.basename(src)
            dest = os.path.join(ldifFolder, file_basename)
            self.render_template(src, dest, ctx)
            backend_id = "userRoot"
            self._run_import_ldif(dest, backend_id)

        # import o_site.ldif
        backend_id = "site"
        dest = "/opt/opendj/ldif/o_site.ldif"
        self._run_import_ldif(dest, backend_id)

    def export_opendj_cert(self):
        """Exports OpenDJ public certificate.
        """
        # Load password to acces OpenDJ truststore
        openDjPinFn = '%s/config/keystore.pin' % self.container.ldap_base_folder
        openDjTruststoreFn = '%s/config/truststore' % self.container.ldap_base_folder
        openDjPin = "`cat {}`".format(openDjPinFn)

        self.docker.exec_cmd(
            self.container.id,
            "touch {}".format(self.container.opendj_cert_fn),
        )

        # Export public OpenDJ certificate
        self.logger.info("exporting OpenDJ certificate")
        cmd = ' '.join([
            self.container.keytool_command, '-exportcert',
            '-keystore', openDjTruststoreFn,
            '-storepass', openDjPin,
            '-file', self.container.opendj_cert_fn,
            '-alias', 'server-cert',
            '-rfc',
        ])
        cmd = '''sh -c "{}"'''.format(cmd)
        self.docker.exec_cmd(self.container.id, cmd)

    def import_opendj_cert(self):
        # Import OpenDJ certificate into java truststore
        self.logger.info("importing OpenDJ certificate into Java truststore")
        cmd = ' '.join([
            "/usr/bin/keytool", "-import", "-trustcacerts",
            "-alias", self.container.domain_name,
            "-file", self.container.opendj_cert_fn,
            "-keystore", self.container.truststore_fn,
            "-storepass", "changeit", "-noprompt",
        ])
        cmd = '''sh -c "{}"'''.format(cmd)
        self.docker.exec_cmd(self.container.id, cmd)

    def replicate_from(self, existing_node):
        """Setups a replication between two OpenDJ servers.

        The data will be replicated from existing OpenDJ server.

        :param existing_node: OpenDJ server where the initial data
                              will be replicated from.
        """
        setup_obj = LdapSetup(existing_node, self.cluster,
                              self.app, logger=self.logger)

        # creates temporary password file
        setup_obj.write_ldap_pw()

        base_dns = ("o=gluu", "o=site",)
        for base_dn in base_dns:
            enable_cmd = " ".join([
                "/opt/opendj/bin/dsreplication", "enable",
                "--host1", existing_node.domain_name,
                "--port1", existing_node.ldap_admin_port,
                "--bindDN1", "'{}'".format(existing_node.ldap_binddn),
                "--bindPasswordFile1", self.container.ldap_pass_fn,
                "--replicationPort1", existing_node.ldap_replication_port,
                "--host2", self.container.domain_name,
                "--port2", self.container.ldap_admin_port,
                "--bindDN2", "'{}'".format(self.container.ldap_binddn),
                "--bindPasswordFile2", self.container.ldap_pass_fn,
                "--replicationPort2", self.container.ldap_replication_port,
                "--adminUID", "admin",
                "--adminPasswordFile", self.container.ldap_pass_fn,
                "--baseDN", "'{}'".format(base_dn),
                "--secureReplication1", "--secureReplication2",
                "-X", "-n", "-Q",
            ])
            self.logger.info("enabling {!r} replication between {} and {}".format(
                base_dn, existing_node.weave_ip, self.container.weave_ip,
            ))
            self.docker.exec_cmd(self.container.id, enable_cmd)

            # wait before initializing the replication to ensure it
            # has been enabled
            time.sleep(10)

            init_cmd = " ".join([
                "/opt/opendj/bin/dsreplication", "initialize",
                "--baseDN", "'{}'".format(base_dn),
                "--adminUID", "admin",
                "--adminPasswordFile", self.container.ldap_pass_fn,
                "--hostSource", existing_node.domain_name,
                "--portSource", existing_node.ldap_admin_port,
                "--hostDestination", self.container.domain_name,
                "--portDestination", self.container.ldap_admin_port,
                "-X", "-n", "-Q",
            ])
            self.logger.info("initializing {!r} replication between {} and {}".format(
                base_dn, existing_node.weave_ip, self.container.weave_ip,
            ))
            self.docker.exec_cmd(self.container.id, init_cmd)
            time.sleep(5)

        self.logger.info("see related logs at {}:/tmp directory "
                         "for replication process".format(self.container.name))

        # cleanups temporary password file
        setup_obj.delete_ldap_pw()

    def add_auto_startup_entry(self):
        """Adds supervisor program for auto-startup.
        """
        # add supervisord entry
        payload = """
[program:opendj]
command=/opt/opendj/bin/start-ds --quiet -N
"""

        self.logger.info("adding supervisord entry")
        cmd = '''sh -c "echo '{}' >> /etc/supervisor/conf.d/supervisord.conf"'''.format(payload)
        self.docker.exec_cmd(self.container.id, cmd)

    def setup(self):
        """Runs the actual setup.
        """
        self.write_ldap_pw()
        self.add_ldap_schema()
        self.import_custom_schema()
        self.setup_opendj()
        self.add_auto_startup_entry()
        self.reload_supervisor()
        self.ensure_opendj_running()
        self.configure_opendj()
        self.index_opendj("site")
        self.index_opendj("userRoot")

        try:
            peer_node = self.cluster.get_ldap_objects()[0]
            # Initialize data from existing ldap node.
            # To create fully meshed replication, update the other
            # ldap node to use this new ldap node as a master.
            self.replicate_from(peer_node)
        except IndexError:
            self.import_ldif()
            self.import_base64_scim_config()
            self.import_base64_config()

        self.export_opendj_cert()
        self.import_opendj_cert()
        self.delete_ldap_pw()
        return True

    def notify_ox(self):
        """Notify all ox* apps.

        Typically this method should be called after adding/removing
        any OpenDJ server.
        """
        # import all OpenDJ certficates because oxIdp checks matched
        # certificate
        for oxidp in self.cluster.get_oxidp_objects():
            setup_obj = OxidpSetup(oxidp, self.cluster,
                                   self.app, logger=self.logger)
            setup_obj.import_ldap_certs()

    def after_setup(self):
        """Runs post-setup.
        """
        if self.container.state == STATE_SUCCESS:
            self.notify_ox()

    def teardown(self):
        """Teardowns the node.
        """
        self.write_ldap_pw()

        # stop the replication agreement
        ldap_num = len(self.cluster.get_ldap_objects())
        if ldap_num > 0:
            self.disable_replication()
            # wait for process to run in the background
            time.sleep(5)

        # remove password file
        self.delete_ldap_pw()

        if self.container.state == STATE_SUCCESS:
            self.notify_ox()

    def import_custom_schema(self):
        """Copies user-defined LDAP schema into the node.
        """
        files = iglob("{}/*.ldif".format(self.app.config["CUSTOM_LDAP_SCHEMA_DIR"]))
        for file_ in files:
            if not os.path.isfile(file_):
                continue
            basename = os.path.basename(file_)
            dest = "{}/{}".format(self.container.schema_folder, basename)
            self.logger.info("copying {}".format(basename))
            self.docker.copy_to_container(self.container.id, file_, dest)

    def disable_replication(self):
        """Disable replication setup for current node.
        """
        self.logger.info("disabling replication for {}".format(self.container.weave_ip))
        disable_repl_cmd = " ".join([
            "{}/bin/dsreplication".format(self.container.ldap_base_folder),
            "disable",
            "--hostname", self.container.domain_name,
            "--port", self.container.ldap_admin_port,
            "--adminUID", "admin",
            "--adminPasswordFile", self.container.ldap_pass_fn,
            "-X", "-n", "--disableAll",
        ])
        self.docker.exec_cmd(self.container.id, disable_repl_cmd)

    def import_base64_config(self):
        """Copies rendered configuration.ldif and imports into LDAP.
        """
        ctx = {
            "inum_appliance": self.cluster.inum_appliance,
            "oxauth_config_base64": generate_base64_contents(self.render_oxauth_config(), 1),
            "oxauth_static_conf_base64": generate_base64_contents(self.render_oxauth_static_config(), 1),
            "oxauth_error_base64": generate_base64_contents(self.render_oxauth_error_config(), 1),
            "oxauth_openid_key_base64": generate_base64_contents(self.gen_openid_key(), 1),
            "oxtrust_config_base64": generate_base64_contents(self.render_oxtrust_config(), 1),
            "oxtrust_cache_refresh_base64": generate_base64_contents(self.render_oxtrust_cache_refresh(), 1),
            "oxtrust_import_person_base64": generate_base64_contents(self.render_oxtrust_import_person(), 1),
            "oxidp_config_base64": generate_base64_contents(self.render_oxidp_config(), 1),
            "oxcas_config_base64": generate_base64_contents(self.render_oxcas_config(), 1),
            "oxasimba_config_base64": generate_base64_contents(self.render_oxasimba_config(), 1),
        }
        self.copy_rendered_jinja_template(
            "nodes/opendj/ldif/configuration.ldif",
            "/opt/opendj/ldif/configuration.ldif",
            ctx,
        )
        self._run_import_ldif("/opt/opendj/ldif/configuration.ldif", "userRoot")

    def gen_openid_key(self):
        """Generates OpenID Connect key.
        """
        def extra_jar_abspath(jar):
            return "/opt/gluu/lib/{}".format(jar)

        jars = map(extra_jar_abspath, [
            "bcprov-jdk16-1.46.jar",
            "jettison-1.3.jar",
            "commons-lang-2.6.jar",
            "log4j-1.2.17.jar",
            "commons-codec-1.5.jar",
            "oxauth-model-2.4.3.Final.jar",
            "oxauth-server-2.4.3.Final.jar",
        ])
        classpath = ":".join(jars)
        resp = self.docker.exec_cmd(
            self.container.id,
            "java -cp {} org.xdi.oxauth.util.KeyGenerator".format(classpath),
        )
        return resp.retval

    def render_oxauth_config(self):
        """Renders oxAuth configuration.
        """
        src = "nodes/oxauth/oxauth-config.json"
        ctx = {
            "ox_cluster_hostname": self.cluster.ox_cluster_hostname,
            "inum_appliance": self.cluster.inum_appliance,
            "inum_org": self.cluster.inum_org,
            "pairwise_calculation_key": get_sys_random_chars(randint(20, 30)),
            "pairwise_calculation_salt": get_sys_random_chars(randint(20, 30)),
        }
        return self.render_jinja_template(src, ctx)

    def render_oxauth_static_config(self):
        """Renders oxAuth static configuration.
        """
        src = "nodes/oxauth/oxauth-static-conf.json"
        ctx = {
            "inum_org": self.cluster.inum_org,
        }
        return self.render_jinja_template(src, ctx)

    def render_oxauth_error_config(self):
        """Renders oxAuth error configuration.
        """
        src = "nodes/oxauth/oxauth-errors.json"
        return self.render_jinja_template(src)

    def render_oxtrust_config(self):
        """Renders oxTrust configuration.
        """
        src = "nodes/oxtrust/oxtrust-config.json"
        ctx = {
            "inum_appliance": self.cluster.inum_appliance,
            "inum_org": self.cluster.inum_org,
            "admin_email": self.cluster.admin_email,
            "ox_cluster_hostname": self.cluster.ox_cluster_hostname,
            "shib_jks_fn": self.cluster.shib_jks_fn,
            "shib_jks_pass": self.cluster.decrypted_admin_pw,
            "inum_org_fn": self.cluster.inum_org_fn,
            "encoded_shib_jks_pw": self.cluster.encoded_shib_jks_pw,
            "encoded_ox_ldap_pw": self.cluster.encoded_ox_ldap_pw,
            "oxauth_client_id": self.cluster.oxauth_client_id,
            "oxauth_client_encoded_pw": self.cluster.oxauth_client_encoded_pw,
            "truststore_fn": self.container.truststore_fn,
            "ldap_hosts": "ldap.gluu.local:{}".format(self.cluster.ldaps_port),
            "config_generation": "true",
            "scim_rs_client_id": self.cluster.scim_rs_client_id,
            "oxtrust_hostname": "localhost:8443",
        }
        return self.render_jinja_template(src, ctx)

    def render_oxtrust_cache_refresh(self):
        """Renders oxTrust CR configuration.
        """
        src = "nodes/oxtrust/oxtrust-cache-refresh.json"
        ctx = {
            "ldap_binddn": self.container.ldap_binddn,
            "encoded_ox_ldap_pw": self.cluster.encoded_ox_ldap_pw,
            "ldap_hosts": "ldap.gluu.local:{}".format(self.cluster.ldaps_port),
        }
        return self.render_jinja_template(src, ctx)

    def render_oxidp_config(self):
        """Renders oxIdp configuration.
        """
        src = "nodes/oxidp/oxidp-config.json"
        ctx = {
            "ox_cluster_hostname": self.cluster.ox_cluster_hostname,
            "oxauth_client_id": self.cluster.oxauth_client_id,
            "oxauth_client_encoded_pw": self.cluster.oxauth_client_encoded_pw,
            "oxtrust_hostname": "localhost:8443",
        }
        return self.render_jinja_template(src, ctx)

    def import_base64_scim_config(self):
        """Copies SCIM configuration (scim.ldif) into the node
        and imports into LDAP.
        """
        ctx = {
            "inum_org": self.cluster.inum_org,
            "ox_cluster_hostname": self.cluster.ox_cluster_hostname,
            "scim_rs_client_id": self.cluster.scim_rs_client_id,
            "scim_rp_client_id": self.cluster.scim_rp_client_id,
            "scim_rs_client_base64_jwks": generate_base64_contents(self.gen_openid_key(), 1),
            "scim_rp_client_base64_jwks": generate_base64_contents(self.gen_openid_key(), 1),
            "oxtrust_hostname": "localhost:8443",
        }
        self.copy_rendered_jinja_template(
            "nodes/opendj/ldif/scim.ldif",
            "/opt/opendj/ldif/scim.ldif",
            ctx,
        )
        self._run_import_ldif("/opt/opendj/ldif/scim.ldif", "userRoot")

    def render_oxtrust_import_person(self):
        """Renders oxTrust import person configuration.
        """
        src = "nodes/oxtrust/oxtrust-import-person.json"
        ctx = {}
        return self.render_jinja_template(src, ctx)

    def ensure_opendj_running(self):
        max_retry = 6
        retry_attempt = 0

        while retry_attempt < max_retry:
            status_cmd = "supervisorctl status opendj"
            resp = self.docker.exec_cmd(self.container.id, status_cmd)

            if "RUNNING" in resp.retval:
                break
            else:
                self.logger.warn("opendj is not running; retrying ...")
                time.sleep(10)
                retry_attempt += 1

    def render_oxcas_config(self):
        """Renders oxCAS configuration.
        """
        src = "nodes/oxcas/oxcas-config.json"
        ctx = {
            "ox_cluster_hostname": self.cluster.ox_cluster_hostname,
            "oxauth_client_id": self.cluster.oxauth_client_id,
            "oxauth_client_encoded_pw": self.cluster.oxauth_client_encoded_pw,
        }
        return self.render_jinja_template(src, ctx)

    def render_oxasimba_config(self):
        """Renders oxAsimba configuration.
        """
        src = "nodes/oxasimba/oxasimba-config.json"
        ctx = {
            "inum_org": self.cluster.inum_org,
        }
        return self.render_jinja_template(src, ctx)

    def _run_import_ldif(self, ldif_fn, backend_id):
        file_basename = os.path.basename(ldif_fn)
        importCmd = " ".join([
            self.container.import_ldif_command,
            '--ldifFile', ldif_fn,
            '--backendID', backend_id,
            '--hostname', self.container.domain_name,
            '--port', self.container.ldap_admin_port,
            '--bindDN', "'{}'".format(self.container.ldap_binddn),
            '-j', self.container.ldap_pass_fn,
            "--rejectFile", "/tmp/rejected-{}".format(file_basename),
            '--append',
            '--trustAll',
        ])
        self.logger.info("importing {}".format(file_basename))
        self.docker.exec_cmd(self.container.id, importCmd)

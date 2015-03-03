# -*- coding: utf-8 -*-
# The MIT License (MIT)
#
# Copyright (c) 2014 Gluu
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
import json
import os.path

from api.helper.common_helper import run


class ldapSetup(object):
    def __init__(self, node, cluster):
        # salt supresses the flask logger, hence we import salt inside
        # this function as a workaround
        import salt.client

        self.saltlocal = salt.client.LocalClient()
        self.node = node
        self.cluster = cluster
        #saltlocal.cmd(self.id, 'cmd.run', [dsconfigCmd])
        #saltlocal.cmd(self.id, 'cp.get_file', [schemaFile, self.schemaFolder])

    def write_ldap_pw(self):
        self.saltlocal.cmd(
            self.node.id,
            ["cmd.run", "cmd.run", "cmd.run"],
            [
                ["mkdir -p {}".format(os.path.dirname(self.node.ldapPassFn))],
                ["echo {} > {}".format(self.node.ldapPass,
                                       self.node.ldapPassFn)],
                ["chown ldap:ldap {}".format(self.node.ldapPassFn)],
            ],
        )

    def delete_ldap_pw(self):
        self.saltlocal.cmd(
            self.node.id,
            'cmd.run',
            ['rm -f {}'.format(self.node.ldapPassFn)],
        )

    def add_ldap_schema(self):
        try:
            # non-rendered schema files
            schemaFiles = [
                "api/templates/salt/ldap/opendj/schema/101-ox.ldif",
                "api/templates/salt/ldap/opendj/schema/77-customAttributes.ldif",
                "api/templates/salt/ldap/opendj/schema/96-eduperson.ldif",
            ]
            for schema in schemaFiles:
                run('salt-cp {} {} {}'.format(self.node.id, schema,
                                              self.node.schemaFolder))

            # rendered schema files
            with open("api/templates/salt/ldap/opendj/schema/100-user.ldif") as fp:
                content = fp.read().format(inumOrgFN=self.cluster.inumOrgFN)
                dest = os.path.join(self.node.schemaFolder, "100-user.ldif")
                self.saltlocal.cmd(
                    self.node.id,
                    "cmd.run",
                    ["echo '{}' > {}".format(content, dest)],
                )
        except Exception as exc:
            print(exc)
            raise

    def setup_opendj(self):
        self.add_ldap_schema()

        # opendj-setup.properties template source
        setup_prop_tmpl = "api/templates/salt/ldap/opendj" \
                          "/opendj-setup.properties"

        # opendj-setup.properties template destination
        setupPropsFN = os.path.join(self.node.ldapBaseFolder,
                                    'opendj-setup.properties')

        try:
            with open(setup_prop_tmpl, "r") as fp:
                content = fp.read().format(
                    ldap_hostname=self.node.local_hostname,
                    ldap_port=self.node.ldap_port,
                    ldaps_port=self.node.ldaps_port,
                    ldap_jmx_port=self.node.ldap_jmx_port,
                    ldap_admin_port=self.node.ldap_admin_port,
                    ldap_binddn=self.node.ldap_binddn,
                    ldapPassFn=self.node.ldapPassFn,
                )

            # Copy opendj-setup.properties so user ldap can find it
            # in /opt/opendj
            self.saltlocal.cmd(
                self.node.id,
                "cmd.run",
                ["echo '{}' > {}".format(content, setupPropsFN)],
            )
        except Exception as exc:
            print(exc)
            raise

        # change_ownership
        self.saltlocal.cmd(
            self.node.id,
            'cmd.run',
            ['chown -R ldap:ldap {}'.format(self.node.ldapBaseFolder)],
        )

        try:
            setupCmd = " ".join([self.node.ldapSetupCommand,
                                 '--no-prompt',
                                 '--cli',
                                 '--propertiesFilePath',
                                 setupPropsFN,
                                 '--acceptLicense'])

            # FIXME:
            #
            # 1 - missing ``/opt/opendj/./config/config.ldif``
            # 2 - missing ``/opt/opendj/config/java.properties``
            self.saltlocal.cmd(
                self.node.id,
                'cmd.run',
                ["su ldap -c 'cd /opt && {}'".format(setupCmd)],
            )
        except Exception as exc:
            print(exc)
            # log "Error running LDAP setup script"
            raise

        # try:
        #     self.saltlocal.cmd(
        #         self.node.id,
        #         'cmd.run',
        #         ['su ldap -c {}'.format(self.node.ldapDsJavaPropCommand)],
        #     )
        # except Exception as exc:
        #     #log "Error running dsjavaproperties"
        #     print(exc)
        #     raise

    def configure_opendj(self):
        try:
            config_changes = [['set-global-configuration-prop', '--set', 'single-structural-objectclass-behavior:accept'],
                              ['set-attribute-syntax-prop', '--syntax-name', '"Directory String"', '--set', 'allow-zero-length-values:true'],
                              ['set-password-policy-prop', '--policy-name', '"Default Password Policy"', '--set', 'allow-pre-encoded-passwords:true'],
                              ['set-log-publisher-prop', '--publisher-name', '"File-Based Audit Logger"', '--set', 'enabled:true'],
                              ['create-backend', '--backend-name', 'site', '--set', 'base-dn:o=site', '--type local-db', '--set', 'enabled:true']]
            for changes in config_changes:
                dsconfigCmd = " ".join([self.node.ldapDsconfigCommand,
                                        '--trustAll',
                                        '--no-prompt',
                                        '--hostname',
                                        self.node.ldap_hostname,
                                        '--port',
                                        self.node.ldap_admin_port,
                                        '--bindDN',
                                        '"%s"' % self.node.ldap_binddn,
                                        '--bindPasswordFile',
                                        self.node.ldapPassFn] + changes)
                self.saltlocal.cmd(self.node.id, 'cmd.run', ['su ldap -c {}'.format(dsconfigCmd)])
        except:
            #log "Error executing config changes"
            pass

    def index_opendj(self):
        try:
            # This json file contains a mapping of the required indexes.
            # [ { "attribute": "inum", "type": "string", "index": ["equality"] }, ...}
            try:
                with open(self.node.indexJson, 'r') as fp:
                    index_json = json.load(fp)
            except:
                #log "bad jason file"
                pass

            if index_json:
                for attrDict in index_json:
                    attr_name = attrDict['attribute']
                    index_types = attrDict['index']
                    for index_type in index_types:
                        # log "Creating %s index for attribute %s" % (index_type, attr_name)
                        indexCmd = " ".join([self.node.ldapDsconfigCommand,
                                             'create-local-db-index',
                                             '--backend-name',
                                             'userRoot',
                                             '--type',
                                             'generic',
                                             '--index-name',
                                             attr_name,
                                             '--set',
                                             'index-type:%s' % index_type,
                                             '--set',
                                             'index-entry-limit:4000',
                                             '--hostName',
                                             self.node.ldap_hostname,
                                             '--port',
                                             self.node.ldap_admin_port,
                                             '--bindDN',
                                             '"%s"' % self.node.ldap_binddn,
                                             '-j', self.node.ldapPassFn,
                                             '--trustAll',
                                             '--noPropertiesFile',
                                             '--no-prompt'])
                        self.saltlocal.cmd(self.node.id, 'cmd.run', ['su ldap -c {}'.format(indexCmd)])
            else:
                # log 'NO indexes found %s' % self.node.indexJson
                pass
        except:
            #log "Error occured during LDAP indexing"
            pass

    def import_ldif(self):
        ldifFolder = '%s/ldif' % self.node.ldapBaseFolder
        for ldif_file_fn in self.node.ldif_files:
            run('salt-cp {} {} {}'.format(self.node.id, ldif_file_fn, ldifFolder))
            ldif_file_fullpath = "%s/ldif/%s" % (self.node.ldapBaseFolder,
                                                 os.path.split(ldif_file_fn)[-1])
            self.saltlocal.cmd(self.node.id, 'cmd.run', ['chown ldap:ldap {}'.format(ldif_file_fullpath)])
            importCmd = " ".join([self.node.importLdifCommand,
                                  '--ldifFile',
                                  ldif_file_fullpath,
                                  '--backendID',
                                  'userRoot',
                                  '--hostname',
                                  self.node.ldap_hostname,
                                  '--port',
                                  self.node.ldap_admin_port,
                                  '--bindDN',
                                  '"%s"' % self.node.ldap_binddn,
                                  '-j',
                                  self.node.ldapPassFn,
                                  '--append',
                                  '--trustAll'])
            self.saltlocal.cmd(self.node.id, 'cmd.run', ['su ldap -c {}'.format(importCmd)])

        run('salt-cp {} {} {}'.format(self.node.id, '{}/static/cache-refresh/o_site.ldif'.format(self.node.install_dir), ldifFolder))
        site_ldif_fn = "%s/o_site.ldif" % ldifFolder
        self.saltlocal.cmd(self.node.id, 'cmd.run', ['chown ldap:ldap {}'.format(site_ldif_fn)])
        importCmd = " ".join([self.node.importLdifCommand,
                              '--ldifFile',
                              site_ldif_fn,
                              '--backendID',
                              'site',
                              '--hostname',
                              self.node.ldap_hostname,
                              '--port',
                              self.node.ldap_admin_port,
                              '--bindDN',
                              '"%s"' % self.node.ldap_binddn,
                              '-j',
                              self.node.ldapPassFn,
                              '--append',
                              '--trustAll'])
        self.saltlocal.cmd(self.node.id, 'cmd.run', ['su ldap -c {}'.format(importCmd)])

    #TODO : need to deside how to port this function
    def export_opendj_public_cert(self):
        # Load password to acces OpenDJ truststore
        openDjPinFn = '%s/config/keystore.pin' % self.node.ldapBaseFolder
        openDjTruststoreFn = '%s/config/truststore' % self.node.ldapBaseFolder
            
        outd = self.saltlocal.cmd(self.node.id, 'cmd.run', ['cat {}'.format(openDjPinFn)])
        openDjPin = outd[self.node.id].strip()
        # Export public OpenDJ certificate
        cmdsrt = ' '.join([self.node.keytoolCommand,
                            '-exportcert',
                            '-keystore',
                            openDjTruststoreFn,
                            '-storepass',
                            openDjPin,
                            '-file',
                            self.node.openDjCertFn,
                            '-alias',
                            'server-cert',
                            '-rfc'])

        # Import OpenDJ certificate into java truststore
        # log "Import OpenDJ certificate"
        self.saltlocal.cmd(self.node.id, 'cmd.run', ['cat {}'.format(cmdsrt)])

        cmdstr = ' '.join(["/usr/bin/keytool", "-import", "-trustcacerts", "-alias", "%s_opendj" % self.hostname,
                          "-file", self.openDjCertFn, "-keystore", self.defaultTrustStoreFN,
                          "-storepass", "changeit", "-noprompt"])
        self.saltlocal.cmd(self.node.id, 'cmd.run', ['cat {}'.format(cmdsrt)])

    def setup(self):
        self.write_ldap_pw()
        self.setup_opendj()
        # self.configure_opendj()
        # self.index_opendj()
        # self.import_ldif()
        self.delete_ldap_pw()
        # self.export_opendj_public_cert()
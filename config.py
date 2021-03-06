#!/usr/bin/env python3

import os
import logging

logger = logging.getLogger('marathon_lb')


class ConfigTemplate:
    def __init__(self, name, value, overridable, description):
        self.name = name
        self.full_name = 'HAPROXY_' + name
        self.value = value
        self.default_value = value
        self.overridable = overridable
        self.description = description


class ConfigTemplater(object):
    def add_template(self, template):
        self.t[template.name] = template

    def load(self):
        self.add_template(
            ConfigTemplate(name='HEAD',
                           value='''\
global
  daemon
  log /dev/log local0
  log /dev/log local1 notice
  maxconn 50000
  tune.ssl.default-dh-param 2048
  ssl-default-bind-ciphers ECDHE-ECDSA-CHACHA20-POLY1305:\
ECDHE-RSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:\
ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:\
ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:\
DHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA256:\
ECDHE-ECDSA-AES128-SHA:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-SHA:\
ECDHE-ECDSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA:ECDHE-RSA-AES256-SHA:\
DHE-RSA-AES128-SHA256:DHE-RSA-AES128-SHA:DHE-RSA-AES256-SHA256:\
DHE-RSA-AES256-SHA:ECDHE-ECDSA-DES-CBC3-SHA:ECDHE-RSA-DES-CBC3-SHA:\
EDH-RSA-DES-CBC3-SHA:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:\
AES256-SHA256:AES128-SHA:AES256-SHA:DES-CBC3-SHA:!DSS
  ssl-default-bind-options no-sslv3 no-tls-tickets
  ssl-default-server-ciphers ECDHE-ECDSA-CHACHA20-POLY1305:\
ECDHE-RSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:\
ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:\
ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:\
DHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA256:\
ECDHE-ECDSA-AES128-SHA:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-SHA:\
ECDHE-ECDSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA:ECDHE-RSA-AES256-SHA:\
DHE-RSA-AES128-SHA256:DHE-RSA-AES128-SHA:DHE-RSA-AES256-SHA256:\
DHE-RSA-AES256-SHA:ECDHE-ECDSA-DES-CBC3-SHA:ECDHE-RSA-DES-CBC3-SHA:\
EDH-RSA-DES-CBC3-SHA:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:\
AES256-SHA256:AES128-SHA:AES256-SHA:DES-CBC3-SHA:!DSS
  ssl-default-server-options no-sslv3 no-tls-tickets
  stats socket /var/run/haproxy/socket
  server-state-file global
  server-state-base /var/state/haproxy/
  lua-load /marathon-lb/getpids.lua
  lua-load /marathon-lb/getconfig.lua
defaults
  load-server-state-from-file global
  log               global
  retries                   3
  backlog               10000
  maxconn               10000
  timeout connect          3s
  timeout client          30s
  timeout server          30s
  timeout tunnel        3600s
  timeout http-keep-alive  1s
  timeout http-request    15s
  timeout queue           30s
  timeout tarpit          60s
  option            redispatch
  option            http-server-close
  option            dontlognull
listen stats
  bind 0.0.0.0:9090
  balance
  mode http
  stats enable
  monitor-uri /_haproxy_health_check
  acl getpid path /_haproxy_getpids
  http-request use-service lua.getpids if getpid
  acl getconfig path /_haproxy_getconfig
  http-request use-service lua.getconfig if getconfig
''',
                           overridable=False,
                           description='''\
The head of the HAProxy config. This contains global settings
and defaults.
'''))

        self.add_template(
            ConfigTemplate(name='HTTP_FRONTEND_HEAD',
                           value='''
frontend marathon_http_in
  bind *:80
  mode http
''',
                           overridable=False,
                           description='''\
An HTTP frontend that binds to port *:80 by default and gathers
all virtual hosts as defined by the `HAPROXY_{n}_VHOST` label.
'''))

        self.add_template(
            ConfigTemplate(name='HTTP_FRONTEND_APPID_HEAD',
                           value='''
frontend marathon_http_appid_in
  bind *:9091
  mode http
''',
                           overridable=False,
                           description='''\
An HTTP frontend that binds to port *:9091 by default and gathers
all apps in HTTP mode.
To use this frontend to forward to your app, configure the app with
`HAPROXY_0_MODE=http` then you can access it via a call to the :9091
with the header "X-Marathon-App-Id" set to the Marathon AppId.
Note multiple HTTP ports being exposed by the same marathon app are not
supported. Only the first HTTP port is available via this frontend.
'''))

        # TODO(lloesche): make certificate path dynamic and allow multi-certs
        self.add_template(
            ConfigTemplate(name='HTTPS_FRONTEND_HEAD',
                           value='''
frontend marathon_https_in
  bind *:443 ssl {sslCerts}
  mode http
''',
                           overridable=False,
                           description='''\
An HTTPS frontend for encrypted connections that binds to port *:443 by
default and gathers all virtual hosts as defined by the
`HAPROXY_{n}_VHOST` label. You must modify this file to
include your certificate.
'''))

        self.add_template(
            ConfigTemplate(name='FRONTEND_HEAD',
                           value='''
frontend {backend}
  bind {bindAddr}:{servicePort}{sslCert}{bindOptions}
  mode {mode}
''',
                           overridable=True,
                           description='''\
Defines the address and port to bind to for this frontend.
'''))

        self.add_template(
            ConfigTemplate(name='BACKEND_HEAD',
                           value='''
backend {backend}
  balance {balance}
  mode {mode}
''',
                           overridable=True,
                           description='''\
Defines the type of load balancing, roundrobin by default,
and connection mode, TCP or HTTP.
'''))

        self.add_template(
            ConfigTemplate(name='BACKEND_REDIRECT_HTTP_TO_HTTPS',
                           value='''\
  redirect scheme https code 301 if !{{ ssl_fc }} host_{cleanedUpHostname}
''',
                           overridable=True,
                           description='''\
This template is used with backends where the
`HAPROXY_{n}_REDIRECT_TO_HTTPS` label is set to true
'''))

        self.add_template(
            ConfigTemplate(name='BACKEND_REDIRECT_HTTP_TO_HTTPS_WITH_PATH',
                           value='''\
  redirect scheme https code 301 if !{{ ssl_fc }} host_{cleanedUpHostname}\
 path_{backend}
''',
                           overridable=True,
                           description='''\
Same as `HAPROXY_BACKEND_REDIRECT_HTTP_TO_HTTPS`,
but includes a path.
'''))

        self.add_template(
            ConfigTemplate(name='BACKEND_HSTS_OPTIONS',
                           value='''\
  rspadd  Strict-Transport-Security:\ max-age=15768000
''',
                           overridable=True,
                           description='''\
This template is used for the backend where the
`HAPROXY_{n}_USE_HSTS` label is set to true.
'''))

        self.add_template(
            ConfigTemplate(name='HTTP_FRONTEND_ACL',
                           value='''\
  acl host_{cleanedUpHostname} hdr(host) -i {hostname}
  use_backend {backend} if host_{cleanedUpHostname}
''',
                           overridable=True,
                           description='''\
The ACL that glues a backend to the corresponding virtual host
of the `HAPROXY_HTTP_FRONTEND_HEAD`
'''))

        self.add_template(
            ConfigTemplate(name='HTTP_FRONTEND_ACL_ONLY',
                           value='''\
  acl host_{cleanedUpHostname} hdr(host) -i {hostname}
''',
                           overridable=True,
                           description='''\
Define the ACL matching a particular hostname, but unlike
`HAPROXY_HTTP_FRONTEND_ACL`, only do the ACL portion. Does not glue
the ACL to the backend. This is useful only in the case of multiple
vhosts routing to the same backend.
'''))

        self.add_template(
            ConfigTemplate(name='HTTP_FRONTEND_ROUTING_ONLY',
                           value='''\
  use_backend {backend} if host_{cleanedUpHostname}
''',
                           overridable=True,
                           description='''\
This is the counterpart to `HAPROXY_HTTP_FRONTEND_ACL_ONLY` which
glues the acl name to the appropriate backend.
'''))

        self.add_template(
            ConfigTemplate(name='HTTP_FRONTEND_ACL_WITH_PATH',
                           value='''\
  acl host_{cleanedUpHostname} hdr(host) -i {hostname}
  acl path_{backend} path_beg {path}
  use_backend {backend} if host_{cleanedUpHostname} path_{backend}
''',
                           overridable=True,
                           description='''\
The ACL that glues a backend to the corresponding virtual host with path
of the `HAPROXY_HTTP_FRONTEND_HEAD`.
'''))

        self.add_template(
            ConfigTemplate(name='HTTP_FRONTEND_ACL_ONLY_WITH_PATH',
                           value='''\
  acl path_{backend} path_beg {path}
''',
                           overridable=True,
                           description='''\
Define the ACL matching a particular hostname with path, but unlike
`HAPROXY_HTTP_FRONTEND_ACL_WITH_PATH`, only do the ACL portion. Does not glue
the ACL to the backend. This is useful only in the case of multiple
vhosts routing to the same backend
'''))

        self.add_template(
            ConfigTemplate(name='HTTPS_FRONTEND_ACL_ONLY_WITH_PATH',
                           value='''\
  acl path_{backend} path_beg {path}
''',
                           overridable=True,
                           description='''\
Same as HTTP_FRONTEND_ACL_ONLY_WITH_PATH, but for HTTPS.
'''))

        self.add_template(
            ConfigTemplate(name='HTTP_FRONTEND_ROUTING_ONLY_WITH_PATH',
                           value='''\
  use_backend {backend} if host_{cleanedUpHostname} path_{backend}
''',
                           overridable=True,
                           description='''\
This is the counterpart to `HAPROXY_HTTP_FRONTEND_ACL_ONLY_WITH_PATH` which
glues the acl names to the appropriate backend
'''))

        self.add_template(
            ConfigTemplate(name='HTTP_FRONTEND_APPID_ACL',
                           value='''\
  acl app_{cleanedUpAppId} hdr(x-marathon-app-id) -i {appId}
  use_backend {backend} if app_{cleanedUpAppId}
''',
                           overridable=True,
                           description='''\
The ACL that glues a backend to the corresponding app
of the `HAPROXY_HTTP_FRONTEND_APPID_HEAD`.
'''))

        self.add_template(
            ConfigTemplate(name='HTTPS_FRONTEND_ACL',
                           value='''\
  use_backend {backend} if {{ ssl_fc_sni {hostname} }}
''',
                           overridable=True,
                           description='''\
The ACL that performs the SNI based hostname matching
for the `HAPROXY_HTTPS_FRONTEND_HEAD` template.
'''))

        self.add_template(
            ConfigTemplate(name='HTTPS_FRONTEND_ACL_WITH_PATH',
                           value='''\
  use_backend {backend} if {{ ssl_fc_sni {hostname} }} path_{backend}
''',
                           overridable=True,
                           description='''\
The ACL that performs the SNI based hostname matching with path
for the `HAPROXY_HTTPS_FRONTEND_HEAD` template.
'''))

        self.add_template(
            ConfigTemplate(name='BACKEND_HTTP_OPTIONS',
                           value='''\
  option forwardfor
  http-request set-header X-Forwarded-Port %[dst_port]
  http-request add-header X-Forwarded-Proto https if { ssl_fc }
''',
                           overridable=True,
                           description='''\
Sets HTTP headers, for example X-Forwarded-For and X-Forwarded-Proto.
'''))

        self.add_template(
            ConfigTemplate(name='BACKEND_HTTP_HEALTHCHECK_OPTIONS',
                           value='''\
  option  httpchk GET {healthCheckPath}
  timeout check {healthCheckTimeoutSeconds}s
''',
                           overridable=True,
                           description='''\
Sets HTTP health check options, for example timeout check and httpchk GET.
Parameters of the first health check for this service are exposed as:
  * healthCheckPortIndex
  * healthCheckPort
  * healthCheckProtocol
  * healthCheckPath
  * healthCheckTimeoutSeconds
  * healthCheckIntervalSeconds
  * healthCheckIgnoreHttp1xx
  * healthCheckGracePeriodSeconds
  * healthCheckMaxConsecutiveFailures
  * healthCheckFalls is set to healthCheckMaxConsecutiveFailures + 1
  * healthCheckPortOptions is set to ` port {healthCheckPort}`

Defaults to empty string.

Example:
```
  option  httpchk GET {healthCheckPath}
  timeout check {healthCheckTimeoutSeconds}s
```
  '''))

        self.add_template(
            ConfigTemplate(name='BACKEND_TCP_HEALTHCHECK_OPTIONS',
                           value='',
                           overridable=True,
                           description='''\
Sets TCP health check options, for example timeout check.
Parameters of the first health check for this service are exposed as:
  * healthCheckPortIndex
  * healthCheckPort
  * healthCheckProtocol
  * healthCheckTimeoutSeconds
  * healthCheckIntervalSeconds
  * healthCheckGracePeriodSeconds
  * healthCheckMaxConsecutiveFailures
  * healthCheckFalls is set to healthCheckMaxConsecutiveFailures + 1
  * healthCheckPortOptions is set to ` port {healthCheckPort}`

Defaults to empty string.

Example:
```
  timeout check {healthCheckTimeoutSeconds}s
```
  '''))

        self.add_template(
            ConfigTemplate(name='BACKEND_STICKY_OPTIONS',
                           value='''\
  cookie mesosphere_server_id insert indirect nocache
''',
                           overridable=True,
                           description='''\
Sets a cookie for services where `HAPROXY_{n}_STICKY` is true.
    '''))

        self.add_template(
            ConfigTemplate(name='BACKEND_SERVER_OPTIONS',
                           value='''\
  server {serverName} {host_ipv4}:{port}{cookieOptions}\
{healthCheckOptions}{otherOptions}
''',
                           overridable=True,
                           description='''\
The options for each server added to a backend.
    '''))

        self.add_template(
            ConfigTemplate(name='BACKEND_SERVER_HTTP_HEALTHCHECK_OPTIONS',
                           value='''\
  check inter {healthCheckIntervalSeconds}s fall {healthCheckFalls}\
{healthCheckPortOptions}
''',
                           overridable=True,
                           description='''\
Sets HTTP health check options for a single server, e.g. check inter.
Parameters of the first health check for this service are exposed as:
  * healthCheckPortIndex
  * healthCheckPort
  * healthCheckProtocol
  * healthCheckPath
  * healthCheckTimeoutSeconds
  * healthCheckIntervalSeconds
  * healthCheckIgnoreHttp1xx
  * healthCheckGracePeriodSeconds
  * healthCheckMaxConsecutiveFailures
  * healthCheckFalls is set to healthCheckMaxConsecutiveFailures + 1
  * healthCheckPortOptions is set to ` port {healthCheckPort}`

Defaults to empty string.

Example:
```
  check inter {healthCheckIntervalSeconds}s fall {healthCheckFalls}
```
  '''))

        self.add_template(
            ConfigTemplate(name='BACKEND_SERVER_TCP_HEALTHCHECK_OPTIONS',
                           value='''\
  check inter {healthCheckIntervalSeconds}s fall {healthCheckFalls}\
{healthCheckPortOptions}
''',
                           overridable=True,
                           description='''\
Sets TCP health check options for a single server, e.g. check inter.
Parameters of the first health check for this service are exposed as:
  * healthCheckPortIndex
  * healthCheckPort
  * healthCheckProtocol
  * healthCheckTimeoutSeconds
  * healthCheckIntervalSeconds
  * healthCheckGracePeriodSeconds
  * healthCheckMaxConsecutiveFailures
  * healthCheckFalls is set to healthCheckMaxConsecutiveFailures + 1
  * healthCheckPortOptions is set to ` port {healthCheckPort}`

Defaults to empty string.

Example:
```
  check inter {healthCheckIntervalSeconds}s fall {healthCheckFalls}
```
  '''))

        self.add_template(
            ConfigTemplate(name='FRONTEND_BACKEND_GLUE',
                           value='''\
  use_backend {backend}
''',
                           overridable=True,
                           description='''\
This option glues the backend to the frontend.
    '''))

    def __init__(self, directory='templates'):
        self.__template_directory = directory
        self.t = dict()
        self.load()
        self.__load_templates()

    def __load_templates(self):
        '''Loads template files if they exist, othwerwise it sets defaults'''

        for template in self.t:
            name = self.t[template].full_name
            try:
                filename = os.path.join(self.__template_directory, name)
                with open(filename) as f:
                    logger.info('overriding %s from %s', name, filename)
                    self.t[template].value = f.read()
            except IOError:
                logger.debug("setting default value for %s", name)

    def get_descriptions(self):
        descriptions = '''\
## Templates

The following is a list of the available HAProxy templates.
Some templates are global-only (such as `HAPROXY_HEAD`), but most may
be overridden on a per service port basis using the
`HAPROXY_{n}_...` syntax.

'''
        desc_template = '''\
## `{name}`
  *{overridable}*

May be specified as {specifiedAs}.

{description}

#### Default template for `{name}`:
```
{default}
```
'''
        for tname in sorted(self.t.keys()):
            t = self.t[tname]
            spec = "`HAPROXY_" + t.name + "` template"
            if t.overridable:
                spec += " or with label `HAPROXY_{n}_" + t.name + "`"
            descriptions += desc_template.format(
                name=t.name,
                specifiedAs=spec,
                overridable="Overridable" if t.overridable else "Global",
                description=t.description,
                default=t.default_value
            )

        descriptions += '''\
## Other Labels
These labels may be used to configure other app settings.

'''
        desc_template = '''\
## `{name}`
  *{perServicePort}*

May be specified as {specifiedAs}.

{description}

'''
        for label in labels:
            if label.name not in self.t:
                if label.name == 'GROUP':
                    # this one is a special snowflake
                    spec = "`HAPROXY_{n}_" + label.name + "`" + " or " + \
                        "`HAPROXY_" + label.name + "`"
                elif label.perServicePort:
                    spec = "`HAPROXY_{n}_" + label.name + "`"
                else:
                    spec = "`HAPROXY_" + label.name + "`"
                descriptions += desc_template.format(
                    name=label.name,
                    specifiedAs=spec,
                    perServicePort="per service port" if label.perServicePort
                    else "per app",
                    description=label.description
                )
        return descriptions

    @property
    def haproxy_head(self):
        return self.t['HEAD'].value

    @property
    def haproxy_http_frontend_head(self):
        return self.t['HTTP_FRONTEND_HEAD'].value

    @property
    def haproxy_http_frontend_appid_head(self):
        return self.t['HTTP_FRONTEND_APPID_HEAD'].value

    @property
    def haproxy_https_frontend_head(self):
        return self.t['HTTPS_FRONTEND_HEAD'].value

    def haproxy_frontend_head(self, app):
        if 'FRONTEND_HEAD' in app.labels:
            return app.labels['HAPROXY_{0}_FRONTEND_HEAD']
        return self.t['FRONTEND_HEAD'].value

    def haproxy_backend_redirect_http_to_https(self, app):
        if 'HAPROXY_{0}_BACKEND_REDIRECT_HTTP_TO_HTTPS' in app.labels:
            return app.labels['HAPROXY_{0}_BACKEND_REDIRECT_HTTP_TO_HTTPS']
        return self.t['BACKEND_REDIRECT_HTTP_TO_HTTPS'].value

    def haproxy_backend_redirect_http_to_https_with_path(self, app):
        if 'HAPROXY_{0}_BACKEND_REDIRECT_HTTP_TO_HTTPS_WITH_PATH' in\
          app.labels:
            return app.\
                labels['HAPROXY_{0}_BACKEND_REDIRECT_HTTP_TO_HTTPS_WITH_PATH']
        return self.t['BACKEND_REDIRECT_HTTP_TO_HTTPS_WITH_PATH'].value

    def haproxy_backend_hsts_options(self, app):
        if 'HAPROXY_{0}_BACKEND_HSTS_OPTIONS' in app.labels:
            return app.labels['HAPROXY_{0}_BACKEND_HSTS_OPTIONS']
        return self.t['BACKEND_HSTS_OPTIONS'].value

    def haproxy_backend_head(self, app):
        if 'HAPROXY_{0}_BACKEND_HEAD' in app.labels:
            return app.labels['HAPROXY_{0}_BACKEND_HEAD']
        return self.t['BACKEND_HEAD'].value

    def haproxy_http_frontend_acl(self, app):
        if 'HAPROXY_{0}_HTTP_FRONTEND_ACL' in app.labels:
            return app.labels['HAPROXY_{0}_HTTP_FRONTEND_ACL']
        return self.t['HTTP_FRONTEND_ACL'].value

    def haproxy_http_frontend_acl_only(self, app):
        if 'HAPROXY_{0}_HTTP_FRONTEND_ACL_ONLY' in app.labels:
            return app.labels['HAPROXY_{0}_HTTP_FRONTEND_ACL_ONLY']
        return self.t['HTTP_FRONTEND_ACL_ONLY'].value

    def haproxy_http_frontend_routing_only(self, app):
        if 'HAPROXY_{0}_HTTP_FRONTEND_ROUTING_ONLY' in app.labels:
            return app.labels['HAPROXY_{0}_HTTP_FRONTEND_ROUTING_ONLY']
        return self.t['HTTP_FRONTEND_ROUTING_ONLY'].value

    def haproxy_http_frontend_acl_with_path(self, app):
        if 'HAPROXY_{0}_HTTP_FRONTEND_ACL_WITH_PATH' in app.labels:
            return app.labels['HAPROXY_{0}_HTTP_FRONTEND_ACL_WITH_PATH']
        return self.t['HTTP_FRONTEND_ACL_WITH_PATH'].value

    def haproxy_http_frontend_acl_only_with_path(self, app):
        if 'HAPROXY_{0}_HTTP_FRONTEND_ACL_ONLY_WITH_PATH' in app.labels:
            return app.labels['HAPROXY_{0}_HTTP_FRONTEND_ACL_ONLY_WITH_PATH']
        return self.t['HTTP_FRONTEND_ACL_ONLY_WITH_PATH'].value

    def haproxy_https_frontend_acl_only_with_path(self, app):
        if 'HAPROXY_{0}_HTTPS_FRONTEND_ACL_ONLY_WITH_PATH' in app.labels:
            return app.labels['HAPROXY_{0}_HTTPS_FRONTEND_ACL_ONLY_WITH_PATH']
        return self.t['HTTPS_FRONTEND_ACL_ONLY_WITH_PATH'].value

    def haproxy_http_frontend_routing_only_with_path(self, app):
        if 'HAPROXY_{0}_HTTP_FRONTEND_ROUTING_ONLY_WITH_PATH' in app.labels:
            return \
                app.labels['HAPROXY_{0}_HTTP_FRONTEND_ROUTING_ONLY_WITH_PATH']
        return self.t['HTTP_FRONTEND_ROUTING_ONLY_WITH_PATH'].value

    def haproxy_http_frontend_appid_acl(self, app):
        if 'HAPROXY_{0}_HTTP_FRONTEND_APPID_ACL' in app.labels:
            return app.labels['HAPROXY_{0}_HTTP_FRONTEND_APPID_ACL']
        return self.t['HTTP_FRONTEND_APPID_ACL'].value

    def haproxy_https_frontend_acl(self, app):
        if 'HAPROXY_{0}_HTTPS_FRONTEND_ACL' in app.labels:
            return app.labels['HAPROXY_{0}_HTTPS_FRONTEND_ACL']
        return self.t['HTTPS_FRONTEND_ACL'].value

    def haproxy_https_frontend_acl_with_path(self, app):
        if 'HAPROXY_{0}_HTTPS_FRONTEND_ACL_WITH_PATH' in app.labels:
            return app.labels['HAPROXY_{0}_HTTPS_FRONTEND_ACL_WITH_PATH']
        return self.t['HTTPS_FRONTEND_ACL_WITH_PATH'].value

    def haproxy_backend_http_options(self, app):
        if 'HAPROXY_{0}_BACKEND_HTTP_OPTIONS' in app.labels:
            return app.labels['HAPROXY_{0}_BACKEND_HTTP_OPTIONS']
        return self.t['BACKEND_HTTP_OPTIONS'].value

    def haproxy_backend_http_healthcheck_options(self, app):
        if 'HAPROXY_{0}_BACKEND_HTTP_HEALTHCHECK_OPTIONS' in app.labels:
            return app.labels['HAPROXY_{0}_BACKEND_HTTP_HEALTHCHECK_OPTIONS']
        return self.t['BACKEND_HTTP_HEALTHCHECK_OPTIONS'].value

    def haproxy_backend_tcp_healthcheck_options(self, app):
        if 'HAPROXY_{0}_BACKEND_TCP_HEALTHCHECK_OPTIONS' in app.labels:
            return app.labels['HAPROXY_{0}_BACKEND_TCP_HEALTHCHECK_OPTIONS']
        return self.t['BACKEND_TCP_HEALTHCHECK_OPTIONS'].value

    def haproxy_backend_sticky_options(self, app):
        if 'HAPROXY_{0}_BACKEND_STICKY_OPTIONS' in app.labels:
            return app.labels['HAPROXY_{0}_BACKEND_STICKY_OPTIONS']
        return self.t['BACKEND_STICKY_OPTIONS'].value

    def haproxy_backend_server_options(self, app):
        if 'HAPROXY_{0}_BACKEND_SERVER_OPTIONS' in app.labels:
            return app.labels['HAPROXY_{0}_BACKEND_SERVER_OPTIONS']
        return self.t['BACKEND_SERVER_OPTIONS'].value

    def haproxy_backend_server_http_healthcheck_options(self, app):
        if 'HAPROXY_{0}_BACKEND_SERVER_HTTP_HEALTHCHECK_OPTIONS' in \
                app.labels:
            return self.__blank_prefix_or_empty(
                app.labels['HAPROXY_{0}_BACKEND' +
                           '_SERVER_HTTP_HEALTHCHECK_OPTIONS']
                .strip())
        return self.__blank_prefix_or_empty(
            self.t['BACKEND_SERVER_HTTP_HEALTHCHECK_OPTIONS'].value.strip())

    def haproxy_backend_server_tcp_healthcheck_options(self, app):
        if 'HAPROXY_{0}_BACKEND_SERVER_TCP_HEALTHCHECK_OPTIONS' in app.labels:
            return self.__blank_prefix_or_empty(
                app.labels['HAPROXY_{0}_BACKEND_'
                           'SERVER_TCP_HEALTHCHECK_OPTIONS']
                .strip())
        return self.__blank_prefix_or_empty(
            self.t['BACKEND_SERVER_TCP_HEALTHCHECK_OPTIONS'].value.strip())

    def haproxy_frontend_backend_glue(self, app):
        if 'HAPROXY_{0}_FRONTEND_BACKEND_GLUE' in app.labels:
            return app.labels['HAPROXY_{0}_FRONTEND_BACKEND_GLUE']
        return self.t['FRONTEND_BACKEND_GLUE'].value

    def __blank_prefix_or_empty(self, s):
        if s:
            return ' ' + s
        else:
            return s


def string_to_bool(s):
    return s.lower() in ["true", "t", "yes", "y"]


def set_hostname(x, k, v):
    x.hostname = v


def set_path(x, k, v):
    x.path = v


def set_sticky(x, k, v):
    x.sticky = string_to_bool(v)


def set_redirect_http_to_https(x, k, v):
    x.redirectHttpToHttps = string_to_bool(v)


def set_use_hsts(x, k, v):
    x.useHsts = string_to_bool(v)


def set_sslCert(x, k, v):
    x.sslCert = v


def set_bindOptions(x, k, v):
    x.bindOptions = v


def set_bindAddr(x, k, v):
    x.bindAddr = v


def set_port(x, k, v):
    x.servicePort = int(v)


def set_mode(x, k, v):
    x.mode = v


def set_balance(x, k, v):
    x.balance = v


def set_label(x, k, v):
    x.labels[k] = v


def set_group(x, k, v):
    x.haproxy_groups = v.split(',')


class Label:
    def __init__(self, name, func, description, perServicePort=True):
        self.name = name
        self.perServicePort = perServicePort
        if perServicePort:
            self.full_name = 'HAPROXY_{0}_' + name
        else:
            self.full_name = 'HAPROXY_' + name
        self.func = func
        self.description = description

labels = []
labels.append(Label(name='VHOST',
                    func=set_hostname,
                    description='''\
The Marathon HTTP Virtual Host proxy hostname(s) to gather.

Ex: `HAPROXY_0_VHOST = 'marathon.mesosphere.com'`

Ex: `HAPROXY_0_VHOST = 'marathon.mesosphere.com,marathon'`
                    '''))
labels.append(Label(name='GROUP',
                    func=set_group,
                    description='''\
HAProxy group per service. This helps us have different HAProxy groups
per service port. This overrides `HAPROXY_GROUP` for the particular service.
If you have both external and internal services running on same set of
instances on different ports, you can use this feature to add them to
different haproxy configs.

Ex: `HAPROXY_0_GROUP = 'external'`

Ex: `HAPROXY_1_GROUP = 'internal'`

Now if you run marathon_lb with --group external, it just adds the
service on `HAPROXY_0_PORT` (or first service port incase `HAPROXY_0_HOST`
is not configured) to haproxy config and similarly if you run it with
--group internal, it adds service on `HAPROXY_1_PORT` to haproxy config.
If the configuration is a combination of `HAPROXY_GROUP` and
`HAPROXY_{n}_GROUP`, the more specific definition takes precedence.

Ex: `HAPROXY_0_GROUP = 'external'`

Ex: `HAPROXY_GROUP   = 'internal'`

Considering the above example where the configuration is hybrid,
a service running on `HAPROXY_0_PORT` is associated with just 'external'
HAProxy group and not 'internal' group. And since there is no HAProxy
group mentioned for second service (`HAPROXY_1_GROUP` not defined)
it falls back to default `HAPROXY_GROUP` and gets associated with
'internal' group.

Load balancers with the group '*' will collect all groups.
    '''))
labels.append(Label(name='DEPLOYMENT_GROUP',
                    func=None,
                    description='''\
Deployment group to which this app belongs.
                    ''',
                    perServicePort=False))
labels.append(Label(name='DEPLOYMENT_ALT_PORT',
                    func=None,
                    description='''\
Alternate service port to be used during a blue/green deployment.
                    ''',
                    perServicePort=False))
labels.append(Label(name='DEPLOYMENT_COLOUR',
                    func=None,
                    description='''\
Blue/green deployment colour. Used by the bluegreen_deploy.py script
to determine the state of a deploy. You generally do not need to modify
this unless you implement your own deployment orchestrator.
                    ''',
                    perServicePort=False))
labels.append(Label(name='DEPLOYMENT_STARTED_AT',
                    func=None,
                    description='''\
The time at which a deployment started. You generally do not need
to modify this unless you implement your own deployment orchestrator.
                    ''',
                    perServicePort=False))
labels.append(Label(name='DEPLOYMENT_TARGET_INSTANCES',
                    func=None,
                    description='''\
The target number of app instances to seek during deployment. You
generally do not need to modify this unless you implement your
own deployment orchestrator.
                    ''',
                    perServicePort=False))
labels.append(Label(name='PATH',
                    func=set_path,
                    description='''\
                    '''))
labels.append(Label(name='STICKY',
                    func=set_sticky,
                    description='''\
Enable sticky request routing for the service.

Ex: `HAPROXY_0_STICKY = true`
                    '''))
labels.append(Label(name='REDIRECT_TO_HTTPS',
                    func=set_redirect_http_to_https,
                    description='''\
Redirect HTTP traffic to HTTPS. Requires at least a VHost be set.

Ex: `HAPROXY_0_REDIRECT_TO_HTTPS = true`
                    '''))
labels.append(Label(name='USE_HSTS',
                    func=set_use_hsts,
                    description='''\
Enable the HSTS response header for HTTP clients which support it.

Ex: `HAPROXY_0_USE_HSTS = true`
                    '''))
labels.append(Label(name='SSL_CERT',
                    func=set_sslCert,
                    description='''\
Enable the given SSL certificate for TLS/SSL traffic.

Ex: `HAPROXY_0_SSL_CERT = '/etc/ssl/certs/marathon.mesosphere.com'`
                    '''))
labels.append(Label(name='BIND_OPTIONS',
                    func=set_bindOptions,
                    description='''\
Set additional bind options

Ex: `HAPROXY_0_BIND_OPTIONS = 'ciphers AES128+EECDH:AES128+EDH force-tlsv12\
 no-sslv3'`
                    '''))
labels.append(Label(name='BIND_ADDR',
                    func=set_bindAddr,
                    description='''\
Bind to the specific address for the service.

Ex: `HAPROXY_0_BIND_ADDR = '10.0.0.42'`
                    '''))
labels.append(Label(name='PORT',
                    func=set_port,
                    description='''\
Bind to the specific port for the service.
This overrides the servicePort which has to be unique.

Ex: `HAPROXY_0_PORT = 80`
                    '''))
labels.append(Label(name='MODE',
                    func=set_mode,
                    description='''\
Set the connection mode to either TCP or HTTP. The default is TCP.

Ex: `HAPROXY_0_MODE = 'http'`
                    '''))
labels.append(Label(name='BALANCE',
                    func=set_balance,
                    description='''\
Set the load balancing algorithm to be used in a backend. The default is
roundrobin.

Ex: `HAPROXY_0_BALANCE = 'leastconn'`
                    '''))
labels.append(Label(name='FRONTEND_HEAD',
                    func=set_label,
                    description=''))
labels.append(Label(name='BACKEND_REDIRECT_HTTP_TO_HTTPS',
                    func=set_label,
                    description=''))
labels.append(Label(name='BACKEND_HEAD',
                    func=set_label,
                    description=''))
labels.append(Label(name='HTTP_FRONTEND_ACL',
                    func=set_label,
                    description=''))
labels.append(Label(name='HTTP_FRONTEND_ACL_ONLY',
                    func=set_label,
                    description=''))
labels.append(Label(name='HTTP_FRONTEND_ROUTING_ONLY',
                    func=set_label,
                    description=''))
labels.append(Label(name='HTTP_FRONTEND_ACL_WITH_PATH',
                    func=set_label,
                    description=''))
labels.append(Label(name='HTTP_FRONTEND_ACL_ONLY_WITH_PATH',
                    func=set_label,
                    description=''))
labels.append(Label(name='HTTPS_FRONTEND_ACL_ONLY_WITH_PATH',
                    func=set_label,
                    description=''))
labels.append(Label(name='HTTP_FRONTEND_ROUTING_ONLY_WITH_PATH',
                    func=set_label,
                    description=''))
labels.append(Label(name='HTTP_FRONTEND_APPID_ACL',
                    func=set_label,
                    description=''))
labels.append(Label(name='HTTPS_FRONTEND_ACL',
                    func=set_label,
                    description=''))
labels.append(Label(name='HTTPS_FRONTEND_ACL_WITH_PATH',
                    func=set_label,
                    description=''))
labels.append(Label(name='BACKEND_HTTP_OPTIONS',
                    func=set_label,
                    description=''))
labels.append(Label(name='BACKEND_HSTS_OPTIONS',
                    func=set_label,
                    description=''))
labels.append(Label(name='BACKEND_HTTP_HEALTHCHECK_OPTIONS',
                    func=set_label,
                    description=''))
labels.append(Label(name='BACKEND_TCP_HEALTHCHECK_OPTIONS',
                    func=set_label,
                    description=''))
labels.append(Label(name='BACKEND_STICKY_OPTIONS',
                    func=set_label,
                    description=''))
labels.append(Label(name='BACKEND_SERVER_OPTIONS',
                    func=set_label,
                    description=''))
labels.append(Label(name='BACKEND_SERVER_TCP_HEALTHCHECK_OPTIONS',
                    func=set_label,
                    description=''))
labels.append(Label(name='BACKEND_SERVER_HTTP_HEALTHCHECK_OPTIONS',
                    func=set_label,
                    description=''))
labels.append(Label(name='FRONTEND_BACKEND_GLUE',
                    func=set_label,
                    description=''))

label_keys = {}
for label in labels:
    if not label.func:
        continue
    label_keys[label.full_name] = label.func

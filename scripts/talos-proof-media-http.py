#!/usr/bin/env python3
"""Verified proof Gateway HTTPS over the coordinator's SSH loopback tunnel.

URL authority/SNI/certificate hostname stay <service>.proof.invalid:18443; only
TCP dialing is redirected to 127.0.0.1. No DNS or proxy environment is consulted.
"""
import http.client
import http.cookiejar
import json
import socket
import ssl
import urllib.parse
import urllib.request


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(req.full_url)[:2] != urllib.parse.urlsplit(newurl)[:2]:
            raise ValueError('cross-origin/downgrade proof redirects forbidden')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class LoopbackTLS(http.client.HTTPSConnection):
    def __init__(self, host, **kwargs):
        super().__init__(host, **kwargs)
        if not self.host.endswith('.proof.invalid') or self.port != 18443:
            raise ValueError('only the dedicated proof Gateway TLS listener is allowed')
        self._create_connection = self.loopback_connection

    @staticmethod
    def loopback_connection(address, timeout=socket._GLOBAL_DEFAULT_TIMEOUT, source_address=None):
        return socket.create_connection(('127.0.0.1', 18443), timeout, source_address)


class GatewayTLSHandler(urllib.request.HTTPSHandler):
    def https_open(self, request):
        return self.do_open(LoopbackTLS, request, context=self._context)


class API:
    def __init__(self, base, headers=None, *, service=None, ca=None, allow_http=False):
        parsed = urllib.parse.urlsplit(base)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            raise ValueError('proof base must be an origin without credentials, path or query')
        handlers = [urllib.request.ProxyHandler({}), SameOriginRedirect(),
                    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())]
        if parsed.scheme == 'https':
            if not service or parsed.hostname != service + '.proof.invalid' or parsed.port != 18443 or ca is None:
                raise ValueError('HTTPS requires exact service proof hostname, port 18443 and explicit proof CA')
            context = ssl.create_default_context(cafile=str(ca))
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
                raise ValueError('TLS verification cannot be disabled')
            handlers.append(GatewayTLSHandler(context=context))
        elif not (allow_http and parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')):
            raise ValueError('verified proof Gateway HTTPS is required (HTTP diagnostic mode is opt-in)')
        self.base, self.headers = base.rstrip('/'), headers or {}
        self.service, self.ca, self.allow_http = service, ca, allow_http
        self.opener = urllib.request.build_opener(*handlers)
        self.last_status, self.last_headers = None, {}

    def anonymous(self):
        return API(self.base, service=self.service, ca=self.ca, allow_http=self.allow_http)

    def call(self, path, method='GET', data=None, form=None, raw=False, headers=None, payload=None):
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('API path must remain same-origin')
        hdr = {**self.headers, **(headers or {})}
        if data is not None:
            payload = json.dumps(data).encode()
            hdr['Content-Type'] = 'application/json'
        elif form is not None:
            payload = urllib.parse.urlencode(form).encode()
            hdr['Content-Type'] = 'application/x-www-form-urlencoded'
        req = urllib.request.Request(self.base + path, data=payload, method=method, headers=hdr)
        with self.opener.open(req, timeout=45) as response:
            self.last_status = response.status
            self.last_headers = dict(response.headers)
            body = response.read()
        if raw:
            return body
        return json.loads(body) if body else None

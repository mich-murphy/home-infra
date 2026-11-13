#!/usr/bin/env python3
"""Offline Torznab/Newznab provider; never a Prowlarr/Radarr API emulator."""
import argparse
import hashlib
import hmac
import http.client
import http.server
import importlib.util
import ipaddress
import json
from pathlib import Path
import socketserver
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET

ENGINE = Path(__file__).resolve().parents[1] / 'download-protocols/server.py'
spec = importlib.util.spec_from_file_location('download_protocol_fixture', ENGINE)
protocols = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocols)

TITLE = 'Proof Fixture'
RELEASE = 'Proof.Fixture.2000.1080p.WEB-DL.H264-Fixture'
TMDB = '900000001'
IMDB = '900000001'
NS = {'torznab': 'http://torznab.com/schemas/2015/feed',
      'newznab': 'http://www.newznab.com/DTD/2010/feeds/attributes/'}
MAX_REQUEST = 2048
MAX_HEADERS = 8192
MAX_RESPONSE = 16384
TIMEOUT = 3
CONCURRENCY = 4
MAX_COUNTER = (1 << 63) - 1
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def canonical_base(value):
    """No DNS, credentials, fragments, paths or non-loopback destinations."""
    try:
        url = urllib.parse.urlsplit(value)
        ip = ipaddress.IPv4Address(url.hostname)
        if (url.scheme != 'http' or not ip.is_loopback or url.username or url.password
                or url.path or url.query or url.fragment or not url.port
                or value != f'http://{ip}:{url.port}'):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('a canonical explicit-port IPv4 loopback HTTP base is required') from None
    return value


def xml(element):
    return ET.tostring(element, encoding='utf-8', xml_declaration=True)


class Contract:
    def __init__(self, fixture, artifact_base, api_key):
        if not isinstance(fixture, protocols.Fixture):
            raise ValueError('shared download-protocol Fixture required')
        self.artifact_base = canonical_base(artifact_base)
        if not 8 <= len(api_key) <= 128 or not api_key.isascii() or not api_key.isalnum():
            raise ValueError('fixture key must be 8..128 ASCII alphanumeric characters')
        # Artifact URLs must describe this exact engine instance, not an arbitrary URL.
        if fixture.torrent != protocols.bencode({'announce': self.artifact_base + '/announce', 'info': fixture.info}):
            raise ValueError('fixture announce and artifact base disagree')
        self.fixture, self._key = fixture, api_key
        self.lock = threading.Lock()
        self.counters = dict(requests=0, caps=0, searches=0, results=0, rejected=0, busy=0)

    def count(self, key):
        with self.lock:
            self.counters[key] = min(MAX_COUNTER, self.counters[key] + 1)

    def caps(self):
        root = ET.Element('caps')
        ET.SubElement(root, 'server', version='1.0', title='Offline synthetic provider')
        ET.SubElement(root, 'limits', max='1', default='1')
        searching = ET.SubElement(root, 'searching')
        ET.SubElement(searching, 'search', available='yes', supportedParams='q')
        ET.SubElement(searching, 'movie-search', available='yes', supportedParams='q,imdbid,tmdbid')
        for kind in ('tv-search', 'audio-search', 'book-search'):
            ET.SubElement(searching, kind, available='no', supportedParams='')
        categories = ET.SubElement(root, 'categories')
        movie = ET.SubElement(categories, 'category', id='2000', name='Movies')
        ET.SubElement(movie, 'subcat', id='2040', name='Movies/HD')
        return xml(root)

    def search(self, protocol, params):
        namespace = NS[protocol]
        root = ET.Element('rss', version='2.0')
        channel = ET.SubElement(root, 'channel')
        ET.SubElement(channel, 'title').text = 'Offline synthetic provider'
        ET.SubElement(channel, 'description').text = 'One controlled release; no upstream'
        ET.SubElement(channel, 'link').text = self.artifact_base
        query = params.get('q', '').strip().casefold()
        match = query in ('', 'proof fixture', RELEASE.casefold(), 'proof.fixture')
        match &= params.get('tmdbid', TMDB) == TMDB
        match &= params.get('imdbid', IMDB).removeprefix('tt') == IMDB
        match &= not params.get('cat') or bool({'2000', '2040'} & set(params['cat'].split(',')))
        match &= params.get('offset', '0') == '0' and params.get('limit', '1') != '0'
        ET.SubElement(channel, f'{{{namespace}}}response', offset=params.get('offset', '0'), total=str(int(match)))
        if match:
            self.count('results')
            item = ET.SubElement(channel, 'item')
            extension = 'torrent' if protocol == 'torznab' else 'nzb'
            artifact = self.artifact_base + '/artifact.' + extension
            guid = hashlib.sha256((protocol + ':' + self.fixture.sha256 + ':' + self.fixture.name).encode()).hexdigest()
            ET.SubElement(item, 'title').text = RELEASE
            ET.SubElement(item, 'guid', isPermaLink='false').text = 'urn:fixture:' + guid
            ET.SubElement(item, 'link').text = artifact
            ET.SubElement(item, 'pubDate').text = 'Sat, 01 Jan 2000 00:00:00 +0000'
            ET.SubElement(item, 'category').text = '2000'
            ET.SubElement(item, 'size').text = str(len(self.fixture.payload))
            ET.SubElement(item, 'enclosure', url=artifact, length=str(len(self.fixture.payload)),
                          type='application/x-bittorrent' if protocol == 'torznab' else 'application/x-nzb')
            attrs = dict(category='2040', size=str(len(self.fixture.payload)), tmdbid=TMDB, imdb=IMDB,
                         downloadvolumefactor='0', uploadvolumefactor='1')
            if protocol == 'torznab':
                attrs.update(seeders='1', peers='1', infohash=self.fixture.infohash.hex())
            else:
                attrs.update(grabs='0')
            for name, value in attrs.items():
                ET.SubElement(item, f'{{{namespace}}}attr', name=name, value=value)
        return xml(root)


class HeaderBudget:
    def __init__(self, stream, connection):
        self.stream, self.connection = stream, connection
        self.remaining, self.deadline = MAX_HEADERS, time.monotonic() + TIMEOUT

    def readline(self, size=-1):
        remaining_time = self.deadline - time.monotonic()
        if remaining_time <= 0 or self.remaining <= 0:
            raise http.client.LineTooLong('bounded headers')
        self.connection.settimeout(remaining_time)
        line = self.stream.readline(min(self.remaining + 1, 2049))
        self.remaining -= len(line)
        if self.remaining < 0 or len(line) > 2048:
            raise http.client.LineTooLong('bounded headers')
        return line


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = CONCURRENCY

    def __init__(self, address, contract):
        if not ipaddress.IPv4Address(address[0]).is_loopback:
            raise ValueError('offline provider binds loopback only')
        self.contract = contract
        self.slots = threading.BoundedSemaphore(CONCURRENCY)
        super().__init__(address, Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(False):
            self.contract.count('busy')
            request.close()
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

    def handle_error(self, request, address):
        self.contract.count('rejected')  # No tracebacks or raw request logging.


class Handler(http.server.BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(TIMEOUT)

    def log_message(self, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        self.reply(code, xml(ET.Element('error', code='200', description='request rejected')))

    def reply(self, status, body, content_type='application/xml'):
        if status != 200:
            self.server.contract.count('rejected')
        if len(body) > MAX_RESPONSE:
            raise ValueError('response limit')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)

    def handle_one_request(self):
        self.close_connection = True
        self.server.contract.count('requests')
        self.raw_requestline = self.rfile.readline(MAX_REQUEST + 1)
        if not self.raw_requestline:
            return
        if len(self.raw_requestline) > MAX_REQUEST:
            self.requestline, self.request_version = '', 'HTTP/1.0'
            self.send_error(414)
            return
        stream = self.rfile
        self.rfile = HeaderBudget(stream, self.connection)
        try:
            if not self.parse_request():
                return
        finally:
            self.rfile = stream
        self.close_connection = True
        self.connection.settimeout(TIMEOUT)
        if self.command != 'GET' or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Length', '0') != '0':
            self.send_error(405)
            return
        self.do_GET()

    def do_GET(self):
        contract = self.server.contract
        try:
            url = urllib.parse.urlsplit(self.path)
            if url.scheme or url.netloc or url.fragment:
                raise ValueError()
            pairs = urllib.parse.parse_qsl(url.query, keep_blank_values=True, max_num_fields=32, errors='strict')
            params = dict(pairs)
            if len(params) != len(pairs) or any(len(k) > 64 or len(v) > 256 for k, v in pairs):
                raise ValueError()
            if not hmac.compare_digest(params.get('apikey', '').encode(), contract._key.encode()):
                self.reply(403, xml(ET.Element('error', code='100', description='authentication failed')))
                return
            # Extensions may be ignored, but cannot select a destination or file.
            if {'url', 'host', 'path', 'redirect', 'redirect_uri', 'downloadurl', 'destination'} & {k.casefold() for k in params}:
                raise ValueError()
            if url.path == '/stats':
                with contract.lock:
                    body = json.dumps(contract.counters, sort_keys=True).encode()
                self.reply(200, body, 'application/json')
                return
            routes = {'/torznab/api': 'torznab', '/newznab/api': 'newznab'}
            if url.path not in routes:
                self.send_error(404)
                return
            action = params.get('t')
            if action == 'caps':
                contract.count('caps')
                self.reply(200, contract.caps())
            elif action in ('search', 'movie'):
                for field in ('limit', 'offset'):
                    if field in params and (not params[field].isascii() or not params[field].isdigit() or len(params[field]) > 6):
                        raise ValueError()
                contract.count('searches')
                self.reply(200, contract.search(routes[url.path], params))
            else:
                self.send_error(400)
        except (ValueError, UnicodeError):
            self.send_error(400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-key', required=True, help='synthetic key only; never a real application key')
    parser.add_argument('--artifact-base', default='http://127.0.0.1:8080')
    parser.add_argument('--port', type=int, default=8090)
    parser.add_argument('--peer-port', type=int, default=6881)
    parser.add_argument('--nntp-port', type=int, default=8119)
    parser.add_argument('--payload', help='caller-owned read-only regular input <=2MiB')
    parser.add_argument('--name', default='Proof.Fixture.2000.1080p.WEB-DL.H264-Fixture.bin')
    args = parser.parse_args()
    base = canonical_base(args.artifact_base)
    host, port = urllib.parse.urlsplit(base).hostname, urllib.parse.urlsplit(base).port
    fixture = protocols.Fixture(protocols.payload_from_file(args.payload) if args.payload else protocols.DEFAULT_PAYLOAD,
                                args.name, base + '/announce')
    contract = Contract(fixture, base, args.api_key)
    running, started = [], []
    try:
        peer = protocols.TCPServer((host, args.peer_port), protocols.PeerHandler, fixture)
        running.append(peer)
        running.append(protocols.TCPServer((host, args.nntp_port), protocols.NNTPHandler, fixture))
        running.append(protocols.HTTPServer((host, port), fixture, (host, peer.server_address[1])))
        running.append(Server((host, args.port), contract))
        for server in running:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            started.append(server)
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        for server in started:
            server.shutdown()
        for server in running:
            server.server_close()


if __name__ == '__main__':
    main()

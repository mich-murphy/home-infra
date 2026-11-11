#!/usr/bin/env python3
"""Closed synthetic BitTorrent/NNTP fixture. No upstreams, arbitrary files or shell."""
import argparse
import hashlib
import http.server
import ipaddress
import json
import os
from pathlib import Path
import socket
import socketserver
import stat
import struct
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
import zlib

MAX_PAYLOAD = 2 * 1024 * 1024
PIECE = 16384
PUBLIC_USER = 'fixture'
PUBLIC_PASSWORD = 'fixture-public'
DEFAULT_PAYLOAD = (b'SYNTHETIC-OFFLINE-DOWNLOAD-PROTOCOL-FIXTURE\n' + bytes(range(256))) * 137


def payload_from_file(path):
    # Every path component must be a real directory/file, never a symlink.
    if '..' in Path(path).parts:
        raise ValueError('payload path traversal is not permitted')
    absolute = Path(os.path.abspath(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in absolute.parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        source = os.open(absolute.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(source)
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_PAYLOAD:
                raise ValueError('payload must be a nonempty regular file <=2MiB')
            with os.fdopen(source, 'rb', closefd=False) as stream:
                data = stream.read(MAX_PAYLOAD + 1)
            if len(data) != info.st_size:
                raise ValueError('payload changed while reading')
            return data
        finally:
            os.close(source)
    finally:
        os.close(fd)


def bencode(value):
    if isinstance(value, int):
        return b'i' + str(value).encode() + b'e'
    if isinstance(value, str):
        value = value.encode()
    if isinstance(value, bytes):
        return str(len(value)).encode() + b':' + value
    if isinstance(value, list):
        return b'l' + b''.join(bencode(v) for v in value) + b'e'
    return b'd' + b''.join(bencode(k) + bencode(value[k]) for k in sorted(value)) + b'e'


def yenc(data, name):
    lines = [f'=ybegin line=128 size={len(data)} name={name}'.encode()]
    line = bytearray()
    for raw in data:
        value = (raw + 42) & 255
        encoded = bytes((61, (value + 64) & 255)) if value in (0, 9, 10, 13, 61) else bytes((value,))
        if len(line) + len(encoded) > 128:
            lines.append(bytes(line))
            line.clear()
        line.extend(encoded)
    if line:
        lines.append(bytes(line))
    lines.append(f'=yend size={len(data)} crc32={zlib.crc32(data):08x}'.encode())
    return b'\r\n'.join(lines) + b'\r\n'


class Fixture:
    def __init__(self, payload=DEFAULT_PAYLOAD, name='synthetic-proof.bin', announce='http://127.0.0.1:8080/announce'):
        if not 0 < len(payload) <= MAX_PAYLOAD:
            raise ValueError('invalid payload size')
        if not name or len(name) > 120 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-' for c in name) or name in ('.', '..'):
            raise ValueError('name must be a safe ASCII basename')
        self.payload, self.name = payload, name
        self.sha256 = hashlib.sha256(payload).hexdigest()
        self.info = {'length': len(payload), 'name': name, 'piece length': PIECE,
                     'pieces': b''.join(hashlib.sha1(payload[i:i + PIECE]).digest() for i in range(0, len(payload), PIECE)), 'private': 1}
        self.infohash = hashlib.sha1(bencode(self.info)).digest()
        self.torrent = bencode({'announce': announce, 'info': self.info})
        self.message_id = self.sha256 + '@synthetic.invalid'
        self.body = yenc(payload, name)
        self.headers = (f'From: fixture@synthetic.invalid\r\nNewsgroups: alt.binaries.synthetic\r\nSubject: "{name}" yEnc (1/1)\r\nMessage-ID: <{self.message_id}>\r\n').encode()
        root = ET.Element('nzb', xmlns='http://www.newzbin.com/DTD/2003/nzb')
        file = ET.SubElement(root, 'file', poster='fixture@synthetic.invalid', date='0', subject=f'"{name}" yEnc (1/1)')
        ET.SubElement(ET.SubElement(file, 'groups'), 'group').text = 'alt.binaries.synthetic'
        ET.SubElement(ET.SubElement(file, 'segments'), 'segment', bytes=str(len(self.body)), number='1').text = self.message_id
        self.nzb = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        self.lock = threading.Lock()
        self.counters = dict(tracker_announces=0, peer_handshakes=0, piece_requests=0, piece_bytes=0,
                             nntp_auth=0, nntp_body_requests=0, nntp_payload_bytes=0, rejected=0)

    def count(self, key, amount=1):
        with self.lock:
            self.counters[key] += amount

    def metadata(self):
        with self.lock:
            return dict(name=self.name, size=len(self.payload), sha256=self.sha256,
                        infohash=self.infohash.hex(), message_id=self.message_id, counters=dict(self.counters))


class BoundedMixIn(socketserver.ThreadingMixIn):
    daemon_threads = True
    block_on_close = False

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
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
        # Never echo client-controlled data or a payload in tracebacks.
        self.fixture.count('rejected')


class TCPServer(BoundedMixIn, socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, address, handler, fixture):
        self.fixture = fixture
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(address, handler)


class HTTPServer(BoundedMixIn, http.server.HTTPServer):
    def __init__(self, address, fixture, peer_address):
        self.fixture, self.peer_address = fixture, peer_address
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(address, HTTPHandler)


class HTTPHandler(http.server.BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        pass

    def do_GET(self):
        f = self.server.fixture
        url = urllib.parse.urlsplit(self.path)
        if url.path == '/announce':
            try:
                query = {}
                for item in url.query.split('&'):
                    key, value = item.split('=', 1)
                    if key in query:
                        raise ValueError('duplicate parameter')
                    query[key] = urllib.parse.unquote_to_bytes(value.replace('+', ' '))
                if query.get('info_hash') != f.infohash:
                    raise ValueError('unknown infohash')
                f.count('tracker_announces')
                ip, port = self.server.peer_address
                content = bencode({'interval': 30, 'complete': 1, 'incomplete': 0,
                                   'peers': ipaddress.IPv4Address(ip).packed + struct.pack('!H', port)})
            except (ValueError, KeyError):
                f.count('rejected')
                content = bencode({'failure reason': 'unknown or invalid synthetic torrent'})
        elif url.query:
            self.send_error(404)
            return
        elif url.path == '/stats':
            content = json.dumps(f.metadata(), sort_keys=True).encode()
        elif url.path == '/artifact.torrent':
            content = f.torrent
        elif url.path == '/artifact.nzb':
            content = f.nzb
        else:
            f.count('rejected')
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/octet-stream')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(content)


def receive(sock, length):
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise EOFError()
        data.extend(chunk)
    return bytes(data)


class PeerHandler(socketserver.BaseRequestHandler):
    def handle(self):
        sock, f = self.request, self.server.fixture
        sock.settimeout(5)
        deadline = time.monotonic() + 60
        hello = receive(sock, 68)
        if hello[:20] != b'\x13BitTorrent protocol' or hello[28:48] != f.infohash:
            f.count('rejected')
            return
        f.count('peer_handshakes')
        sock.sendall(b'\x13BitTorrent protocol' + bytes(8) + f.infohash + b'-FX0001-SYNTHETIC000')
        count = (len(f.payload) + PIECE - 1) // PIECE
        bitfield = bytearray((count + 7) // 8)
        for i in range(count):
            bitfield[i // 8] |= 128 >> (i % 8)
        def send(message):
            sock.sendall(struct.pack('!I', len(message)) + message)
        send(b'\x05' + bitfield)
        send(b'\x01')  # unchoke
        interested = False
        for _ in range(4096):
            if time.monotonic() > deadline:
                return
            length = struct.unpack('!I', receive(sock, 4))[0]
            if length == 0:
                continue
            if length > 16393:
                f.count('rejected')
                return
            message = receive(sock, length)
            kind = message[0]
            if kind in (0, 1, 2, 3) and length == 1:
                if kind == 2:
                    interested = True
            elif kind == 6 and length == 13:
                index, begin, size = struct.unpack('!III', message[1:])
                offset = index * PIECE + begin
                if not interested or index >= count or not 0 < size <= PIECE or begin + size > min(PIECE, len(f.payload) - index * PIECE):
                    f.count('rejected')
                    return
                block = f.payload[offset:offset + size]
                send(b'\x07' + struct.pack('!II', index, begin) + block)
                f.count('piece_requests')
                f.count('piece_bytes', len(block))
            elif (kind == 4 and length == 5) or (kind == 5 and length == 1 + len(bitfield)) or (kind == 8 and length == 13):
                pass  # have, bitfield, cancel; no extensions or arbitrary messages
            else:
                f.count('rejected')
                return


class NNTPHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(5)
        f = self.server.fixture
        deadline = time.monotonic() + 60
        authenticated = False
        user_ok = False
        def reply(line):
            self.wfile.write(line.encode() + b'\r\n')
        def multiline(data):
            for line in data.split(b'\r\n')[:-1]:
                self.wfile.write((b'.' if line.startswith(b'.') else b'') + line + b'\r\n')
            self.wfile.write(b'.\r\n')
        reply('200 synthetic fixture ready; public credentials only')
        for _ in range(256):
            if time.monotonic() > deadline:
                return
            raw = self.rfile.readline(1025)
            if not raw:
                return
            if len(raw) > 1024 or not raw.endswith(b'\r\n'):
                f.count('rejected')
                return
            try:
                parts = raw[:-2].decode('ascii').split(' ', 1)
            except UnicodeDecodeError:
                reply('500 ASCII commands only')
                continue
            command, arg = parts[0].upper(), parts[1] if len(parts) == 2 else ''
            if command == 'QUIT' and not arg:
                reply('205 closing')
                return
            if command == 'CAPABILITIES' and not arg:
                reply('101 capability list')
                multiline(b'VERSION 2\r\nREADER\r\nAUTHINFO USER\r\n')
            elif command == 'MODE' and arg.upper() == 'READER':
                reply('200 reader mode')
            elif command == 'AUTHINFO':
                subcommand, _, credential = arg.partition(' ')
                if subcommand.upper() == 'USER' and credential == PUBLIC_USER:
                    user_ok = True
                    reply('381 password required')
                elif user_ok and subcommand.upper() == 'PASS' and credential == PUBLIC_PASSWORD:
                    authenticated = True
                    f.count('nntp_auth')
                    reply('281 authentication accepted')
                else:
                    user_ok = False
                    f.count('rejected')
                    reply('481 authentication rejected')
            elif not authenticated:
                reply('480 authentication required')
            elif command == 'GROUP' and arg == 'alt.binaries.synthetic':
                reply('211 1 1 1 alt.binaries.synthetic')
            elif command in ('BODY', 'ARTICLE', 'HEAD', 'STAT'):
                if arg != '<' + f.message_id + '>':
                    f.count('rejected')
                    reply('430 no such synthetic article')
                    continue
                code = dict(BODY=222, ARTICLE=220, HEAD=221, STAT=223)[command]
                reply(f'{code} 1 <{f.message_id}> synthetic article')
                if command != 'STAT':
                    content = f.headers if command == 'HEAD' else f.body if command == 'BODY' else f.headers + b'\r\n' + f.body
                    multiline(content)
                if command in ('BODY', 'ARTICLE'):
                    f.count('nntp_body_requests')
                    f.count('nntp_payload_bytes', len(f.payload))
            else:
                f.count('rejected')
                reply('500 unsupported synthetic request')


def servers(fixture, bind, http_port, peer_port, nntp_port, advertise_ip):
    peer = TCPServer((bind, peer_port), PeerHandler, fixture)
    nntp = TCPServer((bind, nntp_port), NNTPHandler, fixture)
    http = HTTPServer((bind, http_port), fixture, (advertise_ip, peer.server_address[1]))
    return [peer, nntp, http]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['serve', 'generate'])
    parser.add_argument('--payload', help='bounded regular synthetic payload; default deterministic binary')
    parser.add_argument('--name', default='synthetic-proof.bin')
    parser.add_argument('--announce', default='http://127.0.0.1:8080/announce')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--advertise-ip', default='127.0.0.1', help='IPv4 reachable by torrent client; never auto-discovered')
    parser.add_argument('--http-port', type=int, default=8080)
    parser.add_argument('--peer-port', type=int, default=6881)
    parser.add_argument('--nntp-port', type=int, default=8119)
    args = parser.parse_args()
    ipaddress.IPv4Address(args.advertise_ip)
    fixture = Fixture(payload_from_file(args.payload) if args.payload else DEFAULT_PAYLOAD, args.name, args.announce)
    if args.action == 'generate':
        if args.output_dir is None:
            parser.error('generate requires --output-dir')
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for name, content in [('artifact.torrent', fixture.torrent), ('artifact.nzb', fixture.nzb), ('manifest.json', (json.dumps(fixture.metadata(), sort_keys=True) + '\n').encode())]:
            path = args.output_dir / name
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
        print(json.dumps(dict(output_dir=str(args.output_dir), **fixture.metadata()), sort_keys=True), flush=True)
        return
    running = servers(fixture, args.bind, args.http_port, args.peer_port, args.nntp_port, args.advertise_ip)
    for server in running:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print(json.dumps(fixture.metadata(), sort_keys=True), flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        for server in running:
            server.shutdown()
            server.server_close()
        print(json.dumps(fixture.metadata(), sort_keys=True), flush=True)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Offline real-socket tests. Never invokes a cluster, subprocess or external peer."""
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib

MODULE = Path(__file__).resolve().parents[1] / 'kubernetes/apps/media/fixtures/download-protocols/server.py'
spec = importlib.util.spec_from_file_location('fixture', MODULE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def decode_bencode(data):
    def parse(i):
        if data[i:i+1] == b'i':
            end = data.index(b'e', i)
            return int(data[i+1:end]), end + 1
        if data[i:i+1] in (b'd', b'l'):
            dictionary = data[i:i+1] == b'd'
            out = {} if dictionary else []
            i += 1
            while data[i:i+1] != b'e':
                value, i = parse(i)
                if dictionary:
                    item, i = parse(i)
                    out[value] = item
                else:
                    out.append(value)
            return out, i + 1
        end = data.index(b':', i)
        length = int(data[i:end])
        return data[end+1:end+1+length], end+1+length
    result, end = parse(0)
    assert end == len(data)
    return result


def decode_yenc(body):
    lines = body.split(b'\r\n')
    header, footer = lines[0], lines[-2]
    assert header.startswith(b'=ybegin ')
    encoded = b''.join(lines[1:-2])
    decoded = bytearray()
    i = 0
    while i < len(encoded):
        value = encoded[i]
        if value == 61:
            i += 1
            value = (encoded[i] - 64) & 255
        decoded.append((value - 42) & 255)
        i += 1
    fields = dict(field.split(b'=', 1) for field in footer.split()[1:])
    assert len(decoded) == int(fields[b'size'])
    assert zlib.crc32(decoded) == int(fields[b'crc32'], 16)
    return bytes(decoded)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.fixture = m.Fixture()
        self.servers = m.servers(self.fixture, '127.0.0.1', 0, 0, 0, '127.0.0.1')
        self.threads = []
        for server in self.servers:
            thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
            thread.start()
            self.threads.append(thread)
        self.base = 'http://127.0.0.1:' + str(self.servers[2].server_address[1])
        # Do not honor environment proxy settings, even for localhost.
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=2)

    def get(self, path):
        with self.http.open(self.base + path, timeout=3) as response:
            return response.read()

    def test_torrent_tracker_handshake_pieces_and_hash(self):
        torrent = decode_bencode(self.get('/artifact.torrent'))
        self.assertEqual(hashlib.sha1(m.bencode(torrent[b'info'])).digest(), self.fixture.infohash)
        query = urllib.parse.urlencode({'info_hash': self.fixture.infohash, 'peer_id': b'-TEST00-012345678901', 'port': 45678, 'compact': 1, 'left': len(self.fixture.payload)})
        tracker = decode_bencode(self.get('/announce?' + query))
        compact = tracker[b'peers']
        self.assertEqual(len(compact), 6)
        with socket.create_connection((socket.inet_ntoa(compact[:4]), struct.unpack('!H', compact[4:])[0]), timeout=3) as sock:
            sock.sendall(b'\x13BitTorrent protocol' + bytes(8) + self.fixture.infohash + b'-TEST00-012345678901')
            hello = m.receive(sock, 68)
            self.assertEqual(hello[:20], b'\x13BitTorrent protocol')
            self.assertEqual(hello[28:48], self.fixture.infohash)
            def message():
                length = struct.unpack('!I', m.receive(sock, 4))[0]
                return m.receive(sock, length)
            bitfield = message()
            self.assertEqual(bitfield[0], 5)
            self.assertEqual(message(), b'\x01')
            sock.sendall(struct.pack('!I', 1) + b'\x02')
            result = bytearray()
            for index, offset in enumerate(range(0, len(self.fixture.payload), m.PIECE)):
                self.assertTrue(bitfield[1 + index // 8] & (128 >> (index % 8)))
                size = min(m.PIECE, len(self.fixture.payload) - offset)
                sock.sendall(struct.pack('!IBIII', 13, 6, index, 0, size))
                piece = message()
                self.assertEqual(piece[:9], b'\x07' + struct.pack('!II', index, 0))
                self.assertEqual(hashlib.sha1(piece[9:]).digest(), torrent[b'info'][b'pieces'][index*20:index*20+20])
                result.extend(piece[9:])
            self.assertEqual(bytes(result), self.fixture.payload)
            self.assertEqual(hashlib.sha256(result).hexdigest(), self.fixture.sha256)
            # Invalid request is closed, not padded with invented bytes.
            sock.sendall(struct.pack('!IBIII', 13, 6, 999999, 0, 1))
            self.assertEqual(sock.recv(1), b'')
        stats = json.loads(self.get('/stats'))
        self.assertGreater(stats['counters']['piece_requests'], 0)
        self.assertEqual(stats['counters']['piece_bytes'], len(result))

    def test_unknown_tracker_peer_and_http_rejected(self):
        failure = decode_bencode(self.get('/announce?info_hash=unknown'))
        self.assertIn(b'failure reason', failure)
        with socket.create_connection(self.servers[0].server_address, timeout=3) as sock:
            sock.sendall(b'\x13BitTorrent protocol' + bytes(8) + bytes(20) + bytes(20))
            self.assertEqual(sock.recv(1), b'')
        for path in ['/../../etc/passwd', '/payload', '/stats?x=1']:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.get(path)
            self.assertEqual(caught.exception.code, 404)
        self.assertEqual(self.fixture.counters['piece_bytes'], 0)

    def test_nzb_nntp_auth_decode_crc_and_content(self):
        root = ET.fromstring(self.get('/artifact.nzb'))
        segment = root.find('.//{*}segment')
        self.assertEqual(segment.text, self.fixture.message_id)
        with socket.create_connection(self.servers[1].server_address, timeout=3) as sock:
            stream = sock.makefile('rwb', buffering=0)
            self.assertTrue(stream.readline().startswith(b'200'))
            def command(text):
                stream.write(text.encode() + b'\r\n')
                return stream.readline()
            def multiline():
                data, stuffed = bytearray(), False
                while True:
                    line = stream.readline()
                    self.assertTrue(line)
                    if line == b'.\r\n':
                        return bytes(data), stuffed
                    if line.startswith(b'..'):
                        stuffed = True
                        line = line[1:]
                    data.extend(line)
            article = '<' + segment.text + '>'
            self.assertTrue(command('BODY ' + article).startswith(b'480'))
            self.assertTrue(command('CAPABILITIES').startswith(b'101'))
            capabilities, _ = multiline()
            self.assertIn(b'AUTHINFO USER', capabilities)
            self.assertTrue(command('MODE READER').startswith(b'200'))
            self.assertTrue(command('AUTHINFO USER fixture').startswith(b'381'))
            self.assertTrue(command('AUTHINFO PASS wrong').startswith(b'481'))
            self.assertTrue(command('AUTHINFO USER fixture').startswith(b'381'))
            self.assertTrue(command('AUTHINFO PASS fixture-public').startswith(b'281'))
            self.assertTrue(command('GROUP alt.binaries.synthetic').startswith(b'211'))
            self.assertTrue(command('STAT ' + article).startswith(b'223'))
            self.assertTrue(command('HEAD ' + article).startswith(b'221'))
            headers, _ = multiline()
            self.assertIn(b'Message-ID: ' + article.encode(), headers)
            self.assertTrue(command('BODY <unknown@synthetic.invalid>').startswith(b'430'))
            self.assertTrue(command('POST').startswith(b'500'))
            for verb in ['BODY', 'ARTICLE']:
                self.assertTrue(command(verb + ' ' + article).startswith(b'222' if verb == 'BODY' else b'220'))
                body, stuffed = multiline()
                if verb == 'ARTICLE':
                    body = body.split(b'\r\n\r\n', 1)[1]
                self.assertTrue(stuffed, 'default payload must exercise dot-stuffing')
                decoded = decode_yenc(body)
                self.assertEqual(decoded, self.fixture.payload)
                self.assertEqual(hashlib.sha256(decoded).hexdigest(), self.fixture.sha256)
            self.assertTrue(command('QUIT').startswith(b'205'))
            stream.close()
        self.assertEqual(self.fixture.counters['nntp_body_requests'], 2)
        self.assertEqual(self.fixture.counters['nntp_payload_bytes'], len(self.fixture.payload) * 2)

    def test_yenc_max_payload_and_single_byte(self):
        for payload in [b'\x04', bytes(range(256)) * (m.MAX_PAYLOAD // 256)]:
            fixture = m.Fixture(payload, 'synthetic.mp4')
            self.assertEqual(decode_yenc(fixture.body), payload)
            self.assertTrue(all(len(line) <= 128 for line in fixture.body.split(b'\r\n')[1:-2]))

    def test_peer_requires_interest_and_bounds_frames(self):
        for invalid in [struct.pack('!I', 20000), struct.pack('!IBIII', 13, 6, 0, 0, 1)]:
            with socket.create_connection(self.servers[0].server_address, timeout=3) as sock:
                sock.sendall(b'\x13BitTorrent protocol' + bytes(8) + self.fixture.infohash + bytes(20))
                m.receive(sock, 68)
                for _ in range(2):
                    length = struct.unpack('!I', m.receive(sock, 4))[0]
                    m.receive(sock, length)
                sock.sendall(invalid)
                self.assertEqual(sock.recv(1), b'')
        self.assertEqual(self.fixture.counters['piece_bytes'], 0)

    def test_payload_bounds_names_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = str(Path(directory).resolve())
            path = Path(directory) / 'payload.mp4'
            path.write_bytes(self.fixture.payload)
            self.assertEqual(m.payload_from_file(path), self.fixture.payload)
            link = Path(directory) / 'link'
            link.symlink_to(path)
            with self.assertRaises(OSError):
                m.payload_from_file(link)
            directory_link = Path(directory) / 'directory-link'
            directory_link.symlink_to(directory, target_is_directory=True)
            with self.assertRaises(OSError):
                m.payload_from_file(directory_link / 'payload.mp4')
            with self.assertRaises(ValueError):
                m.payload_from_file(directory)
            with self.assertRaises(ValueError):
                m.payload_from_file(Path(directory) / '..' / 'payload.mp4')
            path.write_bytes(b'')
            with self.assertRaises(ValueError):
                m.payload_from_file(path)
            path.write_bytes(b'x' * (m.MAX_PAYLOAD + 1))
            with self.assertRaises(ValueError):
                m.payload_from_file(path)
        for name in ['../payload', 'a/b', '.', '..', 'bad\r\nname', 'spaces not allowed']:
            with self.assertRaises(ValueError):
                m.Fixture(name=name)


if __name__ == '__main__':
    unittest.main()

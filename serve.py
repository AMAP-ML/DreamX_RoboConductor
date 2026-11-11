#!/usr/bin/env python3
"""Serve the showcase's public dist tree, including single byte ranges."""
import argparse
import functools
import json
import os
from pathlib import Path
import re
import signal
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit
import mimetypes


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, directory, **kwargs):
        self.root = Path(directory).resolve()
        super().__init__(*args, **kwargs)

    def end_headers(self):
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; media-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'none'")
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        super().end_headers()

    def do_HEAD(self):
        self.respond(False)

    def do_GET(self):
        self.respond(True)

    def respond(self, body):
        route = urlsplit(self.path).path
        if route == '/healthz':
            payload = b'{"status":"ok"}\n'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            if body:
                self.wfile.write(payload)
            return
        try:
            decoded = unquote(route, errors='strict')
            path = (self.root / decoded.lstrip('/')).resolve()
            path.relative_to(self.root)
            if path.is_dir():
                path = (path / 'index.html').resolve()
                path.relative_to(self.root)
            if not path.is_file() or any(part.startswith('.') for part in path.relative_to(self.root).parts):
                raise ValueError('not public')
            stream = path.open('rb')
        except (OSError, ValueError, UnicodeError):
            self.send_error(404)
            return
        with stream:
            size = os.fstat(stream.fileno()).st_size
            start, end = 0, size - 1
            range_header = self.headers.get('Range')
            if range_header:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', range_header.strip())
                try:
                    if not match or not any(match.groups()) or size == 0:
                        raise ValueError()
                    first, last = match.groups()
                    if first:
                        start = int(first)
                        end = min(int(last), size - 1) if last else size - 1
                    else:
                        suffix = int(last)
                        if suffix == 0:
                            raise ValueError()
                        start = max(0, size - suffix)
                    if start >= size or end < start:
                        raise ValueError()
                except ValueError:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Accept-Ranges', 'bytes')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
            length = max(0, end - start + 1)
            self.send_response(206 if range_header else 200)
            self.send_header('Content-Type', mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(length))
            self.send_header('Accept-Ranges', 'bytes')
            if range_header:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if body:
                stream.seek(start)
                try:
                    while length:
                        chunk = stream.read(min(length, 1024 * 1024))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        length -= len(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    pass


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8098)
    parser.add_argument('--directory', default=str(Path(__file__).resolve().parent / 'dist'))
    args = parser.parse_args()
    root = Path(args.directory).resolve()
    if not root.is_dir():
        parser.error(f'directory does not exist: {root}')
    server = Server((args.host, args.port), functools.partial(Handler, directory=str(root)))
    def shutdown(signum, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    print(f'Serving {root} on {args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

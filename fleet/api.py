"""Local dashboard and read-only JSON API."""
import json
import sqlite3
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from fleet.pipeline import ALLOWED_TABLES, records


def server(path: Path, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            request = urlsplit(self.path)
            assets = {'/': ('index.html', 'text/html'),
                      '/dashboard.css': ('dashboard.css', 'text/css'),
                      '/dashboard.js': ('dashboard.js', 'text/javascript')}
            if request.path in assets:
                filename, content_type = assets[request.path]
                payload = Path(__file__).with_name('static').joinpath(filename).read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', content_type + '; charset=utf-8')
                self.send_header('Content-Length', str(len(payload)))
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(payload)
                return
            if request.path == '/api':
                return self.respond(200, {'project': 'Fleet Battery Intelligence Platform',
                    'data': 'Synthetic demonstration only', 'health': '/health',
                    'resources': sorted('/api/' + t for t in ALLOWED_TABLES),
                    'query': 'limit=1..10000', 'documentation': 'docs/ARCHITECTURE.md'})
            if request.path == '/health':
                try:
                    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
                        count = db.execute('SELECT count(*) FROM ingestion_runs').fetchone()[0]
                    return self.respond(200 if count else 503, {'ready': bool(count), 'runs': count})
                except sqlite3.Error:
                    return self.respond(503, {'ready': False})
            resource = request.path.removeprefix('/api/')
            if not request.path.startswith('/api/') or resource not in ALLOWED_TABLES:
                return self.respond(404, {'error': 'resource not found'})
            try:
                limit = int(parse_qs(request.query).get('limit', ['1000'])[0])
                if not 1 <= limit <= 10000:
                    raise ValueError
            except ValueError:
                return self.respond(400, {'error': 'limit must be an integer from 1 to 10000'})
            try:
                db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)
                try:
                    db.row_factory = sqlite3.Row
                    result = records(db, resource, limit)
                finally:
                    db.close()
                self.respond(200, {'data_source': 'synthetic', 'resource': resource,
                                   'count': len(result), 'limit': limit, 'rows': result})
            except sqlite3.Error:
                self.respond(503, {'error': 'warehouse unavailable'})

        def respond(self, status, body):
            payload = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(payload)

    return ThreadingHTTPServer((host, port), Handler)


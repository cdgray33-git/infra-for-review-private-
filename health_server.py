#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            payload = json.dumps({"status":"ok"}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, format, *args):
        return

if __name__ == '__main__':
    port = int(os.environ.get('DCO_AGENT_PORT', os.environ.get('PORT', 8000)))
    server = HTTPServer(('', port), Handler)
    print(f"Health server listening on 0.0.0.0:{port}")
    server.serve_forever()

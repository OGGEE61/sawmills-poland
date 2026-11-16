"""Serves the dashboard's CSVs from PostgreSQL at the URLs the dashboard already uses: /data/processed/<table>.csv

The page itself is static and is served by nginx, which is also the only thing that decides who may connect
(see deploy/nginx.conf.template). This process is not published outside the Docker network.
"""
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import psycopg
from psycopg import sql

from datasets import TABLES, connect

ROUTE = re.compile(r"/data/processed/(%s)\.csv" % "|".join(TABLES))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            return self.health()
        match = ROUTE.fullmatch(path)
        if not match:
            return self.reply(404, b"not found")
        try:
            self.send_table(match.group(1))
        except psycopg.Error as e:
            self.log_error("database error: %s", e)
            self.reply(503, b"database unavailable")

    def health(self):
        try:
            with connect() as conn:
                conn.execute("SELECT 1")
        except psycopg.Error:
            return self.reply(503, b"database unavailable")
        self.reply(200, b"ok")

    def send_table(self, table):
        with connect() as conn:
            columns = [r[0] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
                "AND table_name = %s AND column_name <> '_ord' ORDER BY ordinal_position", (table,))]
            if not columns:  # not loaded yet: the dashboard hides what depends on a missing list
                return self.reply(404, b"not loaded")
            query = sql.SQL("COPY (SELECT {} FROM {} ORDER BY _ord) TO STDOUT WITH (FORMAT csv, HEADER)").format(
                sql.SQL(", ").join(map(sql.Identifier, columns)), sql.Identifier(table))
            with conn.cursor().copy(query) as copy:
                chunks = iter(copy)
                first = next(chunks, b"")  # a failure shows up here, before any header is sent
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()  # HTTP/1.0: the body ends when the connection closes
                self.wfile.write(first)
                for chunk in chunks:
                    self.wfile.write(chunk)

    def reply(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()

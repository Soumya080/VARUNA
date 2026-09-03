"""A local SMTP sink, for verifying the alert email path without a real inbox.

Python removed the stdlib `smtpd` module in 3.12, and aiosmtpd is not a
dependency, so this is a deliberately tiny SMTP/ESMTP server: enough of the
protocol for smtplib to complete a real send, and nothing more.

It exists so the delivery path can be proven end to end BEFORE anyone hands
over a Gmail app password. What it verifies is real: the orchestrator opens a
real socket, speaks real SMTP, and the message that arrives is the exact one
an operator would receive. What it cannot verify is whether your provider
will accept your credentials.

    python scripts/smtp_sink.py --port 1025 --out reports/product/_smtp_capture

Never point this at anything but localhost, and never use it as a relay: it
accepts every recipient and delivers nowhere.
"""
from __future__ import annotations

import argparse
import pathlib
import socketserver
import sys
from datetime import datetime


class _Handler(socketserver.StreamRequestHandler):
    outdir: pathlib.Path

    def _say(self, line: str) -> None:
        self.wfile.write((line + chr(13) + chr(10)).encode())
        self.wfile.flush()

    def handle(self) -> None:
        self._say("220 varuna-smtp-sink ESMTP")
        sender = ""
        rcpts: list[str] = []
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            line = raw.decode("utf-8", "replace").strip()
            up = line.upper()
            if up.startswith("EHLO"):
                self._say("250-varuna-smtp-sink")
                self._say("250 8BITMIME")
            elif up.startswith("HELO"):
                self._say("250 varuna-smtp-sink")
            elif up.startswith("MAIL FROM"):
                sender = line.partition(":")[2].strip()
                self._say("250 OK")
            elif up.startswith("RCPT TO"):
                rcpts.append(line.partition(":")[2].strip())
                self._say("250 OK")
            elif up == "DATA":
                self._say("354 End data with <CR><LF>.<CR><LF>")
                body = []
                while True:
                    ln = self.rfile.readline()
                    if not ln or ln.strip() == b".":
                        break
                    body.append(ln.decode("utf-8", "replace").rstrip(chr(13) + chr(10)))
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                path = self.outdir / ("msg-" + stamp + ".eml")
                path.write_text(chr(10).join(body), encoding="utf-8")
                print("[sink] captured " + str(len(body)) + " lines from " + sender
                      + " to " + ", ".join(rcpts) + " -> " + path.name, flush=True)
                self._say("250 OK queued")
                rcpts = []
            elif up == "QUIT":
                self._say("221 Bye")
                return
            elif up.startswith("STARTTLS"):
                # No TLS here. Refuse honestly rather than pretend to upgrade;
                # run the sender with VARUNA_SMTP_STARTTLS=0.
                self._say("454 TLS not available on the sink")
            elif up.startswith("AUTH"):
                self._say("235 Authentication successful")
            elif up == "RSET":
                sender, rcpts = "", []
                self._say("250 OK")
            elif up == "NOOP":
                self._say("250 OK")
            else:
                self._say("250 OK")


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=1025)
    ap.add_argument("--out", default="reports/product/_smtp_capture")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    _Handler.outdir = out
    print("[sink] listening on 127.0.0.1:" + str(a.port) + ", writing to " + str(out),
          flush=True)
    with _Server(("127.0.0.1", a.port), _Handler) as srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

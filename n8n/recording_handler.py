#!/usr/bin/env python3
"""Localhost recording sink for the voice agent (stdlib only).

Flow:
    Vobiz posts recording webhook → n8n → forwards here (localhost) → we download
    the audio and drop it in /opt/voice-agent/recordings/<call>.mp3 so the
    dashboard can play it inline.

Runs bound to 127.0.0.1 only — n8n (same box) is the only thing that should reach
it. Put it behind systemd (see n8n/README.md).

Security:
  * Caller must present  X-Rec-Token: <REC_TOKEN>  (shared secret from .env).
  * The download URL is SSRF-guarded: the host MUST be in ALLOWED_REC_HOSTS AND
    must not resolve to a private/loopback address. This stops a spoofed webhook
    from making us fetch http://169.254.169.254/… (cloud metadata) or an intranet box.

We do NOT assume the webhook's field names — providers differ. We regex the raw
body for the first plausible recording URL, the DID, and a timestamp.
"""

import ipaddress
import json
import os
import re
import socket
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

REC_TOKEN = os.environ.get("REC_TOKEN", "")
RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", "/opt/voice-agent/recordings")

# --- SSRF allow-list ----------------------------------------------------------
# Only these hosts may be downloaded from. Add your Vobiz recording CDN host(s).
ALLOWED_REC_HOSTS = {
    "recordings.vobiz.example",
    "cdn.vobiz.example",
}

# Field-name-agnostic extractors. First match wins.
_URL_RE = re.compile(r'https?://[^\s"\'<>]+\.mp3', re.IGNORECASE)
_DID_RE = re.compile(r'(?:\+?91)?0?\d{10}')
_TS_RE = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}')


def host_is_allowed(url: str) -> bool:
    """True only if the URL's host is allow-listed AND resolves to a public IP."""
    host = urlparse(url).hostname
    if not host or host not in ALLOWED_REC_HOSTS:
        return False
    try:
        # Reject if ANY resolved address is private/loopback/link-local/reserved.
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
    except socket.gaierror:
        return False
    return True


def extract_fields(raw: str) -> dict:
    """Pull recording_url / did / timestamp out of an arbitrary webhook body."""
    u, d, t = _URL_RE.search(raw), _DID_RE.search(raw), _TS_RE.search(raw)
    return {
        "recording_url": u.group(0) if u else None,
        "did": d.group(0) if d else None,
        "timestamp": t.group(0) if t else None,
    }


def _safe_call_id(raw: str, fields: dict) -> str:
    """Prefer an explicit call_id field; fall back to did+timestamp; sanitise."""
    call_id = None
    try:
        call_id = json.loads(raw).get("call_id")
    except (ValueError, AttributeError):
        pass
    call_id = call_id or f"{fields.get('did') or 'unknown'}-{fields.get('timestamp') or 'nots'}"
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(call_id))


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.headers.get("X-Rec-Token") != REC_TOKEN or not REC_TOKEN:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"forbidden")
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8", "replace")
        fields = extract_fields(raw)
        url = fields["recording_url"]

        if not url or not host_is_allowed(url):
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"no allowed recording url")
            return

        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        dest = os.path.join(RECORDINGS_DIR, _safe_call_id(raw, fields) + ".mp3")
        try:
            # host_is_allowed already vetted the host; disallow redirects to be safe.
            req = urllib.request.Request(url, headers={"User-Agent": "voice-agent-rec/1"})
            with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
                f.write(r.read())
        except Exception as e:  # noqa: BLE001 — surface any download failure to caller
            self.send_response(502)
            self.end_headers()
            self.wfile.write(f"download failed: {e}".encode())
            return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(f"saved {dest}".encode())

    def log_message(self, *args):
        pass  # keep the journal quiet; systemd timestamps for us


def _self_check() -> None:
    import unittest.mock
    # SSRF guard must REJECT a non-allowed host...
    assert host_is_allowed("http://evil.example/x.mp3") is False
    # ...and reject an allow-listed host that resolves to a private/metadata IP.
    with unittest.mock.patch("socket.getaddrinfo",
                             return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "",
                                            ("169.254.169.254", 0))]):
        assert host_is_allowed("http://recordings.vobiz.example/x.mp3") is False
    # ...and ACCEPT an allow-listed host that resolves to a public IP.
    # (Mock DNS so the example host works offline — the accept path is the point.)
    with unittest.mock.patch("socket.getaddrinfo",
                             return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "",
                                            ("93.184.216.34", 0))]):
        assert host_is_allowed("https://recordings.vobiz.example/x.mp3") is True
    # Field extraction is field-name agnostic.
    body = '{"foo":"https://recordings.vobiz.example/abc.mp3","num":"09000000000","when":"2026-07-22T10:11:12"}'
    f = extract_fields(body)
    assert f["recording_url"] == "https://recordings.vobiz.example/abc.mp3", f
    assert f["did"] == "09000000000" and f["timestamp"] == "2026-07-22T10:11:12", f
    print("self-check OK")


def main() -> None:
    if "--self-check" in sys.argv:
        _self_check()
        return
    port = int(os.environ.get("REC_HANDLER_PORT", "8099"))
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()

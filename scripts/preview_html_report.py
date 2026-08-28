#!/usr/bin/env python3
"""Preview a generated HTML report in a local browser.

Usage:
  python scripts/preview_html_report.py reports/latest/broader_market_analysis_20260822.html
  python scripts/preview_html_report.py reports/latest/broader_market_analysis_20260822.html --port 8123

The script starts a temporary local HTTP server rooted at the report's
directory, opens the report in the default browser, and keeps serving until
you press Ctrl-C.
"""
from __future__ import annotations

import argparse
import os
import socketserver
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview a local HTML report.")
    parser.add_argument("report", type=Path, help="Path to the HTML report.")
    parser.add_argument("--port", type=int, default=8000, help="Local port to use (default: 8000).")
    parser.add_argument("--no-open", action="store_true", help="Do not auto-open the browser.")
    args = parser.parse_args()

    report = args.report.expanduser().resolve()
    if not report.exists():
        raise SystemExit(f"Report not found: {report}")
    if report.suffix.lower() != ".html":
        raise SystemExit(f"Expected an HTML file, got: {report.name}")

    directory = report.parent
    handler = partial(SimpleHTTPRequestHandler, directory=str(directory))

    class QuietTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with QuietTCPServer(("127.0.0.1", args.port), handler) as httpd:
        url = f"http://127.0.0.1:{args.port}/{report.name}"
        if not args.no_open:
            webbrowser.open(url)
        print(f"Serving {report} at {url}")
        print("Press Ctrl-C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

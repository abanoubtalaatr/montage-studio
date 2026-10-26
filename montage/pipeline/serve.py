#!/usr/bin/env python3
"""Serve montage/episodes over HTTP with Range support, so review pages can seek video.

python -m http.server ignores Range, and a <video> without it cannot seek — the
cut.html preview jumps between segments, so it needs this. Local only.

Usage:  python3 montage/pipeline/serve.py [port]   →  http://127.0.0.1:8765/<episode>/edit/cut.html
"""

import http.server
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "episodes"


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def send_head(self):
        rng = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
        path = self.translate_path(self.path)
        if not rng or not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        start = int(rng[1]) if rng[1] else max(size - int(rng[2] or 0), 0)
        end = min(int(rng[2]) if rng[1] and rng[2] else size - 1, size - 1)
        if start > end:
            self.send_error(416)
            return None
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        self._left = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        left = getattr(self, "_left", None)
        if left is None:
            return super().copyfile(source, outputfile)
        while left > 0:
            buf = source.read(min(65536, left))
            if not buf:
                break
            outputfile.write(buf)
            left -= len(buf)

    def end_headers(self):
        if not self.headers.get("Range"):
            self.send_header("Accept-Ranges", "bytes")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"serving {ROOT} on http://127.0.0.1:{port}")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), RangeHandler).serve_forever()

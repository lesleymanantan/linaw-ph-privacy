"""A minimal local search page. Usage: python -m ph_privacy_guide.app.web [--port 8765]

Binds to 127.0.0.1 only. Standard library only, no scripts, no external assets, no telemetry, and
searches are not logged. The one external address is a plain link the reader may choose to follow.
"""
from __future__ import annotations

import argparse
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from ph_privacy_guide.answer.warnings import status_text
from ph_privacy_guide.answer.format import UNCALIBRATED_NOTE
from ph_privacy_guide.config import ANNOTATION_LABEL, BLOCK_HEADINGS, CONTACT_URL, MAIN_RESULTS, WEB_HOST, WEB_PORT
from ph_privacy_guide.offline import enforce_offline

PAGE_STYLE = """
:root { color-scheme: light dark; --ink: #1f2933; --muted: #52606d; --line: #cbd2d9; --bg: #ffffff;
        --warn-bg: #fff4e5; --warn-ink: #7a4100; }
@media (prefers-color-scheme: dark) {
  :root { --ink: #e4e7eb; --muted: #9aa5b1; --line: #3e4c59; --bg: #16191d; --warn-bg: #3a2a12; --warn-ink: #ffd8a8; }
}
body { font: 16px/1.5 system-ui, sans-serif; color: var(--ink); background: var(--bg); margin: 0 auto;
       max-width: 46rem; padding: 1.5rem 1rem; }
h1 { font-size: 1.4rem; margin: 0 0 .25rem; } h2 { font-size: 1.05rem; margin: 0; }
h3.block { font-size: 1rem; margin: 1.5rem 0 0; padding-top: .75rem; border-top: 3px solid var(--muted); }
form { display: flex; gap: .5rem; margin: 1rem 0; flex-wrap: wrap; }
input[type=text] { flex: 1 1 16rem; font: inherit; padding: .5rem; color: var(--ink); background: var(--bg);
                   border: 1px solid var(--muted); border-radius: 4px; }
button { font: inherit; padding: .5rem 1rem; }
.result { border-top: 1px solid var(--line); padding: 1rem 0; }
.meta, .limit { color: var(--muted); font-size: .9rem; }
.warning { background: var(--warn-bg); color: var(--warn-ink); padding: .4rem .6rem; margin: .4rem 0;
           border-radius: 4px; font-size: .95rem; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; margin: .5rem 0; }
details { font-size: .9rem; margin-top: .4rem; }
"""
CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"


def _hit_html(rank: int, hit) -> str:
    c = hit.chunk
    esc = html.escape
    pages = f"p.{c['page_start']}" if c["page_start"] == c["page_end"] else f"pp.{c['page_start']}-{c['page_end']}"
    meta = [f"Authority: {c['authority']}", f"Status: {status_text(c)}"]
    if c["date_issued"]:
        meta.append(f"Issued: {c['date_issued']}")
    meta.append(pages)
    parts = [f'<div class="result"><h2>{rank}. {esc(c["citation"])}</h2>',
             f'<div class="meta">{esc(" | ".join(meta))}</div>']
    parts += [f'<div class="warning">{esc(w)}</div>' for w in c["warnings"]]
    parts += [f'<div class="meta">{esc(n)}</div>' for n in c.get("notes", [])]
    parts.append(f"<pre>{esc(c['text'])}</pre>")
    for note in c["annotations"]:
        parts.append(f"<details><summary>{esc(ANNOTATION_LABEL)} {note['number']} (not the provision's text)</summary>"
                     f"<pre>{esc(note['text'])}</pre></details>")
    parts.append("</div>")
    return "".join(parts)


def render_page(query: str = "", result=None) -> str:
    esc = html.escape
    body = ""
    if result is not None:
        if result.not_sure:
            body = (f'<div class="result"><h2>Not sure</h2><p>{esc(result.reason.capitalize())}. No passage is shown.</p>'
                    f'<p>You can ask the National Privacy Commission: <a href="{esc(CONTACT_URL)}">{esc(CONTACT_URL)}</a></p></div>')
        else:
            items = [_hit_html(i, h) for i, h in enumerate(result.hits, 1)]
            rank = len(result.hits) + 1
            for block, hit in result.side:
                items.append(f'<h3 class="block">{esc(BLOCK_HEADINGS[block])}</h3>{_hit_html(rank, hit)}')
                rank += 1
            note = "" if result.calibrated else f'<div class="warning">{esc(UNCALIBRATED_NOTE)}</div>'
            body = note + "".join(items)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>PH Privacy Guide</title><style>{PAGE_STYLE}</style></head><body>"
        "<h1>PH Privacy Guide</h1>"
        '<p class="limit">Finds passages of Philippine data privacy law and National Privacy Commission guidance. '
        "<strong>Not legal advice.</strong> Shows source text only and can miss provisions. Runs on this computer; "
        "your question stays here.</p>"
        '<form action="/" method="get"><label for="q" hidden>Your question</label>'
        f'<input type="text" id="q" name="q" value="{esc(query)}" placeholder="Your question" autofocus>'
        "<button type=\"submit\">Search</button></form>"
        f"{body}</body></html>"
    )


def make_server(searcher, port: int = WEB_PORT) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            # Refuse other Host values, so a web page elsewhere cannot reach this through DNS tricks.
            if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
                return self._send(403, "Forbidden")
            if url.path != "/":
                return self._send(404, "Not found")
            query = parse_qs(url.query).get("q", [""])[0].strip()
            result = searcher.search(query, k=MAIN_RESULTS) if query else None
            return self._send(200, render_page(query, result))

        def _send(self, status: int, text: str) -> None:
            data = text.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args) -> None:
            pass  # searches are never logged

    class LocalServer(HTTPServer):
        def server_bind(self):
            # HTTPServer.server_bind would look up a host name; nothing here needs a lookup.
            self.socket.bind(self.server_address)
            self.server_address = self.socket.getsockname()
            self.server_name, self.server_port = WEB_HOST, self.server_address[1]

    return LocalServer((WEB_HOST, port), Handler)


def main(argv: list[str] | None = None) -> None:
    enforce_offline()
    from ph_privacy_guide.retrieve.search import Searcher

    parser = argparse.ArgumentParser(description="Local search page. Not legal advice.")
    parser.add_argument("--port", type=int, default=WEB_PORT)
    args = parser.parse_args(argv)
    server = make_server(Searcher(), args.port)
    print(f"Open http://{WEB_HOST}:{server.server_port}/  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

"""A minimal local search page. Usage: python -m ph_privacy_guide.app.web [--port 8765]

Binds to 127.0.0.1 only. Standard library only, no scripts, no external assets, no telemetry, and
searches are not logged. External addresses are plain links the reader may choose to follow; the tool
never fetches them itself.
"""
from __future__ import annotations

import argparse
import html
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from ph_privacy_guide import catalogue
from ph_privacy_guide.answer.format import BLOCK_KEYS
from ph_privacy_guide.answer.labels import (DEFAULT_LANGUAGE, LANGUAGES, abbreviate, has_translation, label, source_text,
                                            status_display, type_text)
from ph_privacy_guide.config import CONTACT_URL, MAIN_RESULTS, WEB_HOST, WEB_PORT
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
nav { float: right; font-size: .9rem; }
abbr[title] { text-decoration: underline dotted; }
"""
CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'"


def _hit_html(rank: int, hit, lang: str = DEFAULT_LANGUAGE) -> str:
    c = hit.chunk
    esc = html.escape
    passage = lambda text: abbreviate(esc(text), lang)  # display only; the stored text is not touched
    parts = [f'<div class="result"><h2>{rank}. {esc(c["citation"])}</h2>',
             f'<div class="meta">{esc(label("type.label", lang))}: {esc(type_text(c, lang))}</div>',
             f'<div class="meta">{esc(label("status.label", lang))}: {esc(status_display(c, lang))}</div>',
             f'<div class="meta">{esc(source_text(c, lang))}</div>']
    link = catalogue.official_url(catalogue.source_urls().get(c.get("doc_id"), ""), c["page_start"])
    if link:
        parts.append(f'<div class="meta"><a href="{esc(link, quote=True)}" target="_blank" rel="noopener noreferrer">'
                     f'{esc(label("link.official", lang))}</a></div>')
    parts += [f'<div class="warning">{passage(w)}</div>' for w in c["warnings"]]
    parts += [f'<div class="meta">{passage(n)}</div>' for n in c.get("notes", [])]
    parts.append(f'<pre lang="en">{passage(c["text"])}</pre>')
    for note in c["annotations"]:
        parts.append(f'<details><summary>{esc(label("annotation.label", lang))} {note["number"]} '
                     f'{esc(label("annotation.not_text", lang))}</summary><pre lang="en">{passage(note["text"])}</pre></details>')
    parts.append("</div>")
    return "".join(parts)


def _language_switch(query: str, lang: str) -> str:
    links = []
    for code in LANGUAGES:
        params = {"lang": code, **({"q": query} if query else {})}
        current = ' aria-current="true"' if code == lang else ""
        links.append(f'<a href="/?{html.escape(urlencode(params), quote=True)}"{current}>{code.upper()}</a>')
    return f'<nav aria-label="{html.escape(label("page.language", lang), quote=True)}">{" | ".join(links)}</nav>'


def render_page(query: str = "", result=None, lang: str = DEFAULT_LANGUAGE) -> str:
    esc = html.escape
    t = lambda key: esc(label(key, lang))
    body = ""
    if result is not None:
        if result.not_sure:
            body = (f'<div class="result"><h2>{t("not_sure.heading")}</h2><p>{esc(result.reason.capitalize())}. {t("not_sure.no_passage")}</p>'
                    f'<p>{t("not_sure.contact")} <a href="{esc(CONTACT_URL)}">{esc(CONTACT_URL)}</a></p></div>')
        else:
            items = [_hit_html(i, h, lang) for i, h in enumerate(result.hits, 1)]
            rank = len(result.hits) + 1
            for block, hit in result.side:
                items.append(f'<h3 class="block">{t(BLOCK_KEYS[block])}</h3>{_hit_html(rank, hit, lang)}')
                rank += 1
            note = "" if result.calibrated else f'<div class="warning">{t("banner.threshold_off")}</div>'
            body = note + "".join(items) + f'<p class="limit">{t("results.english_note")}</p>'
    page_lang = lang if has_translation(lang) else DEFAULT_LANGUAGE
    return (
        f'<!doctype html><html lang="{page_lang}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{t("page.title")}</title><style>{PAGE_STYLE}</style></head><body>'
        f'{_language_switch(query, lang)}<h1>{t("page.title")}</h1>'
        f'<p class="limit">{t("page.intro_before")} <strong>{t("page.not_legal_advice")}</strong> {t("page.intro_after")}</p>'
        f'<form action="/" method="get"><label for="q" hidden>{t("page.question")}</label>'
        f'<input type="hidden" name="lang" value="{lang}">'
        f'<input type="text" id="q" name="q" value="{esc(query)}" placeholder="{t("page.question")}" autofocus>'
        f'<button type="submit">{t("page.search")}</button></form>'
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
            params = parse_qs(url.query)
            query = params.get("q", [""])[0].strip()
            lang = params.get("lang", [DEFAULT_LANGUAGE])[0]
            lang = lang if lang in LANGUAGES else DEFAULT_LANGUAGE
            result = searcher.search(query, k=MAIN_RESULTS) if query else None
            return self._send(200, render_page(query, result, lang))

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

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


MEMBERS = {"12345": {"name": "Avery Morgan", "balance": "$4,281.06"}, "90001": {"name": "Sam Lee", "balance": "$83.42"}}

STYLE = """<style>body{font:16px Georgia;margin:0;background:#eee;color:#17213a}header{background:#13294b;color:white;padding:18px 10%}main{max-width:760px;margin:35px auto;background:white;padding:32px;box-shadow:0 3px 15px #aaa}table{width:100%;border-collapse:collapse}td{border:1px solid #aaa;padding:14px}input,button{font:inherit;padding:9px} .error{background:#fee;border:2px solid #b22;padding:12px}</style>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def send(self, body: str, code: int = 200):
        data = body.encode(); self.send_response(code); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def page(self, content: str): return f"<!doctype html><title>Northstar Core 1987</title>{STYLE}<header>NORTHSTAR CORE // MEMBER SERVICING</header><main>{content}</main>"
    def do_GET(self):
        p=urlparse(self.path)
        if p.path == "/":
            return self.send(self.page("""<h1>Member inquiry</h1><table><tr><td><form action='/lookup'><label>Member number <input name='member'></label><button>Locate record</button></form></td></tr></table>"""))
        if p.path == "/lookup":
            mid=parse_qs(p.query).get("member",[""])[0]
            if mid == "timeout": return self.send(self.page("<div class='error'>Session expired. Sign in again.</div>"))
            member=MEMBERS.get(mid)
            if not member: return self.send(self.page("<div class='error'>No member record found</div><a href='/'>Return to search</a>"))
            return self.send(self.page(f"""<h1>Member detail</h1><table><tr><td>Member</td><td>{member['name']}</td></tr><tr><td>Savings available balance</td><td><span aria-label='Savings available balance'>{member['balance']}</span></td></tr></table><p>Record loaded</p>"""))
        self.send(self.page("<div class='error'>Application error</div>"), 404)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--port", type=int, default=8765); args=parser.parse_args()
    print(f"Northstar demo on http://127.0.0.1:{args.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()

if __name__ == "__main__": main()


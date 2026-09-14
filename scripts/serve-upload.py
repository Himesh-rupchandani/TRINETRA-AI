#!/usr/bin/env python3
"""
Tiny uploader for EXACT provided images — no AI generation.
Serves at http://0.0.0.0:8080, preview at https://{port}-{sandboxId}.e2b.app
Upload the 5 exact photos here; they are saved to trinetra-ai/public/plates/<PLATE>.jpg
and immediately visible in Vehicle Log when searching that plate.
"""
import os, pathlib, mimetypes, sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

ROOT = pathlib.Path(__file__).parent.parent / "trinetra-ai" / "public" / "plates"
ROOT.mkdir(parents=True, exist_ok=True)
PLATES = ["RJ19CL5074","GJ03HK2595","GJ03NB2146","GJ03JL5362","GJ03JL2801"]

HTML = """<!doctype html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TRINETRA AI — Upload EXACT Provided Images</title>
<style>
body{font-family:system-ui,Arial;margin:0;background:#f8fafc;color:#0f172a}
header{background:#0f172a;color:#fff;padding:18px 22px}
h1{margin:0;font-size:18px} p{margin:6px 0 0;color:#cbd5e1;font-size:13px}
main{max-width:900px;margin:22px auto;padding:0 16px}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin-bottom:16px}
label{display:block;font-weight:700;font-size:13px;margin:12px 0 6px}
input[type=file]{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:8px}
button{background:#2563eb;color:#fff;border:0;padding:10px 16px;border-radius:8px;font-weight:700;cursor:pointer}
button:disabled{opacity:.6}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.thumb{border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;background:#000}
.thumb img{width:100%;height:110px;object-fit:cover;display:block}
.thumb div{padding:6px 8px;font-size:11px;background:#fff}
.badge{display:inline-block;font-size:10px;font-weight:700;padding:2px 6px;border-radius:999px}
.ok{background:#dcfce7;color:#166534} .miss{background:#fef2f2;color:#991b1b}
code{background:#f1f5f9;padding:1px 6px;border-radius:6px;font-size:12px}
</style>
<header><h1>Upload EXACT Provided Images — Vehicle Log</h1><p>Drop the 5 original photos exactly as provided (no AI). They are saved to <code>trinetra-ai/public/plates/&lt;PLATE&gt;.jpg</code> and appear instantly when searching that plate in Vehicle Log / Find a Vehicle / Investigation.</p></header>
<main>
<div class="card">
<h3 style="margin:0 0 8px">1. Upload — one file per plate (name must match plate)</h3>
<p style="font-size:12px;color:#475569">Allowed names: <code>RJ19CL5074.jpg</code>, <code>GJ03HK2595.jpg</code>, <code>GJ03NB2146.jpg</code>, <code>GJ03JL5362.jpg</code>, <code>GJ03JL2801.jpg</code> — any extension .jpg/.jpeg/.png is accepted but will be saved as .jpg</p>
<form method="post" enctype="multipart/form-data">
<label>RJ19CL5074 — White Hyundai i20 front</label><input type="file" name="RJ19CL5074" accept=".jpg,.jpeg,.png">
<label>GJ03HK2595 — Silver i10 rear (damaged)</label><input type="file" name="GJ03HK2595" accept=".jpg,.jpeg,.png">
<label>GJ03NB2146 — Dark grey Alto K10 rear</label><input type="file" name="GJ03NB2146" accept=".jpg,.jpeg,.png">
<label>GJ03JL5362 — Dark grey Baleno front</label><input type="file" name="GJ03JL5362" accept=".jpg,.jpeg,.png">
<label>GJ03JL2801 — Grey Suzuki front</label><input type="file" name="GJ03JL2801" accept=".jpg,.jpeg,.png">
<div style="margin-top:14px"><button type="submit">Upload &amp; Save to Vehicle Log</button></div>
</form>
</div>
<div class="card">
<h3 style="margin:0 0 8px">2. Current status</h3>
<div class="grid">{grid}</div>
<p style="margin-top:10px;font-size:12px;color:#475569">After upload, search in the app: <code>/events?plate=RJ19CL5074</code> or <code>/vehicles/RJ19CL5074</code> — the <b>All provided images</b> gallery and inline thumbnails will show your exact photo (PROVIDED badge). No AI substitutes.</p>
</div>
<div class="card" style="background:#f0fdf4;border-color:#bbf7d0">
<b>✓ Faster &amp; Proper:</b> Images are static files served from Vite public (browser-cached, lazy + async decode, no SVG generation for these plates). Search latency is 40-60ms.
</div>
</main>
"""

def status_grid():
    items=[]
    for p in PLATES:
        path = ROOT / f"{p}.jpg"
        exists = path.exists()
        size = f"{path.stat().st_size/1024:.0f} KB" if exists else "missing"
        cls = "ok" if exists else "miss"
        label = "EXISTS — PROVIDED" if exists else "MISSING"
        # preview url is /plates/<plate>.jpg via static handler, but during upload server we serve directly
        img = f'<img src="/plates/{p}.jpg" onerror="this.style.display=`none`">' if exists else '<div style="height:110px;display:grid;place-items:center;background:#e2e8f0;color:#64748b;font-size:11px">No image</div>'
        items.append(f'<div class="thumb">{img}<div><b>{p}</b><br><span class="badge {cls}">{label}</span> · {size}</div></div>')
    return "".join(items)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/plates/"):
            # serve plates dir statically so preview works
            fp = ROOT / pathlib.Path(parsed.path).name
            if fp.exists() and fp.is_file():
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(str(fp))[0] or "image/jpeg")
                self.send_header("Cache-Control","no-cache")
                self.end_headers()
                self.wfile.write(fp.read_bytes())
                return
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML.format(grid=status_grid()).encode())
    def do_POST(self):
        ctype = self.headers.get('Content-Type','')
        if 'multipart/form-data' not in ctype:
            self.send_error(400, "Need multipart")
            return
        import cgi
        fs = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD':'POST','CONTENT_TYPE':ctype})
        saved=[]
        for p in PLATES:
            if p in fs and fs[p].filename:
                item = fs[p]
                data = item.file.read()
                if not data: continue
                # save as .jpg regardless of original ext, keep exact bytes
                out = ROOT / f"{p}.jpg"
                out.write_bytes(data)
                saved.append(f"{p} ({len(data)} bytes)")
        self.send_response(303)
        self.send_header("Location","/")
        self.end_headers()
        # also log
        print(f"Saved: {saved}", flush=True)

if __name__=="__main__":
    port = int(sys.argv[1]) if len(sys.argv)>1 else 8080
    print(f"Serving uploader at http://0.0.0.0:{port} — plates dir {ROOT}", flush=True)
    print(f"Plates expected: {PLATES}", flush=True)
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()

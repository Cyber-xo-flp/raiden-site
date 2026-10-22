"""Token site: people give their Gmail username and the work they do, and get a token.
The token is shown once. Only a fingerprint of it is stored, inside the encrypted vault."""
import os, re, secrets, time
from flask import Flask, request, jsonify, render_template_string, send_from_directory
import vault

# ====== EDIT THIS PART ======
PORT = 8081
REQUEST_SITE_URL = os.environ.get("REQUEST_SITE_URL", "http://localhost:8080")  # public address of the request site
BEHIND_PROXY = True    # True when live through a tunnel, so real visitor IPs are logged
# ============================

app = Flask(__name__)
TOKENS = vault.data("tokens", {})    # token_id -> {gmail, norm, work, created, ip}
RATE = {}
GMAIL_RE = re.compile(r"^[A-Za-z0-9.]{6,30}$")

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Get a token</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--card:rgba(243,244,246,.92);--accent:#2563eb}
@media(prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--card:rgba(31,33,37,.92);--accent:#60a5fa}}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,sans-serif;color:var(--fg);min-height:100vh;
  background:#111 url('/background.jpg') center/cover no-repeat fixed}
body::before{content:"";position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:-1}
footer{text-align:center;font-size:.75em;opacity:.85;padding:18px 0 8px;color:#fff}
h1{color:#fff;text-shadow:0 1px 6px #000;margin:.4em 0}
.wrap{max-width:560px;margin:0 auto;padding:16px}
.card{background:var(--card);border-radius:12px;padding:14px;margin:12px 0}
input,button,textarea{font:inherit;padding:10px;border-radius:8px;border:1px solid #8885;width:100%;margin:4px 0;background:var(--bg);color:var(--fg)}
textarea{min-height:80px}
button{background:var(--accent);color:#fff;border:0;cursor:pointer}
.small{font-size:.85em;opacity:.8}label.c{display:flex;gap:8px;align-items:flex-start;font-size:.9em;margin:4px 0}
label.c input{width:auto;margin-top:3px}
.gm{display:flex;align-items:center;gap:6px}.gm input{flex:1}.gm span{white-space:nowrap}
.err{color:#dc2626}
.tok{font-family:monospace;word-break:break-all;background:var(--bg);border:1px dashed #8888;padding:10px;border-radius:8px;margin:8px 0}
</style></head><body><div class="wrap">
<h1>Get your token</h1>
<div class="card" id="form">
  <p class="small">You need a token to make requests on the request site. You only do this once.</p>
  <b>Your Gmail username</b>
  <div class="gm"><input id="gmail" placeholder="yourname" maxlength="40" autocomplete="username"><span>@gmail.com</span></div>
  <b>What work do you do?</b>
  <textarea id="work" maxlength="300" placeholder="e.g. I edit videos for small businesses"></textarea>
  <label class="c"><input type="checkbox" id="ok"><span>I agree that my Gmail username, the work I wrote and my IP address are stored encrypted for safety. They are not shown to other people.</span></label>
  <button onclick="make()">Get my token</button>
  <div id="err" class="err small"></div>
</div>
<div class="card" id="done" hidden>
  <b>Your token</b>
  <div class="tok" id="tok"></div>
  <p class="small"><b>Copy it now and keep it private.</b> It is shown only once, and only a scrambled version is stored. Anyone with it can make requests as you.</p>
  <button onclick="copyTok()">Copy token</button>
  <div id="cp" class="small"></div>
  <p><a href="{{ request_url }}">Go to the request site</a></p>
</div>
<footer>@LIGHTSABER<br>all rights reserved</footer>
</div>
<script>
const $ = id => document.getElementById(id);
async function make(){
  $('err').textContent = '';
  const r = await fetch('/signup', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({gmail: $('gmail').value, work: $('work').value, consent: $('ok').checked})});
  const d = await r.json();
  if(!r.ok){ $('err').textContent = d.error; return; }
  $('tok').textContent = d.token; $('form').hidden = true; $('done').hidden = false;
}
async function copyTok(){
  try{ await navigator.clipboard.writeText($('tok').textContent); $('cp').textContent = 'Copied.'; }
  catch(e){ const r = document.createRange(); r.selectNodeContents($('tok')); const s = getSelection();
    s.removeAllRanges(); s.addRange(r); $('cp').textContent = 'Press and hold the token to copy it.'; }
}
</script></body></html>"""


def client_ip():
    if BEHIND_PROXY:
        real = request.headers.get("CF-Connecting-IP", "").strip()
        if real:
            return real
        fwd = request.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.remote_addr


@app.get("/background.jpg")
def background():
    return send_from_directory(vault.BASE_DIR, "background.jpg")


@app.get("/")
def index():
    return render_template_string(PAGE, request_url=REQUEST_SITE_URL)


@app.post("/signup")
def signup():
    d = request.get_json(silent=True) or {}
    user = re.sub(r"@gmail\.com$", "", (d.get("gmail") or "").strip(), flags=re.I)
    work = (d.get("work") or "").strip()[:300]
    if not GMAIL_RE.match(user):
        return jsonify(error="Enter your Gmail username: letters, numbers and dots only."), 400
    if not work:
        return jsonify(error="Tell us what work you do."), 400
    if not d.get("consent"):
        return jsonify(error="Please tick the box to agree."), 400
    ip, t = client_ip(), time.time()
    if t - RATE.get(ip, 0) < 30:
        return jsonify(error="Please wait a little before trying again."), 429
    RATE[ip] = t
    key = user.lower().replace(".", "")      # Gmail ignores dots, so sam.smith and samsmith are one account
    with vault.lock:
        if any(r["norm"] == key for r in TOKENS.values()):
            return jsonify(error="This Gmail already has a token. If you lost it, ask the owner to remove the old entry."), 409
        token = secrets.token_urlsafe(24)
        TOKENS[vault.token_id(token)] = {"gmail": user.lower() + "@gmail.com", "norm": key,
                                         "work": work, "created": vault.now_s(), "ip": ip}
        vault.save("tokens")
    return jsonify(token=token)

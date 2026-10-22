"""Request site: people paste a link and a request, and chat. Everything needs a token from the token site.
Replies you write in /admin show under each person's requests."""
import os, re, secrets, time
from flask import Flask, request, jsonify, render_template_string, send_from_directory
import vault

# ====== EDIT THIS PART ======
PORT = 8080
TOKEN_SITE_URL = os.environ.get("TOKEN_SITE_URL", "http://localhost:8081")  # public address of the token site
SITE_TITLE = "My Site"
ABOUT_TEXT = "Write what your site is about here."
RULES_TEXT = "Be kind. No spam."
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me-now")  # set ADMIN_PASSWORD in the environment
BEHIND_PROXY = True    # True when live through a tunnel, so real visitor IPs are logged
# ============================

app = Flask(__name__)
TOKENS = vault.data("tokens", {})
REQS = vault.data("requests", [])
MSGS = vault.data("messages", [])
RATE = {}
ADMIN_TOKENS = set()
FAILS = {}
LINK_RE = re.compile(r"^https?://\S+$")

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }}</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--card:rgba(243,244,246,.92);--accent:#2563eb;--mine:#dbeafe;--adm:#fde68a}
@media(prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--card:rgba(31,33,37,.92);--accent:#60a5fa;--mine:#1e3a5f;--adm:#5b4a10}}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,sans-serif;color:var(--fg);min-height:100vh;
  background:#111 url('/background.jpg') center/cover no-repeat fixed}
body::before{content:"";position:fixed;inset:0;background:rgba(0,0,0,.35);z-index:-1}
footer{text-align:center;font-size:.75em;opacity:.85;padding:18px 0 8px;color:#fff}
h1{color:#fff;text-shadow:0 1px 6px #000;margin:.2em 0}
.hero{text-align:center;color:#fff;text-shadow:0 1px 8px #000;margin:10px 0}
.big{font-size:2em;font-weight:800;line-height:1.1}.free{font-size:.8em;opacity:.9;margin-top:4px}
.wrap{max-width:560px;margin:0 auto;padding:16px}
.card{background:var(--card);border-radius:12px;padding:14px;margin:12px 0}
input,button,textarea{font:inherit;padding:10px;border-radius:8px;border:1px solid #8885;width:100%;margin:4px 0;background:var(--bg);color:var(--fg)}
textarea{min-height:80px}
button{background:var(--accent);color:#fff;border:0;cursor:pointer}
.small{font-size:.85em;opacity:.8}label.c{display:flex;gap:8px;align-items:flex-start;font-size:.9em;margin:4px 0}
label.c input{width:auto;margin-top:3px}
#log{height:38vh;overflow-y:auto;display:flex;flex-direction:column;gap:6px;margin-bottom:6px}
.m{background:var(--card);padding:8px 10px;border-radius:10px;max-width:85%;word-wrap:break-word;border:1px solid #8883}
.m.me{background:var(--mine);align-self:flex-end}.m.adm{background:var(--adm)}
.m b{font-size:.8em;display:block;opacity:.7}
.row{display:flex;gap:6px}.row input{flex:1}.row button{width:auto}
.err{color:#dc2626}.ok{color:#16a34a}
.rq{border-top:1px solid #8883;padding:8px 0;font-size:.92em;word-wrap:break-word}
.rp{background:var(--adm);border-radius:8px;padding:6px 8px;margin-top:4px}
</style></head><body><div class="wrap">
<h1>{{ title }}</h1>
<div class="hero"><div class="big">Now requesting r4</div><div class="free">It's free of cost</div></div>

<div class="card"><b>About</b><p>{{ about }}</p><p class="small"><b>Rules:</b> {{ rules }}</p>
  <p class="small">Privacy: for safety, this site records your IP address and what you submit. Everything is stored encrypted and is not shown to other visitors.</p></div>

<div class="card" id="tokcard">
  <b>Enter your token</b>
  <p class="small">No token yet? <a href="{{ token_url }}">Get one here</a>. It only takes a minute.</p>
  <input id="tokin" placeholder="Paste your token" autocomplete="off">
  <button onclick="useTok()">Continue</button>
  <div id="terr" class="err small"></div>
</div>

<div class="card" id="reqcard" hidden>
  <b>Put your link and request here</b>
  <input id="rlink" type="url" placeholder="Paste your link (https://...)" maxlength="500">
  <textarea id="rtext" placeholder="Your request" maxlength="500"></textarea>
  <label class="c"><input type="checkbox" id="rok"><span>I agree my request and IP address are stored for safety.</span></label>
  <button onclick="sendReq()">Submit request</button>
  <div id="rmsg" class="small"></div>
</div>

<div class="card" id="mine" hidden><b>Your requests &amp; replies</b><div id="mylist"></div></div>

<div class="card" id="chatcard" hidden>
  <b>Chat</b>
  <div id="log"></div>
  <div class="row"><input id="msg" placeholder="Type a message" maxlength="500"><button onclick="send()">Send</button></div>
  <div id="cmsg" class="small err"></div>
</div>

<div class="small" style="text-align:center"><a href="#" id="forget" hidden onclick="forget();return false">Use a different token</a></div>
<footer>@LIGHTSABER<br>all rights reserved</footer>
</div>
<script>
const $ = id => document.getElementById(id);
const H = {'Content-Type': 'application/json'};
let tok = '';
try { tok = localStorage.getItem('tok') || ''; } catch(e) {}
let last = 0, started = false;

function show(on){ $('tokcard').hidden = on; ['reqcard', 'chatcard', 'forget'].forEach(i => $(i).hidden = !on); }
async function check(t){ const r = await fetch('/my_requests?token=' + encodeURIComponent(t)); return r.ok; }
function start(){ show(true); if(!started){ started = true; poll(); pollReqs(); } }
function forget(){ try { localStorage.removeItem('tok'); } catch(e) {} location.reload(); }

async function useTok(){
  const t = $('tokin').value.trim(); $('terr').textContent = '';
  if(!t){ $('terr').textContent = 'Paste your token first.'; return; }
  if(!(await check(t))){ $('terr').textContent = "That token wasn't recognised. Check it, or get a new one."; return; }
  tok = t; try { localStorage.setItem('tok', t); } catch(e) {}
  start();
}

function add(m){
  const d = document.createElement('div');
  d.className = 'm' + (m.admin ? ' adm' : (m.mine ? ' me' : ''));
  const b = document.createElement('b'); b.textContent = m.admin ? m.name + ' (owner)' : m.name;
  const t = document.createElement('span'); t.textContent = m.text;
  d.append(b, t); $('log').append(d);
}
async function poll(){
  try{
    const r = await fetch('/messages?since=' + last + '&token=' + encodeURIComponent(tok));
    if(r.ok){ const d = await r.json(); const log = $('log');
      const atEnd = log.scrollTop + log.clientHeight >= log.scrollHeight - 40;
      d.messages.forEach(m => { add(m); last = Math.max(last, m.id); });
      if(d.messages.length && atEnd) log.scrollTop = log.scrollHeight; }
  }catch(e){}
  setTimeout(poll, 2000);
}
async function pollReqs(){
  try{
    const r = await fetch('/my_requests?token=' + encodeURIComponent(tok));
    if(r.ok){ const d = await r.json(); const box = $('mylist'); box.replaceChildren();
      $('mine').hidden = !d.requests.length;
      d.requests.forEach(q => {
        const div = document.createElement('div'); div.className = 'rq';
        const a = document.createElement('div'); a.textContent = q.text;
        const l = document.createElement('div'); l.className = 'small'; l.textContent = q.link;
        const rp = document.createElement('div');
        if(q.reply){ rp.className = 'rp'; rp.textContent = 'Reply: ' + q.reply; }
        else { rp.className = 'small'; rp.textContent = 'Waiting for a reply...'; }
        div.append(a, l, rp); box.append(div); }); }
  }catch(e){}
  setTimeout(pollReqs, 5000);
}
async function send(){
  const text = $('msg').value.trim(); if(!text) return;
  $('cmsg').textContent = '';
  const r = await fetch('/send', {method:'POST', headers:H, body: JSON.stringify({token: tok, text})});
  if(r.ok){ $('msg').value = ''; } else { $('cmsg').textContent = (await r.json()).error; }
}
async function sendReq(){
  const m = $('rmsg');
  const r = await fetch('/request', {method:'POST', headers:H, body: JSON.stringify({token: tok,
    link: $('rlink').value, text: $('rtext').value, consent: $('rok').checked})});
  const d = await r.json();
  m.className = 'small ' + (r.ok ? 'ok' : 'err');
  m.textContent = r.ok ? 'Request received. The reply will appear under "Your requests & replies".' : d.error;
  if(r.ok){ $('rlink').value = ''; $('rtext').value = ''; }
}
$('msg').addEventListener('keydown', e => { if(e.key === 'Enter') send(); });
$('tokin').addEventListener('keydown', e => { if(e.key === 'Enter') useTok(); });
(async () => {
  if(!tok){ show(false); return; }
  if(await check(tok)){ start(); }
  else { try { localStorage.removeItem('tok'); } catch(e) {} tok = ''; show(false);
         $('terr').textContent = 'Your saved token no longer works. Paste a new one.'; }
})();
</script></body></html>"""

ADMIN = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Admin</title>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--card:#f3f4f6;--accent:#2563eb}
@media(prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--card:#1f2125;--accent:#60a5fa}}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;background:var(--bg);color:var(--fg)}
.wrap{max-width:640px;margin:0 auto;padding:16px}.card{background:var(--card);border-radius:12px;padding:14px;margin:12px 0}
input,button,textarea{font:inherit;padding:10px;border-radius:8px;border:1px solid #8885;width:100%;margin:4px 0;background:var(--bg);color:var(--fg)}
textarea{min-height:60px}button{background:var(--accent);color:#fff;border:0;cursor:pointer;width:auto}
.small{font-size:.82em;opacity:.75;word-wrap:break-word}.done{opacity:.6}
#log{max-height:35vh;overflow-y:auto}.m{padding:3px 0;border-bottom:1px solid #8883;word-wrap:break-word}
a{color:var(--accent)}
</style></head><body><div class="wrap">
<h2>Admin</h2>
<div id="login" class="card" {% if authed %}hidden{% endif %}>
  <input id="pw" type="password" placeholder="Admin password">
  <button onclick="login()">Log in</button><div id="lerr" class="small"></div>
</div>
<div id="dash" {% if not authed %}hidden{% endif %}>
  <div class="small" id="stats"></div>
  <div class="card"><b>Requests</b><div id="reqs"></div></div>
  <div class="card"><b>People with tokens</b><div id="people"></div></div>
  <div class="card"><b>Chat</b><div id="log"></div>
    <input id="say" placeholder="Send a message as Admin"><button onclick="say()">Send to chat</button></div>
</div></div>
<script>
const $ = id => document.getElementById(id);
const H = {'Content-Type': 'application/json'};
function el(tag, cls, text){ const e = document.createElement(tag); if(cls) e.className = cls; if(text !== undefined) e.textContent = text; return e; }
async function login(){
  const r = await fetch('/admin/login', {method:'POST', headers:H, body: JSON.stringify({password: $('pw').value})});
  if(r.ok){ $('login').hidden = true; $('dash').hidden = false; refresh(); }
  else { $('lerr').textContent = (await r.json()).error; }
}
let typing = false;
async function refresh(){
  if($('dash').hidden) return;
  try{
    const r = await fetch('/admin/data'); if(r.status === 403){ location.reload(); return; }
    const d = await r.json();
    $('stats').textContent = d.people.length + ' people, ' + d.requests.length + ' requests';
    const log = $('log'); log.replaceChildren();
    d.messages.slice(-40).forEach(m => log.append(el('div', 'm', m.name + ': ' + m.text + (m.admin ? '' : '  [' + m.ip + ']'))));
    log.scrollTop = log.scrollHeight;
    const pbox = $('people'); pbox.replaceChildren();
    d.people.forEach(p => {
      const c = el('div', 'card');
      c.append(el('div', '', p.gmail + ' | ' + p.work));
      c.append(el('div', 'small', 'joined ' + p.created + ' | IP ' + p.ip));
      const b = el('button', '', 'Remove (token stops working)');
      b.onclick = async () => { if(!confirm("Remove this person? Their token will stop working.")) return;
        await fetch('/admin/remove', {method:'POST', headers:H, body: JSON.stringify({tid: p.tid})}); refresh(); };
      c.append(b); pbox.append(c); });
    if(!typing){
      const box = $('reqs'); box.replaceChildren();
      d.requests.slice().reverse().forEach(q => {
        const c = el('div', 'card' + (q.reply ? ' done' : ''));
        c.append(el('div', '', q.text));
        const a = el('a', '', q.link); a.href = q.link; a.target = '_blank'; a.rel = 'noopener noreferrer';
        c.append(a);
        c.append(el('div', 'small', q.time + ' | ' + q.gmail + ' | ' + q.work + ' | IP ' + q.ip));
        if(q.reply) c.append(el('div', 'small', 'Your reply: ' + q.reply));
        const t = el('textarea'); t.placeholder = q.reply ? 'Edit reply' : 'Write a reply';
        t.addEventListener('focus', () => typing = true); t.addEventListener('blur', () => typing = false);
        const b = el('button', '', 'Send reply');
        b.onclick = async () => { if(!t.value.trim()) return;
          await fetch('/admin/reply', {method:'POST', headers:H, body: JSON.stringify({id: q.id, text: t.value})});
          typing = false; refresh(); };
        c.append(t, b); box.append(c); });
    }
  }catch(e){}
}
async function say(){
  const t = $('say').value.trim(); if(!t) return; $('say').value = '';
  await fetch('/admin/say', {method:'POST', headers:H, body: JSON.stringify({text: t})}); refresh();
}
$('pw').addEventListener('keydown', e => { if(e.key === 'Enter') login(); });
$('say').addEventListener('keydown', e => { if(e.key === 'Enter') say(); });
refresh(); setInterval(refresh, 5000);
</script></body></html>"""


def who(token):
    """Return the token's fingerprint if the token is valid, else None."""
    if not isinstance(token, str) or not token.strip():
        return None
    tid = vault.token_id(token.strip())
    return tid if tid in TOKENS else None


def client_ip():
    if BEHIND_PROXY:
        real = request.headers.get("CF-Connecting-IP", "").strip()
        if real:
            return real
        fwd = request.headers.get("X-Forwarded-For", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.remote_addr


def add_message(name, text, tid="", admin=False):
    with vault.lock:
        MSGS.append({"id": (MSGS[-1]["id"] + 1) if MSGS else 1, "name": name, "text": text,
                     "time": vault.now_s(), "admin": admin, "tid": tid, "ip": client_ip()})
        del MSGS[:-1000]
        vault.save("messages")


def is_admin():
    return request.cookies.get("adm") in ADMIN_TOKENS


@app.get("/background.jpg")
def background():
    return send_from_directory(vault.BASE_DIR, "background.jpg")


@app.get("/")
def index():
    return render_template_string(PAGE, title=SITE_TITLE, about=ABOUT_TEXT, rules=RULES_TEXT,
                                  token_url=TOKEN_SITE_URL)


@app.post("/request")
def make_request():
    d = request.get_json(silent=True) or {}
    tid = who(d.get("token"))
    if not tid:
        return jsonify(error="Token not recognised. Check it, or get one from the token site."), 403
    link = (d.get("link") or "").strip()[:500]
    text = (d.get("text") or "").strip()[:500]
    if not LINK_RE.match(link):
        return jsonify(error="Enter a valid link starting with http:// or https://"), 400
    if not text:
        return jsonify(error="Write your request."), 400
    if not d.get("consent"):
        return jsonify(error="Please tick the box to agree."), 400
    t = time.time()
    if t - RATE.get("r" + tid, 0) < 10:
        return jsonify(error="Please wait a few seconds before sending another."), 429
    RATE["r" + tid] = t
    with vault.lock:
        REQS.append({"id": (REQS[-1]["id"] + 1) if REQS else 1, "time": vault.now_s(), "ip": client_ip(),
                     "tid": tid, "link": link, "text": text, "reply": "", "reply_time": ""})
        vault.save("requests")
    return jsonify(ok=True)


@app.get("/my_requests")
def my_requests():
    tid = who(request.args.get("token"))
    if not tid:
        return jsonify(error="Token not recognised."), 403
    mine = [{"text": r["text"], "link": r["link"], "reply": r["reply"]} for r in REQS if r["tid"] == tid]
    return jsonify(requests=mine[::-1])


@app.get("/messages")
def get_messages():
    tid = who(request.args.get("token"))
    if not tid:
        return jsonify(error="Token not recognised."), 403
    since_s = request.args.get("since", "0")
    since = int(since_s) if since_s.isdigit() else 0
    out = [{"id": m["id"], "name": m["name"], "text": m["text"], "admin": m["admin"],
            "mine": bool(m["tid"]) and m["tid"] == tid} for m in MSGS if m["id"] > since]
    return jsonify(messages=out[-100:])


@app.post("/send")
def send():
    d = request.get_json(silent=True) or {}
    tid = who(d.get("token"))
    if not tid:
        return jsonify(error="Token not recognised."), 403
    text = (d.get("text") or "").strip()[:500]
    if not text:
        return jsonify(error="Type a message."), 400
    t = time.time()
    if t - RATE.get("s" + tid, 0) < 1:
        return jsonify(error="Slow down a little."), 429
    RATE["s" + tid] = t
    add_message("Member " + tid[:4], text, tid)
    return jsonify(ok=True)


# ---------------------------------------------------------------- admin
@app.get("/admin")
def admin_page():
    return render_template_string(ADMIN, authed=is_admin())


@app.post("/admin/login")
def admin_login():
    ip = client_ip()
    count, when = FAILS.get(ip, (0, 0))
    if count >= 5 and time.time() - when < 300:
        return jsonify(error="Too many attempts. Wait 5 minutes."), 429
    pw = (request.get_json(silent=True) or {}).get("password", "")
    if not secrets.compare_digest(pw.encode(), ADMIN_PASSWORD.encode()):
        FAILS[ip] = (count + 1, time.time())
        return jsonify(error="Wrong password."), 403
    FAILS.pop(ip, None)
    tok = secrets.token_urlsafe(24)
    ADMIN_TOKENS.add(tok)
    resp = jsonify(ok=True)
    resp.set_cookie("adm", tok, httponly=True, samesite="Lax", max_age=86400 * 7)
    return resp


@app.get("/admin/data")
def admin_data():
    if not is_admin():
        return jsonify(error="forbidden"), 403
    reqs = []
    for r in REQS:
        t = TOKENS.get(r["tid"], {})
        reqs.append({"id": r["id"], "time": r["time"], "ip": r["ip"], "link": r["link"], "text": r["text"],
                     "reply": r["reply"], "gmail": t.get("gmail", "(removed)"), "work": t.get("work", "")})
    people = [{"tid": k, "gmail": v["gmail"], "work": v["work"], "created": v["created"], "ip": v["ip"]}
              for k, v in TOKENS.items()]
    return jsonify(requests=reqs, messages=MSGS[-100:], people=people)


@app.post("/admin/reply")
def admin_reply():
    if not is_admin():
        return jsonify(error="forbidden"), 403
    d = request.get_json(silent=True) or {}
    text = (d.get("text") or "").strip()[:1000]
    with vault.lock:
        for r in REQS:
            if r["id"] == d.get("id"):
                r["reply"], r["reply_time"] = text, vault.now_s()
                vault.save("requests")
                return jsonify(ok=True)
    return jsonify(error="not found"), 404


@app.post("/admin/remove")
def admin_remove():
    if not is_admin():
        return jsonify(error="forbidden"), 403
    tid = (request.get_json(silent=True) or {}).get("tid", "")
    with vault.lock:
        if TOKENS.pop(tid, None) is None:
            return jsonify(error="not found"), 404
        vault.save("tokens")
    return jsonify(ok=True)


@app.post("/admin/say")
def admin_say():
    if not is_admin():
        return jsonify(error="forbidden"), 403
    text = ((request.get_json(silent=True) or {}).get("text") or "").strip()[:500]
    if not text:
        return jsonify(error="empty"), 400
    add_message("Admin", text, admin=True)
    return jsonify(ok=True)


@app.after_request
def headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    return resp

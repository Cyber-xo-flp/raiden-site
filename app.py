#!/usr/bin/env python3
"""Start both sites with one command. Keep vault.py, token_site.py, request_site.py and
background.jpg in the same folder.

    python app.py            starts the token site (8081) and the request site (8080)
    python app.py export     prints everything in the vault, decrypted

Background run:  VAULT_PASSPHRASE="your phrase" nohup python app.py &
"""
import json, sys, threading, time
import vault

if len(sys.argv) > 1 and sys.argv[1] == "export":
    vault.open_vault()
    print(json.dumps(vault.export_all(), indent=2, ensure_ascii=False))
    sys.exit(0)

vault.open_vault()
import token_site, request_site          # imported after the vault is open
from werkzeug.serving import make_server

if request_site.ADMIN_PASSWORD == "change-me-now":
    print("WARNING: change ADMIN_PASSWORD in request_site.py before sharing the site.")
servers = [make_server("0.0.0.0", token_site.PORT, token_site.app, threaded=True),
           make_server("0.0.0.0", request_site.PORT, request_site.app, threaded=True)]
for s in servers:
    threading.Thread(target=s.serve_forever, daemon=True).start()
print(f"Token site:   http://localhost:{token_site.PORT}")
print(f"Request site: http://localhost:{request_site.PORT}")
print(f"Admin:        http://localhost:{request_site.PORT}/admin")
try:
    while True:
        time.sleep(3600)
except KeyboardInterrupt:
    print("Stopped.")

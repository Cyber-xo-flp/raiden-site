"""Encrypted storage shared by both sites.
Everything is kept in ./vault as encrypted files. The key comes from your passphrase (scrypt)
and is never written to disk, so the folder is useless without the passphrase."""
import base64, getpass, hashlib, json, os, secrets, sys, threading, time
from cryptography.fernet import Fernet, InvalidToken

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_DIR = os.path.join(BASE_DIR, "vault")
lock = threading.RLock()
_fernet = None
_cache = {}


def open_vault(passphrase=None):
    global _fernet
    os.makedirs(VAULT_DIR, exist_ok=True)
    try:
        os.chmod(VAULT_DIR, 0o700)
    except OSError:
        pass
    salt_path = os.path.join(VAULT_DIR, "salt.bin")
    if os.path.exists(salt_path):
        with open(salt_path, "rb") as fh:
            salt = fh.read()
    else:
        salt = secrets.token_bytes(16)
        with open(salt_path, "wb") as fh:
            fh.write(salt)
    check_path = os.path.join(VAULT_DIR, "check.enc")
    is_new = not os.path.exists(check_path)
    if passphrase is None:
        passphrase = os.environ.get("VAULT_PASSPHRASE")
    if passphrase is None:
        passphrase = getpass.getpass("Vault passphrase: ")
        if is_new and getpass.getpass("Repeat passphrase (new vault): ") != passphrase:
            sys.exit("Passphrases don't match.")
    if not passphrase:
        sys.exit("Passphrase can't be empty.")
    key = hashlib.scrypt(passphrase.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    f = Fernet(base64.urlsafe_b64encode(key))
    if is_new:
        with open(check_path, "wb") as fh:
            fh.write(f.encrypt(b"ok"))
        print("New vault created. If you lose this passphrase, the data cannot be recovered.")
    else:
        with open(check_path, "rb") as fh:
            try:
                f.decrypt(fh.read())
            except InvalidToken:
                sys.exit("Wrong vault passphrase.")
    _fernet = f
    _cache.clear()


def data(name, default):
    """Return the decrypted object for `name`, loading it once. Edit it in place, then call save(name)."""
    with lock:
        if name not in _cache:
            path = os.path.join(VAULT_DIR, name + ".enc")
            if os.path.exists(path):
                with open(path, "rb") as fh:
                    _cache[name] = json.loads(_fernet.decrypt(fh.read()))
            else:
                _cache[name] = default
        return _cache[name]


def save(name):
    with lock:
        path = os.path.join(VAULT_DIR, name + ".enc")
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(_fernet.encrypt(json.dumps(_cache[name]).encode()))
        os.replace(tmp, path)


def export_all():
    out = {}
    for fn in sorted(os.listdir(VAULT_DIR)):
        if fn.endswith(".enc") and fn != "check.enc":
            out[fn[:-4]] = data(fn[:-4], None)
    return out


def token_id(token):
    """Tokens are never stored; only this SHA-256 fingerprint is."""
    return hashlib.sha256(token.encode()).hexdigest()


def now_s():
    return time.strftime("%Y-%m-%d %H:%M:%S")

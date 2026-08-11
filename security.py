"""
REBEL CROWN BOT HOSTING - Security Module
Token encryption (stdlib-first for Termux), file validation, path safety.
"""

import re
import os
import hmac
import hashlib
import base64
import secrets
import zipfile
from pathlib import Path

from config import (
    BASE_DIR, ADMIN_ID, is_admin, MAX_UPLOAD_SIZE, MAX_ZIP_SIZE,
    MAX_ZIP_EXTRACTED_SIZE, MAX_ZIP_FILE_COUNT,
)

_SALT = b"rebel_crown_hosting_v1_salt_2024"
_SECRET = os.getenv("SECRET_KEY", "rebel-crown-default-local-key-change-me").encode()

# Optional cryptography (Fernet) — used if installed; otherwise stdlib fallback
_FERNET = None
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    def _build_fernet():
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_SALT,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(_SECRET))
        return Fernet(key)

    _FERNET = _build_fernet()
except Exception:
    _FERNET = None


def _derive_key(nbytes: int = 32) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", _SECRET, _SALT, 100000, dklen=nbytes)


def _stdlib_encrypt(plaintext: str) -> str:
    """AES-free obfuscation with HMAC integrity (stdlib only, Termux-safe)."""
    key = _derive_key(32)
    data = plaintext.encode("utf-8")
    nonce = secrets.token_bytes(16)
    out = bytearray()
    counter = 0
    while len(out) < len(data):
        block = hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
        out.extend(block)
        counter += 1
    xored = bytes(a ^ b for a, b in zip(data, out[: len(data)]))
    tag = hmac.new(key, nonce + xored, hashlib.sha256).digest()[:16]
    payload = nonce + tag + xored
    return "stdlib:" + base64.urlsafe_b64encode(payload).decode("ascii")


def _stdlib_decrypt(token: str) -> str:
    if not token.startswith("stdlib:"):
        return ""
    try:
        raw = base64.urlsafe_b64decode(token[7:].encode("ascii"))
        nonce, tag, xored = raw[:16], raw[16:32], raw[32:]
        key = _derive_key(32)
        expect = hmac.new(key, nonce + xored, hashlib.sha256).digest()[:16]
        if not hmac.compare_digest(tag, expect):
            return ""
        out = bytearray()
        counter = 0
        while len(out) < len(xored):
            block = hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
            out.extend(block)
            counter += 1
        data = bytes(a ^ b for a, b in zip(xored, out[: len(xored)]))
        return data.decode("utf-8")
    except Exception:
        return ""


def encrypt_token(token: str) -> str:
    if not token:
        return ""
    if _FERNET is not None:
        try:
            return _FERNET.encrypt(token.encode()).decode()
        except Exception:
            pass
    return _stdlib_encrypt(token)


def decrypt_token(encrypted: str) -> str:
    if not encrypted:
        return ""
    if encrypted.startswith("stdlib:"):
        return _stdlib_decrypt(encrypted)
    if _FERNET is not None:
        try:
            return _FERNET.decrypt(encrypted.encode()).decode()
        except Exception:
            return ""
    return ""


def mask_token(token: str) -> str:
    if not token or len(token) < 12:
        return "***"
    return f"{token[:8]}...{token[-4:]}"


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name
    name = re.sub(r"[^\w.\-]", "_", name)
    name = name.lstrip(".")
    if not name.lower().endswith(".py"):
        name = name + ".py" if "." not in name else name
    if len(name) > 100:
        name = name[:96] + ".py"
    return name or "bot.py"


def validate_py_file(file_path: Path, max_size: int = MAX_UPLOAD_SIZE):
    if not file_path.exists():
        return False, "File does not exist"
    if not file_path.is_file():
        return False, "Not a regular file"
    size = file_path.stat().st_size
    if size == 0:
        return False, "File is empty"
    if size > max_size:
        return False, f"File too large (max {max_size // (1024 * 1024)} MB)"
    if file_path.suffix.lower() != ".py":
        return False, "Only .py files are allowed"
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(4096)
        if not content.strip():
            return False, "File appears empty"
        dangerous = [
            r"os\.system\s*\(\s*[\'\"]rm\s+-rf",
            r"shutil\.rmtree\s*\(\s*[\'\"]/",
            r"subprocess.*shell\s*=\s*True.*rm\s+-rf",
        ]
        for pat in dangerous:
            if re.search(pat, content, re.IGNORECASE):
                return False, "File contains potentially destructive code"
    except Exception as e:
        return False, f"Cannot read file: {e}"
    return True, "OK"


def sanitize_zip_filename(filename: str) -> str:
    """Sanitize an uploaded ZIP's own filename (not its members)."""
    name = Path(filename).name
    name = re.sub(r"[^\w.\-]", "_", name)
    name = name.lstrip(".")
    if not name.lower().endswith(".zip"):
        name = name + ".zip"
    if len(name) > 100:
        name = name[:96] + ".zip"
    return name or "bot.zip"


def validate_zip_file(file_path: Path, max_size: int = MAX_ZIP_SIZE):
    """Basic sanity checks on an uploaded ZIP before extraction."""
    if not file_path.exists():
        return False, "File does not exist"
    if not file_path.is_file():
        return False, "Not a regular file"
    size = file_path.stat().st_size
    if size == 0:
        return False, "File is empty"
    if size > max_size:
        return False, f"ZIP too large (max {max_size // (1024 * 1024)} MB)"
    if not zipfile.is_zipfile(file_path):
        return False, "Not a valid ZIP archive"
    try:
        with zipfile.ZipFile(file_path) as zf:
            bad = zf.testzip()
            if bad is not None:
                return False, f"Corrupt entry in ZIP: {bad}"
            infos = zf.infolist()
            if len(infos) == 0:
                return False, "ZIP archive is empty"
            if len(infos) > MAX_ZIP_FILE_COUNT:
                return False, "ZIP contains too many files"
            total_uncompressed = sum(i.file_size for i in infos)
            if total_uncompressed > MAX_ZIP_EXTRACTED_SIZE:
                return False, "ZIP extracted content is too large"
            for info in infos:
                name = info.filename
                # Reject path traversal / absolute paths / drive letters
                if name.startswith("/") or name.startswith("\\"):
                    return False, f"Unsafe path in ZIP: {name}"
                if re.match(r"^[A-Za-z]:", name):
                    return False, f"Unsafe absolute path in ZIP: {name}"
                if ".." in Path(name).parts:
                    return False, f"Path traversal detected in ZIP: {name}"
                # Reject symlinks (upper 16 bits of external_attr hold unix mode)
                mode = (info.external_attr >> 16) & 0xFFFF
                import stat as _stat
                if mode and _stat.S_ISLNK(mode):
                    return False, f"Symlinks are not allowed in ZIP: {name}"
    except Exception as e:
        return False, f"Cannot read ZIP: {e}"
    return True, "OK"


def safe_extract_zip(zip_path: Path, dest_dir: Path):
    """
    Extract a ZIP into dest_dir, refusing anything that would escape it.
    Assumes validate_zip_file() already passed. Returns (ok, message).
    """
    dest_dir = Path(dest_dir).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                name = info.filename
                if not name or name.endswith("/"):
                    # directory entry
                    target_dir = (dest_dir / name).resolve()
                    if not str(target_dir).startswith(str(dest_dir)):
                        return False, f"Path traversal detected in ZIP: {name}"
                    target_dir.mkdir(parents=True, exist_ok=True)
                    continue
                target = (dest_dir / name).resolve()
                if not str(target).startswith(str(dest_dir)):
                    return False, f"Path traversal detected in ZIP: {name}"
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    out.write(src.read())
        return True, "Extracted"
    except Exception as e:
        return False, f"Extraction failed: {e}"


# Preferred entry-file names, in priority order
_ENTRY_CANDIDATES = ["main.py", "bot.py", "app.py", "run.py", "start.py"]


def detect_entry_file(project_dir: Path):
    """
    Detect the main Python entry file inside an extracted project.
    Prefers main.py, then bot.py, then other common names, then falls
    back to the sole top-level .py file (if unambiguous).
    Returns a path RELATIVE to project_dir, or None if undetectable.
    """
    project_dir = Path(project_dir)

    # If the zip contained one wrapping folder with everything inside it,
    # look one level down as well.
    search_roots = [project_dir]
    top_entries = [p for p in project_dir.iterdir()] if project_dir.exists() else []
    if len(top_entries) == 1 and top_entries[0].is_dir():
        search_roots.append(top_entries[0])

    for root in search_roots:
        for candidate in _ENTRY_CANDIDATES:
            f = root / candidate
            if f.exists() and f.is_file():
                return str(f.relative_to(project_dir))

    for root in search_roots:
        py_files = [p for p in root.glob("*.py") if p.is_file()]
        if len(py_files) == 1:
            return str(py_files[0].relative_to(project_dir))

    return None


def safe_user_path(user_id: int, *parts) -> Path:
    base = Path(BASE_DIR) / "storage" / "users" / str(user_id)
    base = base.resolve()
    target = base.joinpath(*parts).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("Path traversal detected")
    return target


def check_ownership(user_id: int, bot: dict) -> bool:
    if not bot:
        return False
    return int(bot.get("user_id", 0)) == int(user_id) or is_admin(user_id)


def is_banned(user_id: int) -> bool:
    from database import get_user
    u = get_user(user_id)
    return bool(u and u.get("is_banned"))


def validate_bot_token_format(token: str) -> bool:
    if not token or not isinstance(token, str):
        return False
    token = token.strip()
    if re.match(r"^\d{8,12}:[A-Za-z0-9_-]{30,50}$", token):
        return True
    return False

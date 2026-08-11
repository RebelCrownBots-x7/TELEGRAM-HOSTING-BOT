"""
REBEL CROWN BOT HOSTING - Hosting Manager
Coordinates upload, approval, expiry, and storage layout.
"""

import shutil
from pathlib import Path
from datetime import datetime, timedelta

from config import USERS_DIR, UPLOADS_DIR, EXPORTS_DIR
from database import (
    create_hosting_request, get_request, update_request, create_bot_from_request,
    get_bot, update_bot, get_user, update_user, get_expired_bots, log_event,
    now_iso, get_setting, add_credits, update_uploaded_file_status, generate_id,
    add_hosting_history, get_bots_needing_reminder, notification_already_sent,
    record_notification, log_admin_action,
)
from security import (
    sanitize_filename, validate_py_file, encrypt_token, decrypt_token,
    safe_user_path, validate_bot_token_format,
    sanitize_zip_filename, validate_zip_file, safe_extract_zip, detect_entry_file,
)
from process_manager import start_bot, stop_bot, expire_bot

def save_uploaded_file(user_id: int, file_bytes: bytes, original_name: str) -> tuple[bool, str, Path]:
    """Save uploaded .py under user storage. Returns (ok, message, path)."""
    safe_name = sanitize_filename(original_name)
    user_bots = safe_user_path(user_id, "bots")
    user_bots.mkdir(parents=True, exist_ok=True)

    # Unique filename to avoid overwrite
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    unique = f"{ts}_{safe_name}"
    dest = user_bots / unique

    try:
        dest.write_bytes(file_bytes)
        ok, msg = validate_py_file(dest)
        if not ok:
            dest.unlink(missing_ok=True)
            return False, msg, None
        return True, "Saved", dest
    except Exception as e:
        return False, str(e), None


def save_uploaded_zip(user_id: int, file_bytes: bytes, original_name: str):
    """
    Save + safely extract an uploaded ZIP project under isolated per-upload
    storage. Returns (ok, message, project_dir, entry_relpath, original_zip_path).
    The original ZIP is preserved untouched (never deleted) alongside the
    extracted project, satisfying the "don't destroy the original" requirement.
    """
    safe_name = sanitize_zip_filename(original_name)
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    upload_id = generate_id("")
    # Each upload gets its own isolated folder so concurrent/older bots
    # never collide or get overwritten.
    upload_root = safe_user_path(user_id, "bots", f"{ts}_{upload_id}")
    upload_root.mkdir(parents=True, exist_ok=True)

    original_zip_path = upload_root / "__original__" / safe_name
    original_zip_path.parent.mkdir(parents=True, exist_ok=True)
    project_dir = upload_root / "project"
    project_dir.mkdir(parents=True, exist_ok=True)

    try:
        original_zip_path.write_bytes(file_bytes)
    except Exception as e:
        return False, str(e), None, None, None

    ok, msg = validate_zip_file(original_zip_path)
    if not ok:
        return False, msg, None, None, None

    ok, msg = safe_extract_zip(original_zip_path, project_dir)
    if not ok:
        return False, msg, None, None, None

    entry = detect_entry_file(project_dir)
    if not entry:
        return False, (
            "Could not detect a main Python entry file (main.py / bot.py / app.py). "
            "Please make sure your ZIP contains one at the top level."
        ), None, None, None

    return True, "Extracted", project_dir, entry, original_zip_path

def submit_hosting_request(user_id: int, file_path: Path, original_name: str,
                           bot_token: str, days: int = None,
                           file_type: str = "PY", entry_file: str = None) -> tuple[bool, str, dict]:
    if not validate_bot_token_format(bot_token):
        return False, "Invalid bot token format", None

    # Optional live validation via Telegram API
    try:
        import requests
        r = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10)
        data = r.json()
        if not data.get("ok"):
            return False, "Bot token is invalid (Telegram rejected it)", None
    except Exception:
        # Network issues in Termux - still accept format-valid tokens
        pass

    days = days or int(get_setting("default_hosting_days", 10) or 10)
    encrypted = encrypt_token(bot_token.strip())
    # For ZIP projects file_path is the extracted directory; store the
    # entry file's name as "filename" for readability, keep file_path=dir.
    filename = entry_file if (file_type == "ZIP" and entry_file) else file_path.name
    req = create_hosting_request(
        user_id=user_id,
        filename=filename,
        original_filename=original_name,
        file_path=str(file_path),
        bot_token_encrypted=encrypted,
        days=days,
        file_type=file_type,
        entry_file=entry_file,
    )
    log_event("INFO", "hosting", f"New request {req['request_id']} ({file_type})", user_id)
    return True, "Request submitted", req

def approve_request(request_id: str, days: int, admin_id: int) -> tuple[bool, str, dict]:
    req = get_request(request_id)
    if not req:
        return False, "Request not found", None
    if req["status"] != "WAITING":
        return False, f"Request is already {req['status']}", None

    max_days = int(get_setting("max_hosting_days", 365) or 365)
    days = max(1, min(days, max_days))

    bot = create_bot_from_request(req, days=days)
    # Mark free hosting if applicable
    user = get_user(req["user_id"])
    free_limit = int(get_setting("free_bot_limit", 1) or 1)
    if user and user.get("free_bots_used", 0) < free_limit and get_setting("free_hosting_enabled", "1") == "1":
        update_user(req["user_id"], free_bots_used=(user.get("free_bots_used") or 0) + 1,
                    free_hosting_used=1)

    # Start the bot
    ok, msg = start_bot(bot["bot_id"])
    if not ok:
        log_event("WARN", "hosting", f"Approved but start failed: {msg}", req["user_id"])
    else:
        update_bot(bot["bot_id"], status="RUNNING")

    update_uploaded_file_status(request_id, "APPROVED")
    add_hosting_history(bot["bot_id"], req["user_id"], "APPROVED", f"{days}d by admin {admin_id}")
    log_admin_action(admin_id, "approve_hosting", "request", request_id, f"{days}d bot={bot['bot_id']}")
    log_event("INFO", "hosting", f"Approved {request_id} for {days}d by admin {admin_id}", req["user_id"])
    return True, msg, get_bot(bot["bot_id"])

def reject_request(request_id: str, reason: str, admin_id: int) -> tuple[bool, str]:
    req = get_request(request_id)
    if not req:
        return False, "Request not found"
    if req["status"] != "WAITING":
        return False, f"Already {req['status']}"
    update_request(request_id, status="REJECTED", reject_reason=reason or "No reason provided")
    update_uploaded_file_status(request_id, "REJECTED")
    if req.get("bot_id"):
        add_hosting_history(req["bot_id"], req["user_id"], "REJECTED", reason or "")
    log_admin_action(admin_id, "reject_hosting", "request", request_id, reason or "")
    log_event("INFO", "hosting", f"Rejected {request_id}: {reason}", req["user_id"])
    return True, "Rejected"

def process_expiries(bot_instance=None):
    """Stop expired bots, send one-shot expiry notice, preserve all files/history."""
    expired = get_expired_bots()
    for bot in expired:
        expire_bot(bot["bot_id"])
        # One-shot expiry notification
        if not bot.get("reminder_expired_sent") and not notification_already_sent(
            bot["user_id"], bot["bot_id"], "expiry_expired"
        ):
            if bot_instance:
                try:
                    bot_instance.send_message(
                        bot["user_id"],
                        f"❌ <b>HOSTING EXPIRED</b>\n\n"
                        f"📂 Bot: <code>{bot.get('name') or bot['filename']}</code>\n"
                        f"🆔 Bot ID: <code>{bot['bot_id']}</code>\n\n"
                        f"Your hosting period has ended. The bot has been stopped.\n"
                        f"Files are preserved. Contact support or redeem credits to extend.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
            record_notification(bot["user_id"], bot["bot_id"], "expiry_expired", "Hosting expired")
            update_bot(bot["bot_id"], reminder_expired_sent=1)
        log_event("INFO", "hosting", f"Expired bot {bot['bot_id']}", bot["user_id"])
    return len(expired)


def process_expiry_reminders(bot_instance=None):
    """
    Send 3-day and 1-day pre-expiry reminders once each.
    Deduplicated via bots.reminder_* flags and notifications table.
    """
    if not bot_instance:
        return 0
    sent = 0
    now = datetime.utcnow()
    for bot in get_bots_needing_reminder():
        if bot.get("status") in ("EXPIRED", "DELETED"):
            continue
        exp_raw = bot.get("expiry_date")
        if not exp_raw:
            continue
        try:
            exp = datetime.fromisoformat(exp_raw)
        except Exception:
            continue
        remaining = exp - now
        if remaining.total_seconds() <= 0:
            continue  # handled by process_expiries
        days_left = remaining.total_seconds() / 86400.0
        name = bot.get("name") or bot.get("filename") or bot["bot_id"]
        uid = bot["user_id"]
        bid = bot["bot_id"]

        # 1 day reminder
        if days_left <= 1 and not bot.get("reminder_1d_sent"):
            if not notification_already_sent(uid, bid, "expiry_1d"):
                try:
                    bot_instance.send_message(
                        uid,
                        f"⏰ <b>HOSTING REMINDER</b>\n\n"
                        f"📂 Bot: <code>{name}</code>\n"
                        f"🆔 <code>{bid}</code>\n"
                        f"⏳ Less than <b>1 day</b> remaining.\n\n"
                        f"Extend hosting soon to avoid interruption.",
                        parse_mode="HTML",
                    )
                    sent += 1
                except Exception:
                    pass
                record_notification(uid, bid, "expiry_1d", "1 day remaining")
            update_bot(bid, reminder_1d_sent=1)

        # 3 day reminder
        elif days_left <= 3 and not bot.get("reminder_3d_sent"):
            if not notification_already_sent(uid, bid, "expiry_3d"):
                try:
                    bot_instance.send_message(
                        uid,
                        f"⏰ <b>HOSTING REMINDER</b>\n\n"
                        f"📂 Bot: <code>{name}</code>\n"
                        f"🆔 <code>{bid}</code>\n"
                        f"⏳ About <b>{int(days_left)} day(s)</b> remaining.\n\n"
                        f"Consider extending hosting before it expires.",
                        parse_mode="HTML",
                    )
                    sent += 1
                except Exception:
                    pass
                record_notification(uid, bid, "expiry_3d", "3 days remaining")
            update_bot(bid, reminder_3d_sent=1)
    return sent


def extend_hosting(bot_id: str, extra_days: int, admin_id: int = None) -> tuple[bool, str]:
    bot = get_bot(bot_id)
    if not bot:
        return False, "Bot not found"
    try:
        current = datetime.fromisoformat(bot["expiry_date"])
    except Exception:
        current = datetime.utcnow()
    if current < datetime.utcnow():
        current = datetime.utcnow()
    new_exp = (current + timedelta(days=extra_days)).isoformat()
    new_days = (bot.get("days") or 0) + extra_days
    status = bot["status"]
    if status == "EXPIRED":
        status = "STOPPED"
    # Reset reminder flags so they can fire again for the new window
    update_bot(
        bot_id, expiry_date=new_exp, days=new_days, status=status,
        reminder_3d_sent=0, reminder_1d_sent=0, reminder_expired_sent=0,
    )
    add_hosting_history(bot_id, bot["user_id"], "EXTENDED", f"+{extra_days} days → {new_exp[:19]}")
    if admin_id:
        log_admin_action(admin_id, "extend_hosting", "bot", bot_id, f"+{extra_days}d")
    return True, f"Extended to {new_exp}"

def delete_bot_data(bot_id: str, remove_files: bool = True) -> bool:
    bot = get_bot(bot_id)
    if not bot:
        return False
    stop_bot(bot_id, force=True)
    if remove_files:
        try:
            p = Path(bot["file_path"])
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists():
                p.unlink()
        except Exception:
            pass
        # runtime & logs left for admin inspection; can be cleaned separately
    update_bot(bot_id, status="DELETED")
    return True

def export_json(data: dict, name: str) -> Path:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORTS_DIR / f"{name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    import json
    # Never export plaintext tokens
    def sanitize(obj):
        if isinstance(obj, dict):
            return {k: ("***REDACTED***" if "token" in k.lower() else sanitize(v))
                    for k, v in obj.items()}
        if isinstance(obj, list):
            return [sanitize(i) for i in obj]
        return obj
    path.write_text(json.dumps(sanitize(data), indent=2, default=str), encoding="utf-8")
    return path

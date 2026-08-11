"""
DEPLOY BOT flow - upload .py OR .zip + token -> hosting request
                    -> auto-accept OR manual admin approval
"""

from pathlib import Path

from telebot import types
from config import is_admin, ADMIN_ID, ADMIN_IDS, MAX_UPLOAD_SIZE, MAX_ZIP_SIZE
from database import ensure_user, get_user, log_event, get_setting
from security import is_banned, validate_bot_token_format
from hosting_manager import save_uploaded_file, save_uploaded_zip, submit_hosting_request, approve_request
from utils import (
    support_inline, format_request_card, admin_request_actions, user_main_keyboard,
    is_reserved_text, register_state_clearer, KB, IKB, BTN_UPLOAD_FILE, btn_text,
)

# user_id -> temporary state
_deploy_state = {}

def _clear(uid):
    if uid in _deploy_state:
        _deploy_state.pop(uid, None)
        return True
    return False

def _notify_admins_new_file(bot, uid: int, doc, file_type: str, tracking_id: str):
    """
    Section 8 requirement: ADMIN MUST RECEIVE EVERY UPLOAD, immediately,
    even when auto_accept_hosting is enabled. This forwards the ORIGINAL
    file straight after it is received/validated - before the hosting
    request even exists.
    """
    user = get_user(uid)
    uname = f"@{user['username']}" if user and user.get("username") else "-"
    caption = (
        "\u256d\u2501\u2501\u2501\ud835\udcbb \ud83d\udcc2\ud835\udcbc \ufe63\u2501\u2501\u2501\u256e\n"
        "       <b>NEW FILE</b>\n"
        "\u2570\u2501\u2501\u2501\ud835\udcbb \ud83d\udcc2\ud835\udcbc \ufe63\u2501\u2501\u2501\u256f\n\n"
        f"\ud83d\udc64 User: <code>{uname}</code>\n"
        f"\ud83c\udd94 User ID: <code>{uid}</code>\n"
        f"\ud83d\udcc2 File: <code>{doc.file_name}</code>\n"
        f"\ud83d\udce6 Type: <b>{file_type}</b>\n"
        f"\ud83c\udd94 Tracking: <code>{tracking_id}</code>"
    )
    for admin_id in ADMIN_IDS:
        try:
            file_info = bot.get_file(doc.file_id)
            file_bytes = bot.download_file(file_info.file_path)
            bot.send_document(
                int(admin_id),
                (doc.file_name, file_bytes),
                caption=caption,
                parse_mode="HTML",
            )
        except Exception as e:
            log_event("ERROR", "deploy", f"Admin file forward failed ({admin_id}): {e}")


def register(bot):
    register_state_clearer(_clear)

    @bot.message_handler(func=lambda m: m.text in (BTN_UPLOAD_FILE, "🟢 🚀 DEPLOY BOT"))
    def start_deploy(message):
        uid = message.from_user.id
        if is_banned(uid):
            bot.reply_to(message, "🚫 You are banned from using this service.")
            return
        ensure_user(uid, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
        _deploy_state[uid] = {"step": "await_file"}
        bot.send_message(
            message.chat.id,
            f"📤 <b>{btn_text('Upload File')}</b>\n\n"
            "📂 Upload your Telegram bot.\n\n"
            "Supported files:\n"
            "✅ <code>.py</code> (single script)\n"
            "✅ <code>.zip</code> (full project)\n\n"
            "⚠️ Max size: {} MB (.py) / {} MB (.zip)\n\n"
            "Send the file now, or /cancel to abort.".format(
                MAX_UPLOAD_SIZE // (1024 * 1024), MAX_ZIP_SIZE // (1024 * 1024)
            ),
            parse_mode="HTML",
            reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                KB("/cancel")
            ),
        )

    @bot.message_handler(content_types=["document"], func=lambda m: _deploy_state.get(m.from_user.id, {}).get("step") == "await_file")
    def receive_file(message):
        uid = message.from_user.id
        doc = message.document
        if not doc:
            bot.reply_to(message, "Please send a document.")
            return

        name_lower = (doc.file_name or "").lower()
        is_py = name_lower.endswith(".py")
        is_zip = name_lower.endswith(".zip")
        if not (is_py or is_zip):
            bot.reply_to(message, "❌ Only <code>.py</code> or <code>.zip</code> files are allowed.", parse_mode="HTML")
            return

        max_size = MAX_ZIP_SIZE if is_zip else MAX_UPLOAD_SIZE
        if doc.file_size and doc.file_size > max_size:
            bot.reply_to(message, f"❌ File too large (max {max_size // (1024*1024)} MB).")
            return

        try:
            file_info = bot.get_file(doc.file_id)
            file_bytes = bot.download_file(file_info.file_path)
        except Exception as e:
            bot.reply_to(message, f"❌ Download failed: {e}")
            return

        if is_zip:
            ok, msg, project_dir, entry, original_zip_path = save_uploaded_zip(uid, file_bytes, doc.file_name or "bot.zip")
            if not ok:
                bot.reply_to(message, f"❌ {msg}")
                return
            file_type = "ZIP"
            state = {
                "step": "await_token",
                "file_path": str(project_dir),
                "original_name": doc.file_name or "bot.zip",
                "file_type": file_type,
                "entry_file": entry,
            }
            tracking_id = project_dir.parent.name
            preview = f"🤖 Detected entry file: <code>{entry}</code>\n\n"
        else:
            ok, msg, path = save_uploaded_file(uid, file_bytes, doc.file_name or "bot.py")
            if not ok:
                bot.reply_to(message, f"❌ {msg}")
                return
            file_type = "PY"
            state = {
                "step": "await_token",
                "file_path": str(path),
                "original_name": doc.file_name or path.name,
                "file_type": file_type,
                "entry_file": None,
            }
            tracking_id = path.stem
            preview = ""

        _deploy_state[uid] = state

        # Admin ALWAYS receives the original upload immediately, regardless
        # of auto-accept / manual approval mode.
        _notify_admins_new_file(bot, uid, doc, file_type, tracking_id)

        bot.send_message(
            message.chat.id,
            f"✅ File received: <code>{doc.file_name}</code>\n\n"
            f"{preview}"
            f"🤖 Now send your <b>Telegram Bot Token</b>.\n\n"
            f"You can get it from @BotFather.\n"
            f"Send /cancel to abort.",
            parse_mode="HTML",
        )

    @bot.message_handler(
        func=lambda m: _deploy_state.get(m.from_user.id, {}).get("step") == "await_token"
        and m.text and not is_reserved_text(m.text)
    )
    def receive_token(message):
        uid = message.from_user.id
        text = (message.text or "").strip()
        if text.lower() in ("/cancel", "cancel"):
            _deploy_state.pop(uid, None)
            bot.send_message(message.chat.id, "Cancelled.", reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)))
            return

        if not validate_bot_token_format(text):
            bot.reply_to(message, "❌ Invalid token format. Expected like: <code>123456789:AAH...</code>\nTry again or /cancel.", parse_mode="HTML")
            return

        state = _deploy_state.get(uid, {})
        file_path = state.get("file_path")
        original = state.get("original_name", "bot.py")
        file_type = state.get("file_type", "PY")
        entry_file = state.get("entry_file")
        if not file_path:
            bot.reply_to(message, f"Session expired. Start again with {BTN_UPLOAD_FILE}.")
            _deploy_state.pop(uid, None)
            return

        ok, msg, req = submit_hosting_request(
            uid, Path(file_path), original, text,
            file_type=file_type, entry_file=entry_file,
        )
        _deploy_state.pop(uid, None)

        if not ok:
            bot.send_message(message.chat.id, f"❌ {msg}", reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)))
            return

        auto_accept = get_setting("auto_accept_hosting", "0") == "1"

        if auto_accept:
            days = int(get_setting("default_hosting_days", 10) or 10)
            aok, amsg, bot_rec = approve_request(req["request_id"], days, admin_id=0)
            if aok:
                bot.send_message(
                    message.chat.id,
                    f"✅ <b>BOT HOSTING APPROVED (AUTO)</b>\n\n"
                    f"📂 File: <code>{original}</code>\n"
                    f"🆔 Request ID: <code>{req['request_id']}</code>\n"
                    f"🟢 Status: <b>RUNNING</b>\n"
                    f"⏱️ Hosting: <b>{days} Days</b>\n"
                    f"🆔 Bot ID: <code>{bot_rec['bot_id']}</code>\n\n"
                    f"📱 WhatsApp Support\n💬 Telegram Support",
                    parse_mode="HTML",
                    reply_markup=support_inline(),
                )
            else:
                bot.send_message(
                    message.chat.id,
                    f"⚠️ Auto-accepted but startup issue: {amsg}\nOur team has been notified.",
                    reply_markup=support_inline(),
                )
            bot.send_message(message.chat.id, "Back to menu:", reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)))

            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(
                        int(admin_id),
                        f"⚡ <b>AUTO-APPROVED</b>\n\n🆔 {req['request_id']}\n📂 {original}\n👤 {uid}\n{amsg}",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    log_event("ERROR", "deploy", f"Admin auto-approve notify failed ({admin_id}): {e}")
            return

        # Manual approval mode
        bot.send_message(
            message.chat.id,
            f"⏳ <b>HOSTING REQUEST RECEIVED</b>\n\n"
            f"Your hosting request has been successfully submitted.\n\n"
            f"📂 File: <code>{original}</code>\n"
            f"🆔 Request ID: <code>{req['request_id']}</code>\n"
            f"⏳ Status: <b>WAITING FOR ADMIN APPROVAL</b>\n\n"
            f"Our admin will manually review your bot before hosting.\n\n"
            f"📱 WhatsApp Support\n💬 Telegram Support",
            parse_mode="HTML",
            reply_markup=support_inline(),
        )
        bot.send_message(message.chat.id, "Back to menu:", reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)))

        # Notify every configured admin (not just the primary one)
        user = get_user(uid)
        card = format_request_card(req, user)
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(
                    int(admin_id),
                    card,
                    parse_mode="HTML",
                    reply_markup=admin_request_actions(req["request_id"]),
                )
            except Exception as e:
                log_event("ERROR", "deploy", f"Admin notify failed ({admin_id}): {e}")
        # Global /cancel is now handled centrally in handlers/user.py via
        # utils.clear_all_states(), so every flow (not just Deploy) is covered.

"""
Admin panel - full control
"""

import json
import secrets
from pathlib import Path
from datetime import datetime, timedelta

from telebot import types

from config import is_admin, ADMIN_ID, mask_token
from database import (
    get_dashboard_stats, get_waiting_requests, get_request, get_user, get_all_users,
    search_users, get_all_bots, get_bot, update_user, add_credits, get_setting,
    set_setting, get_all_settings, create_redeem_code, get_all_redeem_codes,
    get_recent_logs, count_users, log_event, now_iso, get_user_bots, get_credit_history,
    get_files, get_file, delete_file_record, log_admin_action, get_admin_audit,
    get_hosting_history,
)
from security import decrypt_token, check_ownership
from hosting_manager import approve_request, reject_request, export_json, extend_hosting, delete_bot_data
from process_manager import start_bot, stop_bot, restart_bot, get_bot_status, read_logs, check_and_auto_restart
from utils import (
    users_submenu_keyboard, NAV_BACK, NAV_HOME, NAV_USER_PANEL, NAV_NEXT, NAV_ADMIN_PANEL,
    admin_main_keyboard, user_main_keyboard, admin_request_actions,
    format_request_card, format_bot_card, support_inline, NAV_STATE,
    is_reserved_text, register_state_clearer, heading, KB, IKB,
    file_manager_categories_keyboard, file_card_actions, file_delete_confirm_keyboard,
    format_file_card,
    BTN_DASHBOARD, BTN_WAITING, BTN_ALL_BOTS, BTN_USERS, BTN_FILE_MANAGER,
    BTN_ADMIN_REDEEM, BTN_ADD_CREDITS, BTN_REMOVE_CREDITS, BTN_REFERRALS,
    BTN_HOSTING_TIME, BTN_BROADCAST, BTN_JSON_EXPORT, BTN_CUSTOMIZE, BTN_TERMUX,
    BTN_LOGS, BTN_AUTO_ACCEPT, BTN_SEARCH_USER, BTN_BAN_USER, BTN_UNBAN_USER,
    BTN_RESET_FREE, btn_text,
)

# Conversation states for admin
_admin_state = {}

def _guard(message):
    return is_admin(message.from_user.id)

def _clear(uid):
    if uid in _admin_state:
        _admin_state.pop(uid, None)
        return True
    return False

def register(bot):
    register_state_clearer(_clear)
    # ── Dashboard ──
    @bot.message_handler(func=lambda m: m.text in (BTN_DASHBOARD, "🔵 📊 DASHBOARD") and _guard(m))
    def dashboard(message):
        s = get_dashboard_stats()
        text = (
            f"{heading('Admin Dashboard', 1)}\n\n"
            f"👥 Total Users     : <b>{s['total_users']}</b>\n"
            f"🟢 Active Users    : <b>{s.get('active_users', 0)}</b>\n"
            f"🚫 Banned Users    : <b>{s.get('banned_users', 0)}</b>\n"
            f"🤖 Total Bots      : <b>{s['total_bots']}</b>\n"
            f"🟢 Running         : <b>{s['running_bots']}</b>\n"
            f"🔴 Stopped         : <b>{s['stopped_bots']}</b>\n"
            f"💥 Crashed         : <b>{s.get('crashed_bots', 0)}</b>\n"
            f"⚠️ Error            : <b>{s.get('error_bots', 0)}</b>\n"
            f"⚫ Expired         : <b>{s['expired_bots']}</b>\n"
            f"📡 Active Hosting  : <b>{s.get('active_hosting', 0)}</b>\n"
            f"⏳ Expiring Soon   : <b>{s.get('expiring_soon', 0)}</b>\n"
            f"⏳ Waiting         : <b>{s['waiting_requests']}</b>\n"
            f"📂 Uploaded Files  : <b>{s.get('uploaded_files', 0)}</b>\n"
            f"🔗 Referrals       : <b>{s['referral_count']}</b>\n"
            f"🎟️ Redeem Usage    : <b>{s.get('redeem_usage', 0)}</b>\n"
            f"💰 Credits Pool    : <b>{s['total_credits']}</b>\n"
            f"🎁 Free Host Users : <b>{s.get('free_hosting_users', 0)}</b>\n"
            f"🎫 Open Tickets    : <b>{s['open_tickets']}</b>"
        )
        bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=admin_main_keyboard(1))

    # ── Waiting requests ──
    @bot.message_handler(func=lambda m: m.text in (BTN_WAITING, "🔵 ⏳ WAITING REQUESTS") and _guard(m))
    def waiting(message):
        reqs = get_waiting_requests(30)
        if not reqs:
            bot.send_message(message.chat.id, "✅ No waiting requests.", reply_markup=admin_main_keyboard(1))
            return
        bot.send_message(message.chat.id, f"⏳ <b>WAITING</b> ({len(reqs)})", parse_mode="HTML")
        for r in reqs:
            user = get_user(r["user_id"])
            bot.send_message(
                message.chat.id,
                format_request_card(r, user),
                parse_mode="HTML",
                reply_markup=admin_request_actions(r["request_id"]),
            )

    # ── Request callbacks ──
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("adm_") and is_admin(c.from_user.id))
    def admin_req_cb(call):
        action, rid = call.data.split(":", 1)
        req = get_request(rid)
        if not req:
            bot.answer_callback_query(call.id, "Not found", show_alert=True)
            return

        if action == "adm_file":
            path = Path(req["file_path"])
            if path.exists():
                try:
                    with open(path, "rb") as f:
                        bot.send_document(call.message.chat.id, f, caption=f"📂 {req.get('original_filename')}\nID: {rid}")
                    bot.answer_callback_query(call.id, "Sent")
                except Exception as e:
                    bot.answer_callback_query(call.id, str(e)[:100], show_alert=True)
            else:
                bot.answer_callback_query(call.id, "File missing", show_alert=True)

        elif action == "adm_userreq":
            user = get_user(req["user_id"])
            bots = get_user_bots(req["user_id"])
            text = (
                f"👤 <b>USER INFO</b>\n"
                f"ID: <code>{req['user_id']}</code>\n"
                f"@{user.get('username') if user else '—'}\n"
                f"Credits: {user.get('credits') if user else 0}\n"
                f"Bots: {len(bots)}\n"
                f"Banned: {user.get('is_banned') if user else 0}"
            )
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, text, parse_mode="HTML")

        elif action == "adm_approve":
            _admin_state[call.from_user.id] = {"action": "approve_days", "request_id": rid}
            bot.answer_callback_query(call.id)
            bot.send_message(
                call.message.chat.id,
                f"✅ Approve <code>{rid}</code>\n\nEnter hosting duration in <b>days</b> (e.g. 10, 30, 60):",
                parse_mode="HTML",
            )

        elif action == "adm_reject":
            _admin_state[call.from_user.id] = {"action": "reject_reason", "request_id": rid}
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, f"❌ Reject <code>{rid}</code>\n\nSend rejection reason:", parse_mode="HTML")

        elif action == "adm_note":
            _admin_state[call.from_user.id] = {"action": "add_note", "request_id": rid}
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "📝 Send note text:")

    @bot.message_handler(
        func=lambda m: _guard(m) and m.from_user.id in _admin_state
        and _admin_state[m.from_user.id].get("action") != "reset_free"
        and m.text and not is_reserved_text(m.text)
    )
    def admin_state_handler(message):
        st = _admin_state.get(message.from_user.id)
        if not st:
            return
        action = st.get("action")
        text = (message.text or "").strip()

        if action == "approve_days":
            try:
                days = int(text)
                if days < 1:
                    raise ValueError()
            except ValueError:
                bot.reply_to(message, "Enter a positive integer (days).")
                return
            rid = st["request_id"]
            _admin_state.pop(message.from_user.id, None)
            ok, msg, bot_rec = approve_request(rid, days, message.from_user.id)
            if not ok:
                bot.reply_to(message, f"❌ {msg}")
                return
            req = get_request(rid)
            # Notify user
            try:
                bot.send_message(
                    req["user_id"],
                    f"✅ <b>BOT HOSTING APPROVED</b>\n\n"
                    f"📂 Bot: <code>{req.get('original_filename') or req['filename']}</code>\n"
                    f"🟢 Status: RUNNING\n"
                    f"⏱️ Hosting: <b>{days} Days</b>\n"
                    f"📅 Expires: <code>{bot_rec.get('expiry_date', '')[:19]}</code>\n"
                    f"🆔 Bot ID: <code>{bot_rec['bot_id']}</code>",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            bot.reply_to(message, f"✅ Approved for {days} days.\n{msg}", reply_markup=admin_main_keyboard(1))

        elif action == "reject_reason":
            rid = st["request_id"]
            _admin_state.pop(message.from_user.id, None)
            ok, msg = reject_request(rid, text, message.from_user.id)
            req = get_request(rid)
            try:
                bot.send_message(
                    req["user_id"],
                    f"❌ <b>HOSTING REQUEST REJECTED</b>\n\n📝 Reason: {text}",
                    parse_mode="HTML",
                    reply_markup=support_inline(),
                )
            except Exception:
                pass
            bot.reply_to(message, f"❌ Rejected.\n{msg}", reply_markup=admin_main_keyboard(1))

        elif action == "add_note":
            rid = st["request_id"]
            _admin_state.pop(message.from_user.id, None)
            from database import update_request
            update_request(rid, admin_note=text)
            bot.reply_to(message, "📝 Note saved.")

        elif action == "broadcast":
            _admin_state.pop(message.from_user.id, None)
            users = get_all_users(limit=2000)
            sent = failed = 0
            bot.reply_to(message, f"📢 Broadcasting to {len(users)} users...")
            for u in users:
                try:
                    bot.send_message(u["user_id"], text, parse_mode="HTML")
                    sent += 1
                except Exception:
                    failed += 1
                import time
                time.sleep(0.05)  # rate limit
            bot.send_message(message.chat.id, f"✅ Sent: {sent}\n❌ Failed: {failed}", reply_markup=admin_main_keyboard(1))

        elif action == "add_credits":
            parts = text.split()
            _admin_state.pop(message.from_user.id, None)
            if len(parts) < 2:
                bot.reply_to(message, "Usage: user_id amount")
                return
            try:
                target = int(parts[0])
                amount = int(parts[1])
            except ValueError:
                bot.reply_to(message, "Invalid numbers")
                return
            if amount == 0:
                bot.reply_to(message, "Amount cannot be zero.")
                return
            add_credits(target, amount, type_="admin", description="Admin adjustment", admin_id=message.from_user.id)
            sign = "+" if amount > 0 else ""
            log_admin_action(message.from_user.id, "add_credits", "user", str(target), f"{sign}{amount}")
            bot.reply_to(message, f"✅ Credits updated for {target}: {sign}{amount}")
            try:
                bot.send_message(target, f"💰 Your credits were updated by admin: {sign}{amount}")
            except Exception:
                pass

        elif action == "remove_credits":
            parts = text.split()
            _admin_state.pop(message.from_user.id, None)
            if len(parts) < 2:
                bot.reply_to(message, "Usage: user_id amount")
                return
            try:
                target = int(parts[0])
                amount = abs(int(parts[1]))
            except ValueError:
                bot.reply_to(message, "Invalid numbers")
                return
            if amount <= 0:
                bot.reply_to(message, "Amount must be positive.")
                return
            from database import remove_credits
            remove_credits(target, amount, description=f"Admin removed {amount}", admin_id=message.from_user.id)
            log_admin_action(message.from_user.id, "remove_credits", "user", str(target), f"-{amount}")
            bot.reply_to(message, f"✅ Removed {amount} credits from {target}")
            try:
                bot.send_message(target, f"💰 Admin removed {amount} credits from your balance.")
            except Exception:
                pass

        elif action == "create_redeem":
            # format: CODE type amount [max_uses] [per_user] [days_valid]
            _admin_state.pop(message.from_user.id, None)
            parts = text.split()
            if len(parts) < 3:
                bot.reply_to(message, "Format: CODE credits|hosting_days|premium AMOUNT [max_uses] [per_user] [days_valid]")
                return
            try:
                code, rtype = parts[0], parts[1].lower()
                amount = int(parts[2])
                max_uses = int(parts[3]) if len(parts) > 3 else 1
                per_user = int(parts[4]) if len(parts) > 4 else 1
                days_valid = int(parts[5]) if len(parts) > 5 else 30
                if rtype not in ("credits", "hosting_days", "premium"):
                    bot.reply_to(message, "reward type must be: credits | hosting_days | premium")
                    return
                exp = (datetime.utcnow() + timedelta(days=days_valid)).isoformat()
                create_redeem_code(code, rtype, amount, max_uses, per_user, exp, message.from_user.id)
                bot.reply_to(message, f"✅ Code <code>{code.upper()}</code> created.", parse_mode="HTML")
            except ValueError:
                bot.reply_to(message, "Invalid numbers in redeem command.")
            except Exception as e:
                bot.reply_to(message, f"Error: {e}")

        elif action == "search_user":
            _admin_state.pop(message.from_user.id, None)
            results = search_users(text, 20)
            if not results:
                bot.reply_to(message, "No users found.")
                return
            for u in results:
                bot.send_message(
                    message.chat.id,
                    f"👤 <code>{u['user_id']}</code> @{u.get('username') or '—'}\n"
                    f"Credits: {u.get('credits')} | Bots free used: {u.get('free_bots_used')} | Banned: {u.get('is_banned')}",
                    parse_mode="HTML",
                )

        elif action == "ban_user":
            _admin_state.pop(message.from_user.id, None)
            try:
                target = int(text.split()[0])
                reason = " ".join(text.split()[1:]) or "Banned by admin"
                update_user(target, is_banned=1, ban_reason=reason, banned_at=now_iso())
                log_admin_action(message.from_user.id, "ban_user", "user", str(target), reason)
                bot.reply_to(message, f"🚫 Banned {target}")
            except Exception as e:
                bot.reply_to(message, str(e))

        elif action == "unban_user":
            _admin_state.pop(message.from_user.id, None)
            try:
                target = int(text.strip())
                update_user(target, is_banned=0, ban_reason=None, unbanned_at=now_iso())
                log_admin_action(message.from_user.id, "unban_user", "user", str(target), "unbanned")
                bot.reply_to(message, f"✅ Unbanned {target}")
            except Exception as e:
                bot.reply_to(message, str(e))

        elif action == "set_setting":
            _admin_state.pop(message.from_user.id, None)
            if "=" not in text:
                bot.reply_to(message, "Format: key=value")
                return
            k, v = text.split("=", 1)
            set_setting(k.strip(), v.strip())
            bot.reply_to(message, f"💾 Saved <code>{k.strip()}</code> = <code>{v.strip()}</code>", parse_mode="HTML")

        elif action == "extend_bot":
            _admin_state.pop(message.from_user.id, None)
            parts = text.split()
            if len(parts) < 2:
                bot.reply_to(message, "Format: bot_id days")
                return
            bid, days = parts[0], int(parts[1])
            ok, msg = extend_hosting(bid, days)
            bot.reply_to(message, f"{'✅' if ok else '❌'} {msg}")

    # ── All bots ──
    @bot.message_handler(func=lambda m: m.text in (BTN_ALL_BOTS, "🟢 🤖 ALL BOTS") and _guard(m))
    def all_bots(message):
        bots = get_all_bots(50)
        if not bots:
            bot.send_message(message.chat.id, "No bots.", reply_markup=admin_main_keyboard(1))
            return
        bot.send_message(message.chat.id, f"🤖 <b>ALL BOTS</b> (showing {len(bots)})", parse_mode="HTML")
        for b in bots[:20]:
            bot.send_message(message.chat.id, format_bot_card(b) + f"\n👤 User: <code>{b['user_id']}</code>", parse_mode="HTML")

    # ── Users ──
    @bot.message_handler(func=lambda m: m.text in (BTN_USERS, "🟢 👥 USERS") and _guard(m))
    def users_menu(message):
        NAV_STATE[message.from_user.id] = {"panel": "admin_users", "page": 1}
        bot.send_message(
            message.chat.id,
            "👥 User management:",
            reply_markup=users_submenu_keyboard(),
        )

    @bot.message_handler(func=lambda m: m.text in (BTN_SEARCH_USER, "🔵 🔍 Search user") and _guard(m))
    def search_u(message):
        _admin_state[message.from_user.id] = {"action": "search_user"}
        bot.send_message(message.chat.id, "Send user ID or username fragment:")

    @bot.message_handler(func=lambda m: m.text in (BTN_BAN_USER, "🔴 🚫 Ban user") and _guard(m))
    def ban_u(message):
        _admin_state[message.from_user.id] = {"action": "ban_user"}
        bot.send_message(message.chat.id, "Send: user_id [reason]")

    @bot.message_handler(func=lambda m: m.text in (BTN_UNBAN_USER, "🟢 ✅ Unban user") and _guard(m))
    def unban_u(message):
        _admin_state[message.from_user.id] = {"action": "unban_user"}
        bot.send_message(message.chat.id, "Send user_id to unban:")

    @bot.message_handler(func=lambda m: m.text in (BTN_ADD_CREDITS, "🟢 💰 Add credits") and _guard(m))
    def add_cred(message):
        _admin_state[message.from_user.id] = {"action": "add_credits"}
        bot.send_message(message.chat.id, "Send: user_id amount")

    @bot.message_handler(func=lambda m: m.text in (BTN_RESET_FREE, "🔴 🔄 Reset free hosting") and _guard(m))
    def reset_free(message):
        _admin_state[message.from_user.id] = {"action": "search_user"}  # reuse search then manual
        bot.send_message(message.chat.id, "Search user first, then use customize or tell me user_id to reset.\nSend user_id now to reset free flags:")
        _admin_state[message.from_user.id] = {"action": "reset_free"}

    @bot.message_handler(
        func=lambda m: _admin_state.get(m.from_user.id, {}).get("action") == "reset_free" and _guard(m)
        and m.text and not is_reserved_text(m.text)
    )
    def do_reset_free(message):
        _admin_state.pop(message.from_user.id, None)
        try:
            uid = int(message.text.strip())
            update_user(uid, free_hosting_used=0, free_bots_used=0)
            bot.reply_to(message, f"✅ Free hosting reset for {uid}")
        except Exception as e:
            bot.reply_to(message, str(e))

    # ── File manager ──
    @bot.message_handler(func=lambda m: m.text in (BTN_FILE_MANAGER, "🟢 📂 FILE MANAGER") and _guard(m))
    def file_manager(message):
        bot.send_message(
            message.chat.id,
            f"{heading('File Manager', 2)}\n\nChoose a category:",
            parse_mode="HTML",
            reply_markup=file_manager_categories_keyboard(),
        )

    @bot.callback_query_handler(func=lambda c: c.data == "fm_back" and is_admin(c.from_user.id))
    def fm_back(call):
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            f"{heading('File Manager', 2)}\n\nChoose a category:",
            parse_mode="HTML",
            reply_markup=file_manager_categories_keyboard(),
        )

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("fm_cat:") and is_admin(c.from_user.id))
    def fm_category(call):
        _, cat = call.data.split(":", 1)
        bot.answer_callback_query(call.id)
        if cat == "RECENT":
            files = get_files(limit=15)
        elif cat in ("WAITING", "APPROVED", "REJECTED"):
            files = get_files(status=cat, limit=20)
        elif cat in ("PY", "ZIP"):
            files = get_files(file_type=cat, limit=20)
        else:
            files = []

        if not files:
            bot.send_message(call.message.chat.id, "📂 No files in this category.")
            return
        bot.send_message(call.message.chat.id, f"📂 <b>{cat}</b> ({len(files)})", parse_mode="HTML")
        for f in files:
            bot.send_message(
                call.message.chat.id,
                format_file_card(f),
                parse_mode="HTML",
                reply_markup=file_card_actions(f["file_id"]),
            )

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith(("fm_dl:", "fm_view:", "fm_user:", "fm_bot:", "fm_del:", "fm_delyes:", "fm_delno:")) and is_admin(c.from_user.id))
    def fm_file_actions(call):
        action, file_id = call.data.split(":", 1)
        f = get_file(file_id)
        if not f:
            bot.answer_callback_query(call.id, "File record not found (may already be deleted)", show_alert=True)
            return

        if action == "fm_dl":
            path = Path(f["file_path"])
            try:
                if path.is_dir():
                    # ZIP project — send the preserved original zip
                    original_dir = path.parent / "__original__"
                    zips = list(original_dir.glob("*.zip")) if original_dir.exists() else []
                    if not zips:
                        bot.answer_callback_query(call.id, "Original ZIP not found", show_alert=True)
                        return
                    with open(zips[0], "rb") as fh:
                        bot.send_document(call.message.chat.id, fh, caption=f"📦 {f.get('original_filename')}\nFile ID: {file_id}")
                elif path.exists():
                    with open(path, "rb") as fh:
                        bot.send_document(call.message.chat.id, fh, caption=f"📂 {f.get('original_filename')}\nFile ID: {file_id}")
                else:
                    bot.answer_callback_query(call.id, "File missing on disk", show_alert=True)
                    return
                bot.answer_callback_query(call.id, "Sent")
            except Exception as e:
                bot.answer_callback_query(call.id, str(e)[:100], show_alert=True)

        elif action == "fm_view":
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, format_file_card(f), parse_mode="HTML")

        elif action == "fm_user":
            user = get_user(f["user_id"])
            bots = get_user_bots(f["user_id"])
            text = (
                f"👤 <b>USER INFO</b>\n"
                f"ID: <code>{f['user_id']}</code>\n"
                f"@{user.get('username') if user else '—'}\n"
                f"Credits: {user.get('credits') if user else 0}\n"
                f"Bots: {len(bots)}\n"
                f"Banned: {user.get('is_banned') if user else 0}"
            )
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, text, parse_mode="HTML")

        elif action == "fm_bot":
            b = get_bot(f.get("bot_id")) if f.get("bot_id") else None
            bot.answer_callback_query(call.id)
            if not b:
                bot.send_message(call.message.chat.id, "🤖 No bot record yet (request not approved).")
            else:
                bot.send_message(call.message.chat.id, format_bot_card(b), parse_mode="HTML")

        elif action == "fm_del":
            bot.answer_callback_query(call.id)
            bot.send_message(
                call.message.chat.id,
                f"⚠️ Delete <code>{f.get('original_filename')}</code>? This removes the stored file(s) and its record.",
                parse_mode="HTML",
                reply_markup=file_delete_confirm_keyboard(file_id),
            )

        elif action == "fm_delyes":
            try:
                if f.get("bot_id"):
                    b = get_bot(f["bot_id"])
                    if b:
                        delete_bot_data(f["bot_id"], remove_files=True)
                path = Path(f["file_path"])
                import shutil
                if path.is_dir():
                    shutil.rmtree(path.parent, ignore_errors=True)  # removes project/ + __original__/
                elif path.exists():
                    path.unlink()
            except Exception:
                pass
            delete_file_record(file_id)
            bot.answer_callback_query(call.id, "Deleted")
            bot.send_message(call.message.chat.id, "🗑️ File deleted.")

        elif action == "fm_delno":
            bot.answer_callback_query(call.id, "Cancelled")

    # ── Auto Accept / Manual Approval toggle ──
    @bot.message_handler(func=lambda m: m.text in (BTN_AUTO_ACCEPT, "🔵 ⚡ AUTO ACCEPT") and _guard(m))
    def toggle_auto_accept(message):
        current = get_setting("auto_accept_hosting", "0")
        new_val = "0" if current == "1" else "1"
        set_setting("auto_accept_hosting", new_val)
        mode = "⚡ AUTO ACCEPT" if new_val == "1" else "🛡️ MANUAL APPROVAL"
        bot.send_message(
            message.chat.id,
            f"⚙️ Hosting approval mode is now: <b>{mode}</b>\n\n"
            f"Note: admin always still receives every uploaded file, "
            f"regardless of this setting.",
            parse_mode="HTML",
            reply_markup=admin_main_keyboard(3),
        )

    # ── Redeem admin ──
    @bot.message_handler(func=lambda m: m.text in (BTN_ADMIN_REDEEM, "🟢 🎟️ REDEEM") and _guard(m))
    def redeem_admin(message):
        codes = get_all_redeem_codes(15)
        lines = "\n".join(
            f"• <code>{c['code']}</code> {c['reward_type']}x{c['reward_amount']} "
            f"({c['used_count']}/{c['max_uses']}) {'✅' if c['is_active'] else '❌'}"
            for c in codes
        ) or "No codes."
        bot.send_message(message.chat.id, f"🎟️ <b>REDEEM CODES</b>\n\n{lines}", parse_mode="HTML")
        _admin_state[message.from_user.id] = {"action": "create_redeem"}
        bot.send_message(
            message.chat.id,
            "Create new:\n<code>CODE credits|hosting_days|premium AMOUNT [max_uses] [per_user] [days_valid]</code>\n"
            "Example: <code>WELCOME10 credits 10 100 1 30</code>",
            parse_mode="HTML",
        )

    # ── Credits shortcut ──
    @bot.message_handler(func=lambda m: m.text in (BTN_ADD_CREDITS, "🟢 💰 ADD CREDITS") and _guard(m))
    def credits_admin(message):
        _admin_state[message.from_user.id] = {"action": "add_credits"}
        bot.send_message(message.chat.id, "➕ Add credits.\nSend: user_id amount\n/cancel to abort.")

    @bot.message_handler(func=lambda m: m.text == BTN_REMOVE_CREDITS and _guard(m))
    def remove_credits_admin(message):
        _admin_state[message.from_user.id] = {"action": "remove_credits"}
        bot.send_message(message.chat.id, "➖ Remove credits.\nSend: user_id amount\n/cancel to abort.")

    # ── Referrals ──
    @bot.message_handler(func=lambda m: m.text in (BTN_REFERRALS, "🟢 🔗 REFERRALS") and _guard(m))
    def refs_admin(message):
        s = get_dashboard_stats()
        bot.send_message(
            message.chat.id,
            f"🔗 Total referral events: <b>{s['referral_count']}</b>\n"
            f"Reward setting: {get_setting('referral_reward_credits')} credits\n"
            f"Enabled: {get_setting('referral_enabled')}",
            parse_mode="HTML",
            reply_markup=admin_main_keyboard(1),
        )

    # ── Hosting time ──
    @bot.message_handler(func=lambda m: m.text in (BTN_HOSTING_TIME, "🟢 ⏱️ HOSTING TIME") and _guard(m))
    def hosting_time(message):
        _admin_state[message.from_user.id] = {"action": "extend_bot"}
        bot.send_message(message.chat.id, "Extend hosting.\nSend: bot_id days")

    # ── Broadcast ──
    @bot.message_handler(func=lambda m: m.text in (BTN_BROADCAST, "🟢 📢 BROADCAST") and _guard(m))
    def broadcast(message):
        _admin_state[message.from_user.id] = {"action": "broadcast"}
        bot.send_message(message.chat.id, "📢 Send the message to broadcast (HTML allowed):")

    # ── JSON Export ──
    @bot.message_handler(func=lambda m: m.text in (BTN_JSON_EXPORT, "🔵 📦 JSON EXPORT") and _guard(m))
    def json_export(message):
        from database import get_all_users, get_all_bots, get_waiting_requests, get_all_redeem_codes, get_all_settings
        data = {
            "exported_at": now_iso(),
            "users": get_all_users(2000),
            "bots": get_all_bots(2000),
            "waiting_requests": get_waiting_requests(500),
            "redeem_codes": get_all_redeem_codes(500),
            "settings": get_all_settings(),
            "stats": get_dashboard_stats(),
        }
        path = export_json(data, "full_export")
        try:
            with open(path, "rb") as f:
                bot.send_document(message.chat.id, f, caption="📦 Full data export (tokens redacted)")
        except Exception as e:
            bot.reply_to(message, f"Export saved at {path} but send failed: {e}")

    # ── Customize ──
    @bot.message_handler(func=lambda m: m.text in (BTN_CUSTOMIZE, "🟢 ⚙️ CUSTOMIZE") and _guard(m))
    def customize(message):
        settings = get_all_settings()
        lines = "\n".join(f"<code>{k}</code> = {v}" for k, v in sorted(settings.items())[:40])
        bot.send_message(
            message.chat.id,
            f"⚙️ <b>SETTINGS</b>\n\n{lines}\n\n"
            f"To edit, send: <code>key=value</code>",
            parse_mode="HTML",
        )
        _admin_state[message.from_user.id] = {"action": "set_setting"}

    # ── Termux status ──
    @bot.message_handler(func=lambda m: m.text in (BTN_TERMUX, "🔵 🖥️ TERMUX STATUS") and _guard(m))
    def termux_status(message):
        import platform
        import os
        from pathlib import Path as _P
        check_and_auto_restart()
        running = [get_bot_status(b["bot_id"]) for b in get_all_bots(100) if b.get("status") == "RUNNING"]
        # Termux-safe system info (no psutil)
        mem_line = "RAM: n/a"
        try:
            # Linux/Android /proc/meminfo
            info = {}
            for line in _P("/proc/meminfo").read_text().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    info[k.strip()] = v.strip()
            total_kb = int(info.get("MemTotal", "0").split()[0])
            avail_kb = int(info.get("MemAvailable", info.get("MemFree", "0")).split()[0])
            used_kb = max(0, total_kb - avail_kb)
            pct = round(100.0 * used_kb / total_kb, 1) if total_kb else 0
            mem_line = f"RAM: {pct}% used ({round(used_kb/1024)}MB / {round(total_kb/1024)}MB)"
        except Exception:
            pass
        disk_line = "Disk: n/a"
        try:
            st = os.statvfs("/")
            total = st.f_blocks * st.f_frsize
            free = st.f_bavail * st.f_frsize
            used = total - free
            pct = round(100.0 * used / total, 1) if total else 0
            disk_line = f"Disk: {pct}% used ({round(used/1e6)}MB / {round(total/1e6)}MB)"
        except Exception:
            pass
        cpus = os.cpu_count() or "?"
        text = (
            f"🖥️ <b>SYSTEM STATUS</b>\n\n"
            f"Platform: {platform.system()} {platform.release()}\n"
            f"Python: {platform.python_version()}\n"
            f"CPU count: {cpus}\n"
            f"{mem_line}\n"
            f"{disk_line}\n"
            f"Running processes tracked: {len(running)}"
        )
        bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=admin_main_keyboard(1))

    # ── Logs ──
    @bot.message_handler(func=lambda m: m.text in (BTN_LOGS, "🔵 📝 LOGS") and _guard(m))
    def logs_view(message):
        logs = get_recent_logs(30)
        lines = "\n".join(
            f"{l['created_at'][:16]} [{l['level']}] {l['module']}: {l['message'][:80]}"
            for l in logs
        ) or "No logs."
        bot.send_message(message.chat.id, f"📝 <b>RECENT LOGS</b>\n\n<pre>{lines[:3500]}</pre>", parse_mode="HTML")

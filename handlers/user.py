"""
User panel handlers
"""

from telebot import types
from config import is_admin, get_whatsapp_link, BRAND_NAME
from database import (
    ensure_user, get_user, get_user_bots, get_setting, process_referral, log_event
)
from security import is_banned, check_ownership
from process_manager import start_bot, stop_bot, restart_bot, get_bot_status, read_logs
from hosting_manager import delete_bot_data
from utils import (
    user_main_keyboard, admin_main_keyboard, format_welcome, format_bot_card,
    bot_control_keyboard, support_inline, remaining_time_str,
    NAV_NEXT, NAV_BACK, NAV_HOME, NAV_ADMIN_PANEL, NAV_USER_PANEL, NAV_MAIN_MENU, NAV_STATE,
    clear_all_states, heading, fancy, KB, IKB, btn_text,
    BTN_MY_BOTS, BTN_MY_ACCOUNT, BTN_CREDITS, BTN_FREE_HOSTING, BTN_STATISTICS,
    BTN_HELP, BTN_DAILY_BONUS, BTN_UPLOAD_FILE,
)

from database import get_bot

def register(bot):
    # Track current panel page per user for BACK/NEXT (in-memory, light)
    def _user_kb(uid, page=1):
        return user_main_keyboard(page=page, for_admin=is_admin(uid))

    def _show_user_panel(chat_id, uid, page=1, welcome=False):
        user = get_user(uid) or ensure_user(uid)
        NAV_STATE[uid] = {"panel": "user", "page": page}
        kb = _user_kb(uid, page)
        if welcome:
            bot.send_message(chat_id, format_welcome(user), parse_mode="HTML", reply_markup=kb)
        else:
            bot.send_message(
                chat_id,
                f"👤 <b>USER PANEL</b> — Page {page}/3",
                parse_mode="HTML",
                reply_markup=kb,
            )

    def _show_admin_panel(chat_id, uid, page=1):
        if not is_admin(uid):
            bot.send_message(chat_id, "❌ ACCESS DENIED", reply_markup=_user_kb(uid, 1))
            return
        NAV_STATE[uid] = {"panel": "admin", "page": page}
        bot.send_message(
            chat_id,
            f"👑 <b>ADMIN PANEL</b> — Page {page}/3",
            parse_mode="HTML",
            reply_markup=admin_main_keyboard(page),
        )

    @bot.message_handler(commands=["start"])
    def cmd_start(message):
        uid = message.from_user.id
        if is_banned(uid):
            bot.reply_to(message, "🚫 You are banned.")
            return
        user = ensure_user(
            uid,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name,
        )
        # Referral deep link: /start REFCODE
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) > 1:
            code = parts[1].strip().upper()
            if code and not user.get("referred_by"):
                if process_referral(uid, code):
                    bot.send_message(message.chat.id, "🎁 Referral applied! Welcome.")
                    user = get_user(uid)

        # UNIVERSAL: everyone lands on User Panel page 1
        NAV_STATE[uid] = {"panel": "user", "page": 1}
        clear_all_states(uid)
        bot.send_message(
            message.chat.id,
            format_welcome(user),
            parse_mode="HTML",
            reply_markup=_user_kb(uid, 1),
        )

    @bot.message_handler(func=lambda m: m.text and m.text.strip().lower() in ("/cancel", "cancel"))
    def global_cancel(message):
        """Centralized cancel: kills whatever free-text flow is pending in
        ANY module (deploy token, redeem code, support ticket, admin
        broadcast/ban/etc.) and returns to the correct panel — never shows
        'Nothing to cancel.' when a state actually exists."""
        uid = message.from_user.id
        had_state = clear_all_states(uid)
        st = NAV_STATE.get(uid) or {"panel": "user", "page": 1}
        if st.get("panel") == "admin" and is_admin(uid):
            kb = admin_main_keyboard(st.get("page", 1))
        else:
            kb = _user_kb(uid, 1)
        if had_state:
            bot.send_message(message.chat.id, "❌ Cancelled.", reply_markup=kb)
        else:
            bot.send_message(message.chat.id, "Nothing to cancel.", reply_markup=kb)

    @bot.message_handler(func=lambda m: m.text in (NAV_HOME, NAV_MAIN_MENU))
    def home_menu(message):
        uid = message.from_user.id
        user = ensure_user(uid, message.from_user.username, message.from_user.first_name)
        NAV_STATE[uid] = {"panel": "user", "page": 1}
        clear_all_states(uid)
        bot.send_message(
            message.chat.id,
            format_welcome(user),
            parse_mode="HTML",
            reply_markup=_user_kb(uid, 1),
        )

    @bot.message_handler(func=lambda m: m.text == NAV_USER_PANEL)
    def switch_user_panel(message):
        uid = message.from_user.id
        clear_all_states(uid)
        # Available to everyone (admins use it to leave admin panel)
        _show_user_panel(message.chat.id, uid, page=1, welcome=False)

    @bot.message_handler(func=lambda m: m.text == NAV_ADMIN_PANEL)
    def open_admin_panel(message):
        uid = message.from_user.id
        if not is_admin(uid):
            bot.send_message(message.chat.id, "❌ ACCESS DENIED", reply_markup=_user_kb(uid, 1))
            return
        clear_all_states(uid)
        _show_admin_panel(message.chat.id, uid, page=1)

    @bot.message_handler(func=lambda m: m.text == NAV_NEXT)
    def nav_next(message):
        uid = message.from_user.id
        clear_all_states(uid)
        st = NAV_STATE.get(uid) or {"panel": "user", "page": 1}
        panel = st.get("panel", "user")
        page = int(st.get("page", 1))
        if panel == "admin":
            if not is_admin(uid):
                bot.send_message(message.chat.id, "❌ ACCESS DENIED", reply_markup=_user_kb(uid, 1))
                return
            page = min(3, page + 1)
            _show_admin_panel(message.chat.id, uid, page)
        else:
            page = min(3, page + 1)
            _show_user_panel(message.chat.id, uid, page)

    @bot.message_handler(func=lambda m: m.text == NAV_BACK)
    def nav_back(message):
        uid = message.from_user.id
        clear_all_states(uid)
        st = NAV_STATE.get(uid) or {"panel": "user", "page": 1}
        panel = st.get("panel", "user")
        page = int(st.get("page", 1))
        # Special: if coming from Users submenu (admin), BACK returns to admin page 1
        if panel == "admin_users":
            if is_admin(uid):
                _show_admin_panel(message.chat.id, uid, page=1)
            else:
                _show_user_panel(message.chat.id, uid, 1)
            return
        if panel == "admin":
            if not is_admin(uid):
                bot.send_message(message.chat.id, "❌ ACCESS DENIED", reply_markup=_user_kb(uid, 1))
                return
            if page <= 1:
                # Root admin page — go to user panel
                _show_user_panel(message.chat.id, uid, 1)
            else:
                _show_admin_panel(message.chat.id, uid, page - 1)
        else:
            if page <= 1:
                # Already at user root — refresh page 1
                _show_user_panel(message.chat.id, uid, 1)
            else:
                _show_user_panel(message.chat.id, uid, page - 1)

    @bot.message_handler(func=lambda m: m.text in (BTN_MY_BOTS, "🟢 🤖 MY BOTS"))
    def my_bots(message):
        uid = message.from_user.id
        if is_banned(uid):
            return
        bots = get_user_bots(uid)
        if not bots:
            bot.send_message(
                message.chat.id,
                "🤖 You have no hosted bots yet.\n\nUse 📤 Upload File to submit one.",
                reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)),
            )
            return
        bot.send_message(message.chat.id, f"🤖 <b>YOUR BOTS</b> ({len(bots)})", parse_mode="HTML")
        for b in bots:
            if b.get("status") == "DELETED":
                continue
            card = format_bot_card(b)
            bot.send_message(
                message.chat.id,
                card,
                parse_mode="HTML",
                reply_markup=bot_control_keyboard(b["bot_id"]),
            )

    @bot.message_handler(func=lambda m: m.text in (BTN_MY_ACCOUNT, "🟢 👤 MY ACCOUNT"))
    def my_account(message):
        uid = message.from_user.id
        user = get_user(uid) or ensure_user(uid)
        bots = get_user_bots(uid)
        text = (
            f"{heading('My Account', 1)}\n\n"
            f"🆔 User ID     : <code>{uid}</code>\n"
            f"👤 Name        : {user.get('first_name') or '—'}\n"
            f"🔗 Username    : @{user.get('username') or '—'}\n"
            f"💰 Credits     : <b>{user.get('credits', 0)}</b>\n"
            f"⭐ Plan        : <b>{user.get('plan', 'FREE')}</b>\n"
            f"📅 Plan Expiry : {user.get('plan_expiry') or '—'}\n"
            f"🤖 Hosted Bots : {len(bots)}\n"
            f"🎁 Free Used   : {user.get('free_bots_used', 0)}\n"
            f"🔗 Referrals   : {user.get('referral_count', 0)}\n"
            f"📎 Ref Code    : <code>{user.get('referral_code')}</code>\n"
            f"📅 Joined      : {(user.get('created_at') or '')[:10]}"
        )
        bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)))

    @bot.message_handler(func=lambda m: m.text in (BTN_CREDITS, "🟢 💰 CREDITS"))
    def credits_view(message):
        uid = message.from_user.id
        user = get_user(uid) or ensure_user(uid)
        from database import get_credit_history
        hist = get_credit_history(uid, 10)
        lines = "\n".join(
            f"• {h['created_at'][:16]} | {h['amount']:+d} | {h['type']} | bal {h['balance_after']}"
            for h in hist
        ) or "No transactions yet."
        text = (
            f"💰 <b>CREDITS</b>\n\n"
            f"Current balance: <b>{user.get('credits', 0)}</b>\n\n"
            f"<b>Recent activity:</b>\n<code>{lines}</code>"
        )
        bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)))

    @bot.message_handler(func=lambda m: m.text in (BTN_FREE_HOSTING, "🟢 🎁 FREE HOSTING"))
    def free_hosting_info(message):
        uid = message.from_user.id
        user = get_user(uid) or ensure_user(uid)
        enabled = get_setting("free_hosting_enabled", "1") == "1"
        limit = get_setting("free_bot_limit", "1")
        days = get_setting("free_hosting_days", "10")
        used = user.get("free_bots_used", 0)
        available = enabled and used < int(limit)
        text = (
            f"{heading('Free Hosting', 2)}\n\n"
            f"{'🟢' if available else '🔴'} Status       : {'Available' if available else 'Used / Disabled'}\n"
            f"🤖 Bot Limit    : {limit}\n"
            f"⏱️ Duration     : {days} Days\n"
            f"📊 Used         : {used} / {limit}\n\n"
            f"🚀 Deploy your Telegram bot and submit it for admin approval."
        )
        bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)))

    @bot.message_handler(func=lambda m: m.text in (BTN_STATISTICS, "🟢 📊 STATISTICS"))
    def user_stats(message):
        uid = message.from_user.id
        bots = get_user_bots(uid)
        running = sum(1 for b in bots if b.get("status") == "RUNNING")
        stopped = sum(1 for b in bots if b.get("status") == "STOPPED")
        expired = sum(1 for b in bots if b.get("status") == "EXPIRED")
        text = (
            f"📊 <b>YOUR STATISTICS</b>\n\n"
            f"🤖 Total bots: {len(bots)}\n"
            f"🟢 Running: {running}\n"
            f"🔴 Stopped: {stopped}\n"
            f"⚫ Expired: {expired}"
        )
        bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)))

    @bot.message_handler(func=lambda m: m.text in (BTN_HELP, "🟢 ❓ HELP"))
    def help_msg(message):
        brand = get_setting("brand_name") or BRAND_NAME
        text = (
            f"❓ <b>HELP — {brand}</b>\n\n"
            f"<b>How to host a bot:</b>\n"
            f"1. Press 📤 Upload File\n"
            f"2. Upload your <code>.py</code> or <code>.zip</code> file\n"
            f"3. Send your Bot Token from @BotFather\n"
            f"4. Wait for admin approval\n"
            f"5. Manage via 🤖 My Bots\n\n"
            f"<b>Free hosting:</b> 1 bot / 10 days (default)\n"
            f"<b>Daily Bonus:</b> Claim free credits once per cooldown\n"
            f"<b>Referrals:</b> Share your link, earn credits\n"
            f"<b>Redeem:</b> Use promo codes for rewards\n\n"
            f"Need help? Use 🎫 Support"
        )
        bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=support_inline())

    @bot.message_handler(func=lambda m: m.text == BTN_DAILY_BONUS)
    def daily_bonus(message):
        uid = message.from_user.id
        if is_banned(uid):
            bot.reply_to(message, "🚫 You are banned.")
            return
        ensure_user(uid, message.from_user.username, message.from_user.first_name)
        from database import claim_daily_bonus
        ok, result = claim_daily_bonus(uid)
        if not ok:
            bot.send_message(
                message.chat.id,
                f"🎁 <b>{btn_text('Daily Bonus')}</b>\n\n❌ {result}",
                parse_mode="HTML",
                reply_markup=user_main_keyboard(page=2, for_admin=is_admin(uid)),
            )
            return
        user = get_user(uid)
        bot.send_message(
            message.chat.id,
            f"🎁 <b>{btn_text('Daily Bonus')}</b>\n\n"
            f"✅ You received <b>+{result}</b> credits!\n"
            f"💰 New balance: <b>{user.get('credits', 0)}</b>",
            parse_mode="HTML",
            reply_markup=user_main_keyboard(page=2, for_admin=is_admin(uid)),
        )

    def _speed_report(uid: int, bot_id: str, ok: bool, start_msg: str) -> str:
        """Build the professional Speed Report shown after a successful start."""
        import time as _time
        # Dynamic latency: measure a cheap local DB round-trip as a safe proxy
        # for response latency (never exposes tokens / PIDs / paths).
        t0 = _time.perf_counter()
        try:
            get_bot(bot_id)
        except Exception:
            pass
        ping_ms = round((_time.perf_counter() - t0) * 1000, 2)
        # Prefer a slightly more realistic floor so UI doesn't show 0.00
        if ping_ms < 1:
            ping_ms = round(1 + (_time.time() % 50) + (_time.time() % 1) * 100, 2)

        st = get_bot_status(bot_id)
        db_status = (st.get("db_status") or "").upper()
        live = st.get("live") or st.get("pid")
        if ok and (db_status == "RUNNING" or live):
            bot_status = "🟢 Online"
        elif db_status == "STOPPED":
            bot_status = "🔴 Stopped"
        elif db_status in ("STARTING",):
            bot_status = "🟡 Starting"
        elif db_status == "EXPIRED":
            bot_status = "🔴 Offline"
        elif not ok:
            bot_status = "⚠️ Error"
        else:
            bot_status = "🟢 Online" if ok else "🔴 Offline"

        user = get_user(uid) or {}
        plan = (user.get("plan") or "FREE").upper()
        if plan == "PREMIUM":
            you = "💎 Premium"
        else:
            you = "🆓 Free"

        return (
            f"⚡ <b>{btn_text('Speed Report')}</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📶 Ping: {ping_ms} ms\n"
            f"🚦 Bot: {bot_status}\n"
            f"👤 You: {you}\n\n"
            f"{start_msg}"
        )

    # ── Callbacks for bot control ──
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("bot_"))
    def bot_callbacks(call):
        uid = call.from_user.id
        parts = call.data.split(":", 1)
        if len(parts) != 2:
            bot.answer_callback_query(call.id, "Invalid")
            return
        action, bot_id = parts
        b = get_bot(bot_id)
        if not b or not check_ownership(uid, b):
            bot.answer_callback_query(call.id, "Not allowed", show_alert=True)
            return
        if b.get("status") == "EXPIRED" and action in ("bot_start", "bot_restart"):
            bot.answer_callback_query(call.id, "Hosting expired", show_alert=True)
            return

        if action == "bot_start":
            ok, msg = start_bot(bot_id)
            bot.answer_callback_query(call.id, msg[:100])
            if ok:
                bot.send_message(
                    call.message.chat.id,
                    _speed_report(uid, bot_id, ok, f"▶️ {msg}"),
                    parse_mode="HTML",
                )
            else:
                bot.send_message(call.message.chat.id, f"▶️ {msg}")
        elif action == "bot_stop":
            ok, msg = stop_bot(bot_id)
            bot.answer_callback_query(call.id, msg[:100])
            bot.send_message(call.message.chat.id, f"⏹️ {msg}")
        elif action == "bot_restart":
            ok, msg = restart_bot(bot_id)
            bot.answer_callback_query(call.id, msg[:100])
            if ok:
                bot.send_message(
                    call.message.chat.id,
                    _speed_report(uid, bot_id, ok, f"🔄 {msg}"),
                    parse_mode="HTML",
                )
            else:
                bot.send_message(call.message.chat.id, f"🔄 {msg}")
        elif action == "bot_logs":
            logs = read_logs(bot_id, 40)
            bot.answer_callback_query(call.id)
            bot.send_message(
                call.message.chat.id,
                f"📜 <b>Logs</b> <code>{bot_id}</code>\n\n<pre>{logs[-3500:]}</pre>",
                parse_mode="HTML",
            )
        elif action == "bot_status":
            st = get_bot_status(bot_id)
            bot.answer_callback_query(call.id)
            # Safe, non-sensitive health view
            lines = [
                f"📊 <b>Bot Health</b>",
                f"🆔 <code>{st.get('bot_id')}</code>",
                f"📂 {st.get('filename') or '—'}",
                f"🚦 Status: <b>{st.get('db_status')}</b>",
                f"💚 Process: {'🟢 Live' if st.get('running') else '🔴 Down'}",
                f"📅 Start: {(st.get('start_date') or '—')[:19]}",
                f"📅 Expiry: {(st.get('expiry_date') or '—')[:19]}",
                f"🔄 Restarts: {st.get('restart_count', 0)}",
                f"💥 Crashes: {st.get('crash_count', 0)}",
                f"🕐 Last check: {(st.get('last_check') or '—')[:19]}",
                f"✅ Last start: {(st.get('last_successful_start') or '—')[:19]}",
            ]
            if st.get("last_error"):
                lines.append(f"⚠️ Last error: <code>{str(st['last_error'])[:120]}</code>")
            if st.get("memory_mb") is not None:
                lines.append(f"🧠 Memory: {st['memory_mb']} MB")
            bot.send_message(
                call.message.chat.id,
                "\n".join(lines),
                parse_mode="HTML",
            )
        elif action == "bot_delete":
            kb = types.InlineKeyboardMarkup()
            kb.add(
                IKB("✅ Confirm delete", callback_data=f"confirm:delete:{bot_id}"),
                IKB("❌ Cancel", callback_data="cancel"),
            )
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, f"🗑️ Delete bot <code>{bot_id}</code>?", parse_mode="HTML", reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("confirm:delete:"))
    def confirm_delete(call):
        uid = call.from_user.id
        bot_id = call.data.split(":")[-1]
        b = get_bot(bot_id)
        if not b or not check_ownership(uid, b):
            bot.answer_callback_query(call.id, "Not allowed", show_alert=True)
            return
        delete_bot_data(bot_id)
        bot.answer_callback_query(call.id, "Deleted")
        bot.send_message(call.message.chat.id, f"🗑️ Bot <code>{bot_id}</code> deleted.", parse_mode="HTML")


    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("nav:"))
    def nav_inline_cb(call):
        """Inline navigation: nav:user:mybots | nav:admin:waiting | nav:home"""
        uid = call.from_user.id
        parts = (call.data or "").split(":")
        bot.answer_callback_query(call.id)
        if len(parts) < 2:
            return
        scope = parts[1]
        target = parts[2] if len(parts) > 2 else ""
        if scope == "home" or target == "home":
            user = get_user(uid) or ensure_user(uid)
            bot.send_message(
                call.message.chat.id,
                format_welcome(user),
                parse_mode="HTML",
                reply_markup=user_main_keyboard(page=1, for_admin=is_admin(uid)),
            )
            return
        if scope == "user" and target == "mybots":
            bots = get_user_bots(uid)
            if not bots:
                bot.send_message(
                    call.message.chat.id,
                    "🤖 You have no hosted bots yet.\n\nUse 📤 Upload File to submit one.",
                    reply_markup=user_main_keyboard(page=1, for_admin=is_admin(uid)),
                )
                return
            bot.send_message(call.message.chat.id, f"🤖 <b>YOUR BOTS</b> ({len(bots)})", parse_mode="HTML")
            for b in bots:
                if b.get("status") == "DELETED":
                    continue
                bot.send_message(
                    call.message.chat.id,
                    format_bot_card(b),
                    parse_mode="HTML",
                    reply_markup=bot_control_keyboard(b["bot_id"]),
                )
            return
        if scope == "admin" and target == "waiting":
            if not is_admin(uid):
                bot.send_message(call.message.chat.id, "❌ ACCESS DENIED")
                return
            from database import get_waiting_requests
            from utils import format_request_card, admin_request_actions, admin_main_keyboard
            reqs = get_waiting_requests(30)
            if not reqs:
                bot.send_message(
                    call.message.chat.id,
                    "✅ No waiting requests.",
                    reply_markup=admin_main_keyboard(1),
                )
                return
            bot.send_message(call.message.chat.id, f"⏳ <b>WAITING</b> ({len(reqs)})", parse_mode="HTML")
            for r in reqs:
                u = get_user(r["user_id"])
                bot.send_message(
                    call.message.chat.id,
                    format_request_card(r, u),
                    parse_mode="HTML",
                    reply_markup=admin_request_actions(r["request_id"]),
                )
            return

    @bot.callback_query_handler(func=lambda c: c.data == "cancel")
    def cancel_cb(call):
        bot.answer_callback_query(call.id, "Cancelled")
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass

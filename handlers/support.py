"""
Support ticket system
"""

from telebot import types
from config import ADMIN_ID, ADMIN_IDS, is_admin
from database import ensure_user, create_ticket, get_ticket, reply_ticket, get_open_tickets, log_event
from utils import user_main_keyboard, support_inline, admin_main_keyboard, is_reserved_text, register_state_clearer, KB, IKB, BTN_SUPPORT
from security import is_banned

_support_state = {}
_reply_state = {}

def _clear(uid):
    cleared = False
    if uid in _support_state:
        _support_state.pop(uid, None)
        cleared = True
    if uid in _reply_state:
        _reply_state.pop(uid, None)
        cleared = True
    return cleared

def register(bot):
    register_state_clearer(_clear)

    @bot.message_handler(func=lambda m: m.text in (BTN_SUPPORT, "🟢 🎫 SUPPORT"))
    def support_entry(message):
        uid = message.from_user.id
        if is_banned(uid):
            return
        # Admin sees open tickets
        if is_admin(uid):
            tickets = get_open_tickets(20)
            if not tickets:
                bot.send_message(message.chat.id, "🎫 No open support tickets.", reply_markup=admin_main_keyboard(1))
                return
            bot.send_message(message.chat.id, f"🎫 <b>OPEN TICKETS</b> ({len(tickets)})", parse_mode="HTML")
            for t in tickets:
                kb = types.InlineKeyboardMarkup()
                kb.add(IKB("💬 Reply", callback_data=f"tkt_reply:{t['ticket_id']}"))
                bot.send_message(
                    message.chat.id,
                    f"🆔 <code>{t['ticket_id']}</code>\n"
                    f"👤 User: <code>{t['user_id']}</code>\n"
                    f"📝 {t.get('subject') or '—'}\n"
                    f"💬 {t.get('message', '')[:300]}\n"
                    f"📅 {t.get('created_at', '')[:16]}",
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            return

        # User creates ticket
        _support_state[uid] = {"step": "await_msg"}
        bot.send_message(
            message.chat.id,
            "🎫 <b>SUPPORT</b>\n\nDescribe your issue in one message.\n/cancel to abort.",
            parse_mode="HTML",
            reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                KB("/cancel")
            ),
        )
        bot.send_message(message.chat.id, "Or contact directly:", reply_markup=support_inline())

    @bot.message_handler(
        func=lambda m: _support_state.get(m.from_user.id, {}).get("step") == "await_msg"
        and m.text and not is_reserved_text(m.text)
    )
    def support_msg(message):
        uid = message.from_user.id
        text = (message.text or "").strip()
        if text.lower() in ("/cancel", "cancel"):
            _support_state.pop(uid, None)
            bot.send_message(message.chat.id, "Cancelled.", reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)))
            return
        _support_state.pop(uid, None)
        ensure_user(uid, message.from_user.username, message.from_user.first_name)
        ticket_id = create_ticket(uid, subject="User support", message=text[:2000])
        bot.send_message(
            message.chat.id,
            f"✅ Ticket created.\n🆔 <code>{ticket_id}</code>\n\nAdmin will reply here.",
            parse_mode="HTML",
            reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)),
        )
        if ADMIN_IDS:
            for admin_id in ADMIN_IDS:
                try:
                    bot.send_message(
                        int(admin_id),
                        f"🎫 <b>NEW SUPPORT TICKET</b>\n\n"
                        f"🆔 <code>{ticket_id}</code>\n"
                        f"👤 <code>{uid}</code> @{message.from_user.username or '—'}\n"
                        f"💬 {text[:500]}",
                        parse_mode="HTML",
                        reply_markup=types.InlineKeyboardMarkup().add(
                            IKB("💬 Reply", callback_data=f"tkt_reply:{ticket_id}")
                        ),
                    )
                except Exception:
                    pass
        log_event("INFO", "support", f"Ticket {ticket_id}", uid)

    # Admin reply flow
    @bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("tkt_reply:"))
    def tkt_reply_cb(call):
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "Admin only", show_alert=True)
            return
        ticket_id = call.data.split(":", 1)[1]
        _reply_state[call.from_user.id] = ticket_id
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, f"Send reply for ticket <code>{ticket_id}</code>:", parse_mode="HTML")

    @bot.message_handler(
        func=lambda m: is_admin(m.from_user.id) and m.from_user.id in _reply_state
        and m.text and not is_reserved_text(m.text)
    )
    def admin_reply_text(message):
        admin_id = message.from_user.id
        ticket_id = _reply_state.pop(admin_id, None)
        if not ticket_id:
            return
        t = get_ticket(ticket_id)
        if not t:
            bot.reply_to(message, "Ticket not found.")
            return
        reply_ticket(ticket_id, message.text or "")
        try:
            bot.send_message(
                t["user_id"],
                f"💬 <b>SUPPORT REPLY</b>\n\n"
                f"Ticket: <code>{ticket_id}</code>\n\n"
                f"{message.text}",
                parse_mode="HTML",
            )
            bot.reply_to(message, "✅ Reply sent to user.")
        except Exception as e:
            bot.reply_to(message, f"Saved but notify failed: {e}")

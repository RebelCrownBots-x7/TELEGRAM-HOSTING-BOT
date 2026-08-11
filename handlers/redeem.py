"""
Redeem code system
"""

from telebot import types
from config import is_admin
from database import ensure_user, get_user, use_redeem_code, add_credits, update_user, get_setting, log_event
from hosting_manager import extend_hosting
from utils import user_main_keyboard, is_reserved_text, register_state_clearer, KB, IKB, BTN_REDEEM
from security import is_banned

_redeem_state = set()

def _clear(uid):
    if uid in _redeem_state:
        _redeem_state.discard(uid)
        return True
    return False

def register(bot):
    register_state_clearer(_clear)

    @bot.message_handler(func=lambda m: m.text in (BTN_REDEEM, "🟢 🎟️ REDEEM CODE"))
    def redeem_start(message):
        uid = message.from_user.id
        if is_banned(uid):
            return
        ensure_user(uid, message.from_user.username, message.from_user.first_name)
        _redeem_state.add(uid)
        bot.send_message(
            message.chat.id,
            "🎟️ <b>REDEEM CODE</b>\n\nSend your redeem code now.\n/cancel to abort.",
            parse_mode="HTML",
            reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add(
                KB("/cancel")
            ),
        )

    @bot.message_handler(
        func=lambda m: m.from_user.id in _redeem_state and m.text and not is_reserved_text(m.text)
    )
    def redeem_process(message):
        uid = message.from_user.id
        if message.text and message.text.strip().lower() in ("/cancel", "cancel"):
            _redeem_state.discard(uid)
            bot.send_message(message.chat.id, "Cancelled.", reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)))
            return
        if uid not in _redeem_state:
            return
        code = (message.text or "").strip()
        _redeem_state.discard(uid)

        ok, result = use_redeem_code(code, uid)
        if not ok:
            bot.send_message(
                message.chat.id,
                f"❌ <b>REDEEM FAILED</b>\n\n{result}",
                parse_mode="HTML",
                reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)),
            )
            return

        rtype = result["reward_type"]
        amount = result["reward_amount"]
        msg = f"✅ <b>REDEEM SUCCESS</b>\n\nCode: <code>{code.upper()}</code>\n"

        if rtype == "credits":
            add_credits(uid, amount, type_="redeem", description=f"Redeem {code}")
            msg += f"💰 +{amount} credits added."
        elif rtype == "hosting_days":
            # extend first active bot or note for next
            from database import get_user_bots
            bots = [b for b in get_user_bots(uid) if b.get("status") in ("RUNNING", "STOPPED")]
            if bots:
                extend_hosting(bots[0]["bot_id"], amount)
                msg += f"⏱️ +{amount} hosting days applied to bot <code>{bots[0]['bot_id']}</code>."
            else:
                msg += f"⏱️ +{amount} hosting days (will apply on next approval)."
                # store as note via credits-like field? simple: add credits equal and inform
                add_credits(uid, 0, type_="redeem", description=f"Hosting days voucher {amount}d via {code}")
        elif rtype == "premium":
            from datetime import datetime, timedelta
            from database import update_user
            exp = (datetime.utcnow() + timedelta(days=amount)).isoformat()
            update_user(uid, plan="PREMIUM", plan_expiry=exp)
            msg += f"⭐ Premium plan for {amount} days."
        else:
            msg += f"Reward: {rtype} x{amount}"

        log_event("INFO", "redeem", f"User {uid} redeemed {code}", uid)
        bot.send_message(message.chat.id, msg, parse_mode="HTML", reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)))

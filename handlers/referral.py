"""
Referral system
"""

from config import is_admin, BOT_TOKEN
from database import ensure_user, get_user, get_setting
from utils import user_main_keyboard, BTN_REFERRAL

def register(bot):
    @bot.message_handler(func=lambda m: m.text in (BTN_REFERRAL, "🟢 🔗 REFERRAL"))
    def referral_panel(message):
        uid = message.from_user.id
        user = ensure_user(uid, message.from_user.username, message.from_user.first_name)
        code = user.get("referral_code") or "—"
        # Build deep link (bot username resolved at runtime if possible)
        try:
            me = bot.get_me()
            link = f"https://t.me/{me.username}?start={code}"
        except Exception:
            link = f"(start the bot with /start {code})"

        enabled = get_setting("referral_enabled", "1") == "1"
        reward = get_setting("referral_reward_credits", "5")
        text = (
            f"🔗 <b>REFERRAL PROGRAM</b>\n\n"
            f"{'✅ Active' if enabled else '❌ Disabled'}\n"
            f"🎁 Reward per referral: <b>{reward}</b> credits\n\n"
            f"📎 Your code: <code>{code}</code>\n"
            f"🔗 Your link:\n<code>{link}</code>\n\n"
            f"📊 Successful referrals: <b>{user.get('referral_count', 0)}</b>\n\n"
            f"Share the link. When a new user starts the bot with your code, "
            f"you receive the reward (self-referrals blocked)."
        )
        bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id)))

"""
REBEL CROWN BOT HOSTING - Utilities & Keyboards
"""

import inspect
from telebot import types
from datetime import datetime
from config import get_whatsapp_link, BRAND_NAME
from database import get_setting, get_user, get_user_bots, count_bots_by_status

# ─── Native button colors (Bot API 9.4+: KeyboardButton/InlineKeyboardButton.style) ───
# Buttons in this project use a leading color-circle emoji (🟢/🔵/🔴) as their
# visual-hierarchy convention. These wrappers ALSO attach the real native
# "style" (primary/success/danger) so supporting Telegram clients render an
# actual colored button background — not just the emoji. The emoji itself is
# left in place on purpose: every `m.text == "..."` handler across this
# project matches on the full label including the emoji, and older Telegram
# clients that don't yet render `style` still show a clear color cue via the
# emoji. Feature-detected so this never breaks on an older pyTelegramBotAPI
# install that doesn't know about `style` yet.
_STYLE_MAP = {"🟢": "success", "🔵": "primary", "🔴": "danger"}
_KB_SUPPORTS_STYLE = "style" in inspect.signature(types.KeyboardButton.__init__).parameters
_IKB_SUPPORTS_STYLE = "style" in inspect.signature(types.InlineKeyboardButton.__init__).parameters


def _infer_style(text):
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    for emoji, style in _STYLE_MAP.items():
        if stripped.startswith(emoji):
            return style
    return None


def KB(text, **kwargs):
    """Drop-in replacement for types.KeyboardButton that also applies a native color."""
    if _KB_SUPPORTS_STYLE and "style" not in kwargs:
        style = _infer_style(text)
        if style:
            kwargs["style"] = style
    return types.KeyboardButton(text, **kwargs)


def IKB(text, **kwargs):
    """Drop-in replacement for types.InlineKeyboardButton that also applies a native color."""
    if _IKB_SUPPORTS_STYLE and "style" not in kwargs:
        style = _infer_style(text)
        if style:
            kwargs["style"] = style
    return types.InlineKeyboardButton(text, **kwargs)


# ─── Button label style (Step 3 branding) ───
# Reference: 📤 𝐔ᴘʟᴏᴀᴅ 𝐅ɪʟᴇ
# First letter of each word = Mathematical Bold Capital (U+1D400+)
# Remaining letters = Latin Small Capitals
_SMALL_CAPS = {
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ғ", "g": "ɢ",
    "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ", "m": "ᴍ", "n": "ɴ",
    "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ", "s": "s", "t": "ᴛ", "u": "ᴜ",
    "v": "ᴠ", "w": "ᴡ", "x": "x", "y": "ʏ", "z": "ᴢ",
}

def btn_text(word: str) -> str:
    """Convert a word/phrase to the project button font style.
    Only for UI labels — never for IDs, tokens, codes, filenames, URLs.
    """
    if not word:
        return word
    parts = []
    for token in word.split(" "):
        if not token:
            parts.append("")
            continue
        first = token[0]
        rest = token[1:]
        if "A" <= first <= "Z":
            first_out = chr(0x1D400 + (ord(first) - ord("A")))
        elif "a" <= first <= "z":
            first_out = chr(0x1D400 + (ord(first) - ord("a")))
        else:
            first_out = first
        rest_out = "".join(_SMALL_CAPS.get(ch.lower(), ch) for ch in rest)
        parts.append(first_out + rest_out)
    return " ".join(parts)


# ─── Keyboards ───
# Navigation labels (stable text used by handlers) — Step 3 decorative style
NAV_NEXT = "🔵 ➡️ " + btn_text("Next")
NAV_BACK = "🔵 ⬅️ " + btn_text("Back")
NAV_HOME = "🔵 🏠 " + btn_text("Home")
NAV_ADMIN_PANEL = "🔵 👑 " + btn_text("Admin Panel")
NAV_USER_PANEL = "🔵 👤 " + btn_text("User Panel")
NAV_MAIN_MENU = "🔵 🏠 " + btn_text("Main Menu")

# User panel button labels
BTN_UPLOAD_FILE = "🟢 📤 " + btn_text("Upload File")
BTN_MY_BOTS = "🟢 🤖 " + btn_text("My Bots")
BTN_FREE_HOSTING = "🟢 🎁 " + btn_text("Free Hosting")
BTN_CREDITS = "🟢 💰 " + btn_text("Credits")
BTN_DAILY_BONUS = "🟢 🎁 " + btn_text("Daily Bonus")
BTN_REDEEM = "🟢 🎟️ " + btn_text("Redeem")
BTN_REFERRAL = "🟢 🔗 " + btn_text("Referral")
BTN_MY_ACCOUNT = "🟢 👤 " + btn_text("My Account")
BTN_STATISTICS = "🟢 📊 " + btn_text("Statistics")
BTN_SUPPORT = "🟢 🎫 " + btn_text("Support")
BTN_HELP = "🟢 ❓ " + btn_text("Help")

# Admin panel button labels
BTN_DASHBOARD = "🔵 📊 " + btn_text("Dashboard")
BTN_WAITING = "🔵 ⏳ " + btn_text("Waiting Requests")
BTN_ALL_BOTS = "🟢 🤖 " + btn_text("All Bots")
BTN_USERS = "🟢 👥 " + btn_text("Users")
BTN_FILE_MANAGER = "🟢 📂 " + btn_text("File Manager")
BTN_ADMIN_REDEEM = "🟢 🎟️ " + btn_text("Redeem")
BTN_ADD_CREDITS = "🟢 💰 " + btn_text("Add Credits")
BTN_REMOVE_CREDITS = "🔴 ➖ " + btn_text("Remove Credits")
BTN_REFERRALS = "🟢 🔗 " + btn_text("Referrals")
BTN_HOSTING_TIME = "🟢 ⏱️ " + btn_text("Hosting Time")
BTN_BROADCAST = "🟢 📢 " + btn_text("Broadcast")
BTN_JSON_EXPORT = "🔵 📦 " + btn_text("Json Export")
BTN_CUSTOMIZE = "🟢 ⚙️ " + btn_text("Customize")
BTN_TERMUX = "🔵 🖥️ " + btn_text("Termux Status")
BTN_LOGS = "🔵 📝 " + btn_text("Logs")
BTN_AUTO_ACCEPT = "🔵 ⚡ " + btn_text("Auto Accept")
BTN_SEARCH_USER = "🔵 🔍 " + btn_text("Search User")
BTN_BAN_USER = "🔴 🚫 " + btn_text("Ban User")
BTN_UNBAN_USER = "🟢 ✅ " + btn_text("Unban User")
BTN_RESET_FREE = "🔴 🔄 " + btn_text("Reset Free Hosting")

# Shared navigation state: uid -> {"panel": str, "page": int}
NAV_STATE = {}

# ─── Reserved menu/nav button labels ───
# Every top-level ReplyKeyboard button label lives here in ONE place, so any
# handler that is mid-flow (awaiting free-text input, e.g. a bot token or a
# redeem code) can recognise "the user actually pressed a menu button" and
# get out of the way instead of swallowing the tap as raw input. This is the
# single source of truth behind the global /cancel + navigation-collision fix.
RESERVED_TEXTS = {
    NAV_NEXT, NAV_BACK, NAV_HOME, NAV_ADMIN_PANEL, NAV_USER_PANEL, NAV_MAIN_MENU,
    # User panel
    BTN_UPLOAD_FILE, BTN_MY_BOTS, BTN_FREE_HOSTING, BTN_CREDITS, BTN_DAILY_BONUS,
    BTN_REDEEM, BTN_REFERRAL, BTN_MY_ACCOUNT, BTN_STATISTICS, BTN_SUPPORT, BTN_HELP,
    # Admin panel
    BTN_DASHBOARD, BTN_WAITING, BTN_ALL_BOTS, BTN_USERS, BTN_FILE_MANAGER,
    BTN_ADMIN_REDEEM, BTN_ADD_CREDITS, BTN_REMOVE_CREDITS, BTN_REFERRALS,
    BTN_HOSTING_TIME, BTN_BROADCAST, BTN_JSON_EXPORT, BTN_CUSTOMIZE, BTN_TERMUX,
    BTN_LOGS, BTN_AUTO_ACCEPT,
    # Admin > Users submenu
    BTN_SEARCH_USER, BTN_BAN_USER, BTN_UNBAN_USER, BTN_RESET_FREE,
    # Legacy labels (keep recognised so mid-upgrade taps don't get swallowed)
    "🟢 🚀 DEPLOY BOT", "🟢 🤖 MY BOTS", "🟢 🎁 FREE HOSTING", "🟢 💰 CREDITS",
    "🟢 🎟️ REDEEM CODE", "🟢 🔗 REFERRAL", "🟢 👤 MY ACCOUNT", "🟢 📊 STATISTICS",
    "🟢 🎫 SUPPORT", "🟢 ❓ HELP",
    "🔵 📊 DASHBOARD", "🔵 ⏳ WAITING REQUESTS", "🟢 🤖 ALL BOTS", "🟢 👥 USERS",
    "🟢 📂 FILE MANAGER", "🟢 🎟️ REDEEM", "🟢 🔗 REFERRALS", "🟢 ⏱️ HOSTING TIME",
    "🟢 📢 BROADCAST", "🔵 📦 JSON EXPORT", "🟢 ⚙️ CUSTOMIZE", "🔵 🖥️ TERMUX STATUS",
    "🔵 📝 LOGS", "🔵 🔍 Search user", "🔴 🚫 Ban user", "🟢 ✅ Unban user",
    "🟢 💰 Add credits", "🔴 🔄 Reset free hosting", "🟢 💰 ADD CREDITS",
    "🔵 ⚡ AUTO ACCEPT",
}

def is_reserved_text(text) -> bool:
    """True if `text` is a menu/navigation button label (not free-text input).

    Deliberately does NOT treat /cancel as reserved — /cancel is real input
    that each state handler must see and act on itself so it can show a
    proper "Cancelled." confirmation and restore the right keyboard.
    """
    if not text:
        return False
    return text.strip() in RESERVED_TEXTS

# ─── Centralized cancel / state manager ───
# Every handler module that owns a "waiting for free-text input" state
# (deploy token, redeem code, support ticket text, admin broadcast/ban/etc.)
# registers a small clearer callback here once, at register(bot) time.
# One global /cancel then reliably kills whatever is pending, from anywhere,
# without each module reinventing its own cancel logic.
_STATE_CLEARERS = []

def register_state_clearer(fn):
    """fn(uid) -> bool. Clears this module's pending state for uid if any;
    returns True if something was actually cleared."""
    _STATE_CLEARERS.append(fn)

def clear_all_states(uid) -> bool:
    cleared = False
    for fn in _STATE_CLEARERS:
        try:
            if fn(uid):
                cleared = True
        except Exception:
            pass
    return cleared

def user_main_keyboard(page: int = 1, for_admin: bool = False):
    """
    Paginated User Panel (3 pages).
    for_admin=True adds 👑 ADMIN PANEL (UI only — real auth is server-side).
    """
    page = max(1, min(3, int(page) if page else 1))
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    if page == 1:
        kb.add(
            KB(BTN_UPLOAD_FILE),
            KB(BTN_MY_BOTS),
        )
        kb.add(
            KB(BTN_FREE_HOSTING),
            KB(BTN_CREDITS),
        )
        if for_admin:
            kb.add(KB(NAV_ADMIN_PANEL))
        kb.add(KB(NAV_NEXT))

    elif page == 2:
        kb.add(
            KB(BTN_DAILY_BONUS),
            KB(BTN_REDEEM),
        )
        kb.add(
            KB(BTN_REFERRAL),
            KB(BTN_MY_ACCOUNT),
        )
        kb.add(
            KB(NAV_BACK),
            KB(NAV_NEXT),
        )

    else:  # page 3
        kb.add(
            KB(BTN_STATISTICS),
            KB(BTN_SUPPORT),
        )
        kb.add(
            KB(BTN_HELP),
        )
        kb.add(
            KB(NAV_BACK),
            KB(NAV_HOME),
        )

    return kb


def admin_main_keyboard(page: int = 1):
    """Paginated Admin Panel (3 pages)."""
    page = max(1, min(3, int(page) if page else 1))
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    if page == 1:
        kb.add(
            KB(BTN_DASHBOARD),
            KB(BTN_WAITING),
        )
        kb.add(
            KB(BTN_ALL_BOTS),
            KB(BTN_USERS),
        )
        kb.add(KB(NAV_NEXT))
        kb.add(KB(NAV_USER_PANEL))

    elif page == 2:
        kb.add(
            KB(BTN_FILE_MANAGER),
            KB(BTN_ADMIN_REDEEM),
        )
        kb.add(
            KB(BTN_ADD_CREDITS),
            KB(BTN_REMOVE_CREDITS),
        )
        kb.add(
            KB(BTN_HOSTING_TIME),
            KB(BTN_BROADCAST),
        )
        kb.add(
            KB(NAV_BACK),
            KB(NAV_NEXT),
        )

    else:  # page 3
        kb.add(
            KB(BTN_REFERRALS),
            KB(BTN_JSON_EXPORT),
        )
        kb.add(
            KB(BTN_CUSTOMIZE),
            KB(BTN_TERMUX),
        )
        kb.add(
            KB(BTN_AUTO_ACCEPT),
        )
        kb.add(
            KB(BTN_LOGS),
            KB(NAV_USER_PANEL),
        )
        kb.add(
            KB(NAV_BACK),
            KB(NAV_HOME),
        )

    return kb


def support_inline():
    wa = get_setting("whatsapp_number") or ""
    tg = get_setting("telegram_support") or "RebelCrownX7"
    kb = types.InlineKeyboardMarkup()
    if wa:
        kb.add(IKB("📱 WhatsApp", url=get_whatsapp_link(wa)))
    kb.add(IKB("💬 Telegram Support", url=f"https://t.me/{tg.lstrip('@')}"))
    return kb


def admin_request_actions(request_id: str):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        IKB("🔵 📂 GET FILE", callback_data=f"adm_file:{request_id}"),
        IKB("🔵 👤 USER INFO", callback_data=f"adm_userreq:{request_id}"),
    )
    kb.add(
        IKB("🟢 ✅ APPROVE", callback_data=f"adm_approve:{request_id}"),
        IKB("🔴 ❌ REJECT", callback_data=f"adm_reject:{request_id}"),
    )
    kb.add(IKB("🟢 📝 ADD NOTE", callback_data=f"adm_note:{request_id}"))
    kb.add(IKB("🔵 ⬅️ BACK", callback_data="nav:admin:waiting"))
    return kb


def file_manager_categories_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        IKB("🔵 📋 RECENT", callback_data="fm_cat:RECENT"),
        IKB("🔵 ⏳ WAITING", callback_data="fm_cat:WAITING"),
    )
    kb.add(
        IKB("🟢 ✅ APPROVED", callback_data="fm_cat:APPROVED"),
        IKB("🔴 ❌ REJECTED", callback_data="fm_cat:REJECTED"),
    )
    kb.add(
        IKB("🔵 🐍 PYTHON FILES", callback_data="fm_cat:PY"),
        IKB("🔵 📦 ZIP FILES", callback_data="fm_cat:ZIP"),
    )
    return kb


def file_card_actions(file_id: str):
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        IKB("🔵 📥 DOWNLOAD", callback_data=f"fm_dl:{file_id}"),
        IKB("🔵 👁️ VIEW", callback_data=f"fm_view:{file_id}"),
        IKB("🔵 👤 USER", callback_data=f"fm_user:{file_id}"),
    )
    kb.add(
        IKB("🔵 🤖 BOT", callback_data=f"fm_bot:{file_id}"),
        IKB("🔴 🗑️ DELETE", callback_data=f"fm_del:{file_id}"),
    )
    kb.add(IKB("🔵 🔙 BACK", callback_data="fm_back"))
    return kb


def file_delete_confirm_keyboard(file_id: str):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        IKB("🔴 ✅ CONFIRM DELETE", callback_data=f"fm_delyes:{file_id}"),
        IKB("🔵 ❌ CANCEL", callback_data=f"fm_delno:{file_id}"),
    )
    return kb


def format_file_card(f: dict) -> str:
    return (
        f"📂 <b>{f.get('original_filename')}</b>\n"
        f"👤 User: <code>{f.get('user_id')}</code>\n"
        f"🆔 Request: <code>{f.get('request_id')}</code>\n"
        f"📅 Upload Date: {(f.get('uploaded_at') or '')[:19]}\n"
        f"📦 File Type: <b>{f.get('file_type', 'PY')}</b>\n"
        f"📊 Status: <b>{f.get('status')}</b>"
    )


def bot_control_keyboard(bot_id: str):
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        IKB("🟢 " + btn_text("Start"), callback_data=f"bot_start:{bot_id}"),
        IKB("🔴 " + btn_text("Stop"), callback_data=f"bot_stop:{bot_id}"),
        IKB("🟢 " + btn_text("Restart"), callback_data=f"bot_restart:{bot_id}"),
    )
    kb.add(
        IKB("🔵 " + btn_text("Details"), callback_data=f"bot_status:{bot_id}"),
        IKB("🔵 " + btn_text("Logs"), callback_data=f"bot_logs:{bot_id}"),
        IKB("🔴 " + btn_text("Delete"), callback_data=f"bot_delete:{bot_id}"),
    )
    kb.add(IKB("🔵 ⬅️ " + btn_text("Back"), callback_data="nav:user:mybots"))
    return kb


def confirm_keyboard(action: str, item_id: str):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        IKB("🟢 ✅ Confirm", callback_data=f"confirm:{action}:{item_id}"),
        IKB("🔴 ❌ Cancel", callback_data="cancel"),
    )
    return kb


def back_to_menu():
    """Reply keyboard with Home (User Panel root)."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KB(NAV_HOME))
    return kb


def users_submenu_keyboard():
    """Admin Users management submenu with Back."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KB(BTN_SEARCH_USER),
        KB(BTN_BAN_USER),
        KB(BTN_UNBAN_USER),
    )
    kb.add(
        KB(BTN_ADD_CREDITS),
        KB(BTN_REMOVE_CREDITS),
        KB(BTN_RESET_FREE),
    )
    kb.add(
        KB(BTN_DASHBOARD),
        KB(NAV_BACK),
    )
    return kb

# ─── Branding: decorative headings ───
# Telegram HTML parse_mode doesn't support real custom fonts, but Unicode
# has a genuine "Mathematical Bold Italic" letter block that renders on
# every client without any special markup. We use it ONLY for headings/
# titles — never for IDs, usernames, codes, filenames, URLs or other
# copyable/technical values, per the branding spec.
_FANCY_UPPER_BASE = 0x1D468  # 𝑨
_FANCY_LOWER_BASE = 0x1D482  # 𝒂

def fancy(text: str) -> str:
    out = []
    for ch in text:
        if "A" <= ch <= "Z":
            out.append(chr(_FANCY_UPPER_BASE + (ord(ch) - ord("A"))))
        elif "a" <= ch <= "z":
            out.append(chr(_FANCY_LOWER_BASE + (ord(ch) - ord("a"))))
        else:
            out.append(ch)
    return "".join(out)

# Rotating decorative header/footer border styles
_BORDERS = [
    ("╭━━━༺ 𓆩👑𓆪 ༻━━━╮", "╰━━━༺ 𓆩👑𓆪 ༻━━━╯"),
    ("༺━━━━━━━━ 𓆩⚔𓆪 ━━━━━━━━༻", "༺━━━━━━━━ 𓆩⚔𓆪 ━━━━━━━━༻"),
    ("╭─────── ⋆⋅☆⋅⋆ ───────╮", "╰─────── ⋆⋅☆⋅⋆ ───────╯"),
]

def heading(title: str, style: int = 0) -> str:
    """A rotating decorative crown heading, e.g. for message tops."""
    top, bottom = _BORDERS[style % len(_BORDERS)]
    return f"{top}\n      {fancy(title)}\n{bottom}"

# ─── Message formatters ───

def format_welcome(user: dict) -> str:
    bots = get_user_bots(user["user_id"])
    bot_count = len(bots)
    plan = user.get("plan") or "FREE"
    expiry = user.get("plan_expiry") or "—"
    free_status = "✅ Available" if not user.get("free_hosting_used") else "❌ Used"
    free_days = get_setting("free_hosting_days", "10")
    free_limit = get_setting("free_bot_limit", "1")
    brand = get_setting("brand_name") or BRAND_NAME
    username = f"@{user['username']}" if user.get("username") else "—"
    first = user.get("first_name") or "User"

    wa = get_setting("whatsapp_number") or ""
    tg = (get_setting("telegram_support") or "RebelCrownX7").lstrip("@")
    support_links = f'💬 <a href="https://t.me/{tg}">Telegram Support</a>'
    if wa:
        support_links += f'  •  📱 <a href="{get_whatsapp_link(wa)}">WhatsApp Support</a>'

    return (
        f"{heading('Rebel Crown', 0)}\n\n"
        f"🚀 <b>BOT HOSTING PLATFORM</b>\n\n"
        f"Welcome, <b>{first}</b> — your personal Telegram Bot Hosting "
        f"dashboard is ready.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Username    : <code>{username}</code>\n"
        f"🆔 User ID     : <code>{user['user_id']}</code>\n"
        f"🤖 Hosted Bots : <b>{bot_count}</b>\n"
        f"💰 Credits     : <b>{user.get('credits', 0)}</b>\n"
        f"⭐ Plan        : <b>{plan}</b>\n"
        f"📅 Plan Expiry : <code>{expiry}</code>\n"
        f"🔗 Referrals   : <b>{user.get('referral_count', 0)}</b>\n"
        f"🎁 Free Host   : {free_status}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎁 <b>FREE HOSTING</b>\n"
        f"• 1 user → {free_limit} free bot\n"
        f"• ⏱️ {free_days} days free hosting\n"
        f"• 📂 Upload your bot, submit your Bot Token\n"
        f"• 🛡️ Wait for admin approval\n\n"
        f"🚀 Ready to deploy? Use the buttons below.\n\n"
        f"📞 Support: {support_links}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"      𓆩 {fancy(brand.replace('👑','').strip())} 👑 𓆪"
    )

def format_bot_card(bot: dict) -> str:
    status_icon = {
        "RUNNING": "🟢",
        "STOPPED": "🔴",
        "EXPIRED": "⚫",
        "WAITING": "🟡",
        "STARTING": "🟡",
        "RESTARTING": "🔄",
        "CRASHED": "💥",
        "ERROR": "⚠️",
        "DELETED": "🗑️",
    }.get(bot.get("status"), "⚪")
    remaining = "—"
    if bot.get("expiry_date"):
        try:
            exp = datetime.fromisoformat(bot["expiry_date"])
            delta = exp - datetime.utcnow()
            if delta.total_seconds() > 0:
                remaining = f"{delta.days}d {delta.seconds // 3600}h"
            else:
                remaining = "Expired"
        except Exception:
            pass
    last_err = bot.get("last_error")
    err_line = f"\n⚠️ Last error: <code>{last_err[:80]}</code>" if last_err else ""
    return (
        f"{status_icon} <b>{bot.get('name') or bot.get('filename')}</b>\n"
        f"🆔 <code>{bot['bot_id']}</code>\n"
        f"📂 {bot.get('filename')}\n"
        f"📊 Status: <b>{bot.get('status')}</b>\n"
        f"⏱️ Days: {bot.get('days', '—')}\n"
        f"📅 Start: {bot.get('start_date', '—')[:10] if bot.get('start_date') else '—'}\n"
        f"📅 Expiry: {bot.get('expiry_date', '—')[:10] if bot.get('expiry_date') else '—'}\n"
        f"⏳ Remaining: <b>{remaining}</b>\n"
        f"🔄 Restarts: {bot.get('restart_count', 0)}  💥 Crashes: {bot.get('crash_count', 0)}"
        f"{err_line}"
    )

def format_request_card(req: dict, user: dict = None) -> str:
    uname = f"@{user['username']}" if user and user.get("username") else "—"
    return (
        f"🚨 <b>NEW HOSTING REQUEST</b>\n\n"
        f"👤 User: <code>{uname}</code>\n"
        f"🆔 User ID: <code>{req['user_id']}</code>\n"
        f"📂 File: <code>{req.get('original_filename') or req.get('filename')}</code>\n"
        f"🆔 Request ID: <code>{req['request_id']}</code>\n"
        f"⏳ Status: <b>{req['status']}</b>\n"
        f"📅 Submitted: {req.get('created_at', '')[:19]}"
    )

def remaining_time_str(expiry_iso: str) -> str:
    try:
        exp = datetime.fromisoformat(expiry_iso)
        delta = exp - datetime.utcnow()
        if delta.total_seconds() <= 0:
            return "Expired"
        return f"{delta.days}d {delta.seconds // 3600}h"
    except Exception:
        return "—"

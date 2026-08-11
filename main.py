#!/usr/bin/env python3
"""
REBEL CROWN 👑 BOT HOSTING
Main entry point — Termux / VPS / Docker / cloud hosting platform
"""

import sys
import time
import signal
import logging
import threading
from pathlib import Path

# Ensure project root on path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import BOT_TOKEN, ADMIN_ID, ADMIN_IDS, validate_config, BRAND_NAME
from database import init_db, log_event
from process_manager import check_and_auto_restart, reconcile_processes, restore_hosted_bots
from hosting_manager import process_expiries, process_expiry_reminders
from health_server import start_health_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(ROOT / "logs" / "hosting_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("rebel_crown")

_shutdown = threading.Event()


def background_worker(bot):
    """Periodic tasks: expiry, reminders, health check / auto-restart."""
    while not _shutdown.is_set():
        try:
            process_expiries(bot)
            process_expiry_reminders(bot)
            check_and_auto_restart()
        except Exception as e:
            logger.exception("Background worker error: %s", e)
            log_event("ERROR", "worker", str(e))
        _shutdown.wait(60)  # every minute, interruptible


def _handle_signal(signum, frame):
    logger.info("Received signal %s — shutting down...", signum)
    _shutdown.set()


def main():
    ok, msg = validate_config()
    if not ok:
        print(f"❌ Configuration error: {msg}")
        print("Copy .env.example to .env and set BOT_TOKEN and ADMIN_IDS.")
        sys.exit(1)

    # Graceful shutdown on SIGTERM (Docker / systemd / cloud platforms)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_signal)
        except Exception:
            pass

    print(f"👑 Initializing {BRAND_NAME} ...")
    init_db()
    print("✅ Database ready.")

    # Health HTTP server — required by Railway / Render / Fly / many PaaS
    # Binds to $PORT when set; skipped on pure local/Termux unless FORCE_HEALTH_SERVER=1
    start_health_server()

    try:
        live = reconcile_processes()
        print(f"✅ Process state reconciled ({len(live)} live).")
    except Exception as e:
        logger.warning("Process reconcile failed: %s", e)
        print(f"⚠️ Process reconcile failed: {e}")

    # After container/VPS restart, bring back hosted bots that should still run
    try:
        restored = restore_hosted_bots()
        print(
            f"✅ Hosted bots restore: started={restored['started']} "
            f"failed={restored['failed']} skipped={restored['skipped']}"
        )
    except Exception as e:
        logger.warning("Hosted bots restore failed: %s", e)
        print(f"⚠️ Hosted bots restore failed: {e}")

    import telebot
    bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

    # Register handlers
    from handlers import user, admin, deploy, referral, redeem, support
    user.register(bot)
    admin.register(bot)
    deploy.register(bot)
    referral.register(bot)
    redeem.register(bot)
    support.register(bot)

    # Fallback for unknown text (keep keyboard alive)
    @bot.message_handler(func=lambda m: True, content_types=["text"])
    def fallback(message):
        from config import is_admin
        from utils import user_main_keyboard
        if message.text and message.text.startswith("/"):
            return
        # Always restore User Panel (admins open Admin via 👑 ADMIN PANEL)
        kb = user_main_keyboard(page=1, for_admin=is_admin(message.from_user.id))
        bot.send_message(
            message.chat.id,
            "Use the menu buttons below 👇",
            reply_markup=kb,
        )

    # Start background thread
    t = threading.Thread(target=background_worker, args=(bot,), daemon=True)
    t.start()

    log_event("INFO", "main", "Bot started")
    print(f"✅ {BRAND_NAME} is running.")
    print(f"   Admin ID(s): {', '.join(sorted(ADMIN_IDS)) or ADMIN_ID}")
    print("   Press Ctrl+C to stop.\n")

    # Polling with reconnect until shutdown signal
    while not _shutdown.is_set():
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=40, skip_pending=True)
        except KeyboardInterrupt:
            break
        except Exception as e:
            if _shutdown.is_set():
                break
            logger.exception("Polling error: %s", e)
            log_event("ERROR", "main", f"Polling: {e}")
            time.sleep(5)

    print("\n👋 Shutting down...")
    log_event("INFO", "main", "Bot stopped")
    _shutdown.set()


if __name__ == "__main__":
    main()

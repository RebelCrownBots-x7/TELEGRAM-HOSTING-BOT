"""
REBEL CROWN BOT HOSTING - Process Manager
Real Termux-compatible process control for hosted bots.
Includes PID persistence via runtime/pids.json and startup reconciliation.
"""

import os
import sys
import json
import time
import subprocess
import logging
import threading
from pathlib import Path
from datetime import datetime

from config import RUNTIME_DIR, LOGS_DIR, BASE_DIR
from database import (
    update_bot, get_bot, log_event, now_iso, get_running_bots, get_all_bots,
    add_hosting_history, get_setting,
)
from security import decrypt_token

logger = logging.getLogger("process_manager")

PIDS_FILE = RUNTIME_DIR / "pids.json"
_pid_lock = threading.Lock()


def _runtime_dir(user_id: int, bot_id: str) -> Path:
    p = RUNTIME_DIR / str(user_id) / bot_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _log_dir(user_id: int, bot_id: str) -> Path:
    p = LOGS_DIR / str(user_id) / bot_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _pid_file(user_id: int, bot_id: str) -> Path:
    return _runtime_dir(user_id, bot_id) / "bot.pid"


def _env_file(user_id: int, bot_id: str) -> Path:
    return _runtime_dir(user_id, bot_id) / "bot.env"


# ─── PID registry (runtime/pids.json) ───

def _load_pids() -> dict:
    if not PIDS_FILE.exists():
        return {}
    try:
        data = json.loads(PIDS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_pids(data: dict):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PIDS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(PIDS_FILE)


def register_pid(bot_id: str, user_id: int, pid: int):
    with _pid_lock:
        data = _load_pids()
        data[bot_id] = {
            "pid": pid,
            "user_id": user_id,
            "started_at": datetime.utcnow().isoformat(),
        }
        _save_pids(data)


def unregister_pid(bot_id: str):
    with _pid_lock:
        data = _load_pids()
        if bot_id in data:
            del data[bot_id]
            _save_pids(data)


def write_bot_env(user_id: int, bot_id: str, bot_token: str):
    """Write isolated env for the hosted bot (only its own token)."""
    env_path = _env_file(user_id, bot_id)
    content = f"BOT_TOKEN={bot_token}\n"
    env_path.write_text(content, encoding="utf-8")
    try:
        os.chmod(env_path, 0o600)
    except Exception:
        pass
    return env_path


def is_process_running(pid: int) -> bool:
    """Termux-compatible: check /proc/<pid> (no psutil)."""
    if not pid or pid <= 0:
        return False
    proc = Path(f"/proc/{pid}")
    if not proc.exists():
        return False
    # Exclude zombies when possible
    try:
        status = (proc / "status").read_text(encoding="utf-8", errors="ignore")
        for line in status.splitlines():
            if line.startswith("State:"):
                state = line.split(":", 1)[1].strip()
                # Z = zombie
                if state.startswith("Z"):
                    return False
                break
    except Exception:
        pass
    return True


def get_process_info(pid: int) -> dict:
    """Read process info from /proc (Termux-compatible, no psutil)."""
    info = {"pid": pid, "status": "unknown", "cpu_percent": None, "memory_mb": None, "create_time": None}
    if not is_process_running(pid):
        return info
    try:
        status_txt = Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="ignore")
        for line in status_txt.splitlines():
            if line.startswith("State:"):
                info["status"] = line.split(":", 1)[1].strip().split()[0]
            elif line.startswith("VmRSS:"):
                # kB
                parts = line.split()
                if len(parts) >= 2:
                    info["memory_mb"] = round(int(parts[1]) / 1024, 2)
    except Exception:
        pass
    try:
        # starttime from /proc/pid/stat field 22 (ticks since boot)
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="ignore")
        # comm can contain spaces in parens — take after last ')'
        after = stat.rsplit(")", 1)[-1].strip().split()
        if len(after) >= 20:
            start_ticks = int(after[19])  # field 22 overall, index 19 after state fields post-comm
            hz = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK")) if hasattr(os, "sysconf") else 100
            try:
                uptime = float(Path("/proc/uptime").read_text().split()[0])
                start_ago = uptime - (start_ticks / float(hz or 100))
                info["create_time"] = datetime.fromtimestamp(time.time() - max(0, start_ago)).isoformat()
            except Exception:
                pass
    except Exception:
        pass
    return info


def _resolve_live_pid(bot: dict) -> int:
    """Find a live PID from DB, pid file, or pids.json — without starting anything."""
    candidates = []
    if bot.get("pid"):
        candidates.append(int(bot["pid"]))
    user_id = bot["user_id"]
    bot_id = bot["bot_id"]
    pid_path = _pid_file(user_id, bot_id)
    if pid_path.exists():
        try:
            candidates.append(int(pid_path.read_text().strip()))
        except Exception:
            pass
    registry = _load_pids().get(bot_id) or {}
    if registry.get("pid"):
        candidates.append(int(registry["pid"]))
    for pid in candidates:
        if is_process_running(pid):
            return pid
    return 0


def reconcile_processes():
    """
    On main bot startup:
    - Load saved process information
    - Check whether processes still exist
    - Reconcile DB status vs live PIDs
    - Remove stale PID records
    - Do NOT start or kill unrelated processes

    Bots that *should* still be running (previous status RUNNING, not
    manual_stop, not expired) are left with status RUNNING and pid=None
    so restore_hosted_bots() / check_and_auto_restart can bring them back
    after a host/container restart.
    """
    logger.info("Reconciling process state...")
    with _pid_lock:
        registry = _load_pids()
        cleaned = {}

        # Check all bots that claim RUNNING or appear in registry
        bots_by_id = {b["bot_id"]: b for b in get_all_bots(2000)}
        all_ids = set(registry.keys()) | {
            b["bot_id"] for b in bots_by_id.values() if b.get("status") == "RUNNING"
        }

        for bot_id in all_ids:
            bot = bots_by_id.get(bot_id)
            if not bot:
                # Orphan registry entry
                continue
            if bot.get("status") == "EXPIRED" or bot.get("status") == "DELETED":
                continue

            live = _resolve_live_pid(bot)
            if live:
                cleaned[bot_id] = {
                    "pid": live,
                    "user_id": bot["user_id"],
                    "started_at": (registry.get(bot_id) or {}).get("started_at")
                    or datetime.utcnow().isoformat(),
                }
                if bot.get("status") != "RUNNING" or bot.get("pid") != live:
                    update_bot(bot_id, status="RUNNING", pid=live)
                    pid_path = _pid_file(bot["user_id"], bot_id)
                    try:
                        pid_path.write_text(str(live), encoding="utf-8")
                    except Exception:
                        pass
            else:
                # Process gone (common after VPS/container restart).
                # Keep status=RUNNING if it should auto-come back; otherwise STOPPED.
                should_restore = (
                    bot.get("status") == "RUNNING"
                    and not bot.get("manual_stop")
                    and get_setting("auto_restart", "1") == "1"
                    and bot.get("auto_restart", 1)
                )
                if should_restore:
                    update_bot(bot_id, status="RUNNING", pid=None, last_check=now_iso())
                elif bot.get("status") == "RUNNING":
                    update_bot(bot_id, status="STOPPED", pid=None, last_check=now_iso())
                pid_path = _pid_file(bot["user_id"], bot_id)
                if pid_path.exists():
                    try:
                        pid_path.unlink()
                    except Exception:
                        pass

        _save_pids(cleaned)
        log_event("INFO", "process_manager", f"Reconciled {len(cleaned)} live process(es)")
        logger.info("Reconcile done: %d live process(es)", len(cleaned))
        return cleaned


def restore_hosted_bots(limit: int = 50) -> dict:
    """
    After reconcile, start any bot that should be running but has no live PID.
    Used on main process startup so hosted bots survive host/container restarts.
    Returns {"started": n, "failed": n, "skipped": n}.
    """
    stats = {"started": 0, "failed": 0, "skipped": 0}
    global_auto = get_setting("auto_restart", "1") == "1"
    if not global_auto:
        logger.info("restore_hosted_bots: auto_restart disabled, skipping")
        return stats

    candidates = []
    for bot in get_all_bots(2000):
        if bot.get("status") not in ("RUNNING", "STOPPED", "CRASHED", "RESTARTING"):
            continue
        if bot.get("status") in ("EXPIRED", "DELETED"):
            continue
        if bot.get("manual_stop"):
            stats["skipped"] += 1
            continue
        if not bot.get("auto_restart", 1):
            stats["skipped"] += 1
            continue
        # Prefer bots that claimed they should be up
        if bot.get("status") == "RUNNING" or (
            bot.get("status") in ("STOPPED", "CRASHED") and not bot.get("manual_stop")
            and bot.get("last_successful_start")
        ):
            # Only auto-restore previous RUNNING after host restart.
            # STOPPED/CRASHED without live process stay stopped unless status is RUNNING.
            if bot.get("status") != "RUNNING":
                stats["skipped"] += 1
                continue
            candidates.append(bot)

    logger.info("restore_hosted_bots: %d candidate(s)", len(candidates))
    for bot in candidates[:limit]:
        bot_id = bot["bot_id"]
        live = _resolve_live_pid(bot)
        if live:
            stats["skipped"] += 1
            continue
        ok, msg = start_bot(bot_id, clear_manual_stop=False)
        if ok:
            stats["started"] += 1
            log_event("INFO", "process_manager", f"Restored bot {bot_id} after host restart", bot["user_id"])
        else:
            stats["failed"] += 1
            log_event("ERROR", "process_manager", f"Restore failed {bot_id}: {msg}", bot["user_id"])
    return stats


def start_bot(bot_id: str, *, clear_manual_stop: bool = True) -> tuple[bool, str]:
    """Start a hosted bot process. Prevents duplicate processes."""
    bot = get_bot(bot_id)
    if not bot:
        return False, "Bot not found"
    if bot["status"] == "EXPIRED":
        return False, "Hosting has expired"
    if bot["status"] == "DELETED":
        return False, "Bot was deleted"

    # Prevent duplicate: if anything is already live, refuse
    live = _resolve_live_pid(bot)
    if live:
        update_bot(
            bot_id, status="RUNNING", pid=live, last_check=now_iso(),
            last_successful_start=bot.get("last_successful_start") or now_iso(),
            manual_stop=0 if clear_manual_stop else bot.get("manual_stop") or 0,
        )
        register_pid(bot_id, bot["user_id"], live)
        return True, "Bot is already running"

    user_id = bot["user_id"]
    file_path = Path(bot["file_path"])
    if not file_path.exists():
        update_bot(bot_id, status="ERROR", last_error="Bot file missing", last_check=now_iso())
        return False, "Bot file missing"

    token = decrypt_token(bot.get("bot_token_encrypted") or "")
    if not token:
        update_bot(bot_id, status="ERROR", last_error="Token unavailable", last_check=now_iso())
        return False, "Bot token unavailable"

    update_bot(bot_id, status="STARTING", last_check=now_iso(),
               manual_stop=0 if clear_manual_stop else (bot.get("manual_stop") or 0))

    runtime = _runtime_dir(user_id, bot_id)
    log_dir = _log_dir(user_id, bot_id)
    stdout_log = log_dir / "stdout.log"
    stderr_log = log_dir / "stderr.log"
    pid_path = _pid_file(user_id, bot_id)

    write_bot_env(user_id, bot_id, token)

    env = os.environ.copy()
    for key in ("BOT_TOKEN", "ADMIN_ID", "SECRET_KEY", "ADMIN_IDS"):
        env.pop(key, None)
    env["BOT_TOKEN"] = token
    env["PYTHONUNBUFFERED"] = "1"
    env["HOME"] = str(runtime)

        import shutil
    file_type = (bot.get("file_type") or "PY").upper()

    # file_type যাই হোক না কেন, পাথটি যদি ফোল্ডার হয় তবে সিস্টেম একে ZIP প্রোজেক্ট হিসেবেই রান করবে
    if file_path.is_dir():
        entry_rel = bot.get("entry_file") or "main.py"

        project_in_runtime = runtime / "project"
        try:
            if project_in_runtime.exists():
                shutil.rmtree(project_in_runtime, ignore_errors=True)
            shutil.copytree(file_path, project_in_runtime)
        except Exception as e:
            update_bot(bot_id, status="ERROR", last_error=str(e)[:500], last_check=now_iso())
            return False, f"Cannot prepare project: {e}"
        script_in_runtime = project_in_runtime / entry_rel
        run_cwd = project_in_runtime
        if not script_in_runtime.exists():
            update_bot(bot_id, status="ERROR", last_error=f"Entry missing: {entry_rel}", last_check=now_iso())
            return False, f"Entry file missing after copy: {entry_rel}"
    else:
        script_in_runtime = runtime / "bot_main.py"
        try:
            if script_in_runtime.exists() or script_in_runtime.is_symlink():
                script_in_runtime.unlink()
            shutil.copy2(file_path, script_in_runtime)
        except Exception as e:
            update_bot(bot_id, status="ERROR", last_error=str(e)[:500], last_check=now_iso())
            return False, f"Cannot prepare script: {e}"
        run_cwd = runtime

    stdout_f = None
    stderr_f = None
    try:
        stdout_f = open(stdout_log, "a", encoding="utf-8")
        stderr_f = open(stderr_log, "a", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "-u", str(script_in_runtime)],
            cwd=str(run_cwd),
            env=env,
            stdout=stdout_f,
            stderr=stderr_f,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            stdout_f.close()
            stderr_f.close()
        except Exception:
            pass

        pid = proc.pid
        # Brief settle — catch instant crashes
        time.sleep(0.4)
        if not is_process_running(pid):
            update_bot(
                bot_id, status="CRASHED", pid=None,
                last_error="Process exited immediately after start",
                last_crash=now_iso(), last_check=now_iso(),
                crash_count=(bot.get("crash_count") or 0) + 1,
            )
            unregister_pid(bot_id)
            add_hosting_history(bot_id, user_id, "CRASHED", "Immediate exit after start")
            log_event("ERROR", "process_manager", f"Immediate crash {bot_id}", user_id)
            return False, "Bot process exited immediately (check logs)"

        pid_path.write_text(str(pid), encoding="utf-8")
        now = now_iso()
        update_bot(
            bot_id, status="RUNNING", pid=pid,
            last_successful_start=now, last_check=now,
            last_error=None, manual_stop=0 if clear_manual_stop else (bot.get("manual_stop") or 0),
        )
        register_pid(bot_id, user_id, pid)
        add_hosting_history(bot_id, user_id, "STARTED", f"pid={pid}")
        log_event("INFO", "process_manager", f"Started bot {bot_id}", user_id)
        return True, "Started successfully"
    except Exception as e:
        if stdout_f:
            try:
                stdout_f.close()
            except Exception:
                pass
        if stderr_f:
            try:
                stderr_f.close()
            except Exception:
                pass
        update_bot(bot_id, status="ERROR", last_error=str(e)[:500], last_check=now_iso())
        add_hosting_history(bot_id, user_id, "ERROR", str(e)[:200])
        log_event("ERROR", "process_manager", f"Start failed {bot_id}: {e}", user_id)
        return False, f"Start failed: {e}"


def stop_bot(bot_id: str, force: bool = False, manual: bool = True) -> tuple[bool, str]:
    """Stop a hosted bot. manual=True marks intentional stop (blocks auto-restart)."""
    bot = get_bot(bot_id)
    if not bot:
        return False, "Bot not found"
    user_id = bot["user_id"]
    pid = _resolve_live_pid(bot)
    pid_path = _pid_file(user_id, bot_id)

    if not pid:
        update_bot(
            bot_id, status="STOPPED", pid=None, last_check=now_iso(),
            manual_stop=1 if manual else (bot.get("manual_stop") or 0),
        )
        unregister_pid(bot_id)
        if pid_path.exists():
            try:
                pid_path.unlink()
            except Exception:
                pass
        return True, "Already stopped"

    try:
        import signal as _signal
        if force:
            os.kill(pid, _signal.SIGKILL)
        else:
            os.kill(pid, _signal.SIGTERM)
            deadline = time.time() + 8
            while time.time() < deadline:
                if not is_process_running(pid):
                    break
                time.sleep(0.25)
            if is_process_running(pid):
                os.kill(pid, _signal.SIGKILL)
                time.sleep(0.5)
    except ProcessLookupError:
        pass
    except PermissionError as e:
        log_event("ERROR", "process_manager", f"Stop permission error {bot_id}: {e}", user_id)
    except Exception as e:
        log_event("ERROR", "process_manager", f"Stop error {bot_id}: {e}", user_id)

    if pid_path.exists():
        try:
            pid_path.unlink()
        except Exception:
            pass
    update_bot(
        bot_id, status="STOPPED", pid=None, last_check=now_iso(),
        manual_stop=1 if manual else 0,
    )
    unregister_pid(bot_id)
    add_hosting_history(bot_id, user_id, "STOPPED", "manual" if manual else "system")
    log_event("INFO", "process_manager", f"Stopped bot {bot_id}", user_id)
    return True, "Stopped"


def restart_bot(bot_id: str) -> tuple[bool, str]:
    bot = get_bot(bot_id)
    if not bot:
        return False, "Bot not found"
    if bot.get("status") == "EXPIRED":
        return False, "Hosting has expired"
    update_bot(bot_id, status="RESTARTING", last_check=now_iso())
    stop_bot(bot_id, manual=False)
    time.sleep(1)
    ok, msg = start_bot(bot_id, clear_manual_stop=True)
    if ok:
        bot = get_bot(bot_id)
        if bot:
            update_bot(bot_id, restart_count=(bot.get("restart_count") or 0) + 1)
            add_hosting_history(bot_id, bot["user_id"], "RESTARTED", msg)
    return ok, msg


def get_bot_status(bot_id: str) -> dict:
    """Health snapshot. Syncs DB status with live process state. Never exposes secrets."""
    bot = get_bot(bot_id)
    if not bot:
        return {"error": "not found"}
    pid = _resolve_live_pid(bot)
    running = bool(pid)
    info = {
        "bot_id": bot_id,
        "db_status": bot["status"],
        "running": running,
        "expiry_date": bot.get("expiry_date"),
        "days": bot.get("days"),
        "restart_count": bot.get("restart_count") or 0,
        "crash_count": bot.get("crash_count") or 0,
        "last_error": bot.get("last_error"),
        "last_check": bot.get("last_check"),
        "last_successful_start": bot.get("last_successful_start"),
        "last_crash": bot.get("last_crash"),
        "manual_stop": bot.get("manual_stop") or 0,
        "filename": bot.get("filename") or bot.get("name"),
        "user_id": bot.get("user_id"),
        "start_date": bot.get("start_date"),
    }
    if running:
        pinfo = get_process_info(pid)
        # Intentionally omit raw PID from the public-facing dict for safety
        info["process_state"] = pinfo.get("status")
        info["memory_mb"] = pinfo.get("memory_mb")
        if bot.get("status") not in ("RUNNING",) or bot.get("pid") != pid:
            update_bot(bot_id, status="RUNNING", pid=pid, last_check=now_iso())
            info["db_status"] = "RUNNING"
        else:
            update_bot(bot_id, last_check=now_iso())
    else:
        if bot["status"] == "RUNNING":
            # Process died — leave auto-restart to check_and_auto_restart
            update_bot(bot_id, status="STOPPED", pid=None, last_check=now_iso())
            unregister_pid(bot_id)
            info["db_status"] = "STOPPED"
        else:
            update_bot(bot_id, last_check=now_iso())
    return info


def read_logs(bot_id: str, lines: int = 50, stream: str = "stderr") -> str:
    bot = get_bot(bot_id)
    if not bot:
        return "Bot not found"
    log_dir = _log_dir(bot["user_id"], bot_id)
    path = log_dir / f"{stream}.log"
    if not path.exists():
        alt = log_dir / ("stdout.log" if stream == "stderr" else "stderr.log")
        if alt.exists():
            path = alt
        else:
            return "(no logs yet)"
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.readlines()
        return "".join(content[-lines:]) or "(empty)"
    except Exception as e:
        return f"Error reading logs: {e}"


def check_and_auto_restart():
    """
    Detect dead processes that claim RUNNING and auto-restart when allowed.
    Crash protection: after max_crash_restarts within crash_window_minutes,
    mark CRASHED and stop retrying until a manual start/restart.
    Never restart EXPIRED, DELETED, or intentionally STOPPED (manual_stop=1) bots.
    """
    max_restarts = int(get_setting("max_crash_restarts", 5) or 5)
    window_min = int(get_setting("crash_window_minutes", 30) or 30)
    global_auto = get_setting("auto_restart", "1") == "1"

    for bot in get_running_bots():
        bot_id = bot["bot_id"]
        user_id = bot["user_id"]
        try:
            if bot.get("status") in ("EXPIRED", "DELETED"):
                continue
            # Intentionally stopped by user/admin — do not auto-restart
            if bot.get("manual_stop"):
                continue
            if not global_auto or not bot.get("auto_restart", 1):
                pid = _resolve_live_pid(bot)
                if not pid and bot.get("status") == "RUNNING":
                    update_bot(bot_id, status="STOPPED", pid=None, last_check=now_iso())
                    unregister_pid(bot_id)
                continue

            pid = _resolve_live_pid(bot)
            if pid:
                update_bot(bot_id, last_check=now_iso())
                continue

            # Dead process while status claimed RUNNING
            crash_count = (bot.get("crash_count") or 0) + 1
            last_crash = bot.get("last_crash")
            within_window = False
            if last_crash:
                try:
                    from datetime import datetime, timedelta
                    lc = datetime.fromisoformat(last_crash)
                    within_window = (datetime.utcnow() - lc) < timedelta(minutes=window_min)
                except Exception:
                    within_window = False

            # If crashes pile up inside the window, stop retrying
            effective_crashes = crash_count if within_window else 1
            if effective_crashes > max_restarts:
                update_bot(
                    bot_id, status="CRASHED", pid=None,
                    crash_count=crash_count, last_crash=now_iso(),
                    last_error=f"Exceeded {max_restarts} restarts in {window_min}m",
                    last_check=now_iso(),
                )
                unregister_pid(bot_id)
                add_hosting_history(
                    bot_id, user_id, "CRASHED",
                    f"Crash protection: {crash_count} crashes"
                )
                log_event(
                    "ERROR", "process_manager",
                    f"Crash protection tripped for {bot_id}", user_id,
                )
                continue

            log_event(
                "WARN", "process_manager",
                f"Bot {bot_id} crashed, auto-restart attempt #{effective_crashes}",
                user_id,
            )
            update_bot(
                bot_id,
                status="RESTARTING",
                last_crash=now_iso(),
                crash_count=crash_count if within_window else 1,
                restart_count=(bot.get("restart_count") or 0) + 1,
                last_check=now_iso(),
            )
            add_hosting_history(bot_id, user_id, "CRASHED", "Process died; auto-restart")
            ok, msg = start_bot(bot_id, clear_manual_stop=False)
            if not ok:
                update_bot(
                    bot_id, status="CRASHED",
                    last_error=(msg or "auto-restart failed")[:500],
                    last_check=now_iso(),
                )
                add_hosting_history(bot_id, user_id, "ERROR", f"Auto-restart failed: {msg}")
        except Exception as e:
            log_event("ERROR", "process_manager", f"auto-restart loop error {bot_id}: {e}", user_id)


def expire_bot(bot_id: str):
    bot = get_bot(bot_id)
    stop_bot(bot_id, force=True, manual=False)
    update_bot(bot_id, status="EXPIRED", pid=None, last_check=now_iso())
    unregister_pid(bot_id)
    if bot:
        add_hosting_history(bot_id, bot["user_id"], "EXPIRED", "Hosting period ended")
    log_event("INFO", "process_manager", f"Bot {bot_id} expired and stopped")

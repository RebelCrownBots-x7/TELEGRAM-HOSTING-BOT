# 👑 REBEL CROWN BOT HOSTING

**Professional Telegram Bot Hosting Platform**

Host user-submitted Python Telegram bots with manual admin approval, process management, credits, referrals, redeem codes, and full admin control.

Works on:
- **VPS / dedicated Linux** (recommended for 24/7)
- **Docker** (easiest production setup)
- **Railway / Render / Fly.io** (with persistent disk)
- **Termux** (Android — original target)

> Uploaded user bots run as real OS processes. Free serverless platforms without persistent disk or long-running processes are **not** suitable.

---

## Features

- 🚀 User bot deployment (`.py` or ZIP project + token)
- ⏳ Manual admin approval workflow (or auto-accept)
- 🖥️ Real process management (start / stop / restart / logs)
- 🔁 **Auto-restore hosted bots after host/container restart**
- ❤️ Built-in **HTTP health server** (`/health`) for cloud platforms that require `$PORT`
- 🎁 Free hosting (configurable)
- 🔗 Referral system with rewards
- 💰 Credits & redeem codes
- 🎫 Support tickets
- 👑 Full admin panel
- 🔐 Token encryption, path safety, ownership checks
- 🗄️ SQLite persistence

---

## Quick start — Docker (recommended for online)

```bash
# 1. Put project on your server
git clone <your-repo> && cd HOSTING   # or upload the folder

# 2. Config
cp .env.example .env
nano .env   # set BOT_TOKEN and ADMIN_IDS

# 3. Run
docker compose up -d --build

# 4. Logs
docker compose logs -f
```

Data lives in `./data`, `./storage`, `./runtime`, `./logs` (bind-mounted).  
Safe to rebuild the image — user bots and DB survive.

Stop: `docker compose down`  
Update: `git pull && docker compose up -d --build`

---

## Quick start — VPS without Docker

```bash
# Ubuntu/Debian example
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git

git clone <your-repo> rebel_crown && cd rebel_crown
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
nano .env   # BOT_TOKEN + ADMIN_IDS

chmod +x start.sh
./start.sh
```

### Keep running with systemd

```bash
sudo nano /etc/systemd/system/rebel-crown.service
```

```ini
[Unit]
Description=REBEL CROWN Bot Hosting
After=network.target

[Service]
Type=simple
User=YOUR_LINUX_USER
WorkingDirectory=/home/YOUR_LINUX_USER/rebel_crown
Environment=PYTHONUNBUFFERED=1
# Optional health port if you put nginx in front
# Environment=PORT=8080
# Environment=FORCE_HEALTH_SERVER=1
ExecStart=/home/YOUR_LINUX_USER/rebel_crown/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now rebel-crown
sudo systemctl status rebel-crown
```

---

## Railway / Render / similar PaaS

1. Create a new project from this repo (Dockerfile is included).
2. Set env vars: `BOT_TOKEN`, `ADMIN_IDS`.
3. **Attach a persistent disk / volume** mounted at least on:
   - `/app/data`
   - `/app/storage`
   - `/app/runtime`
   - `/app/logs`  
   Without a volume, every redeploy wipes the database and user bots.
4. The app binds health checks to `$PORT` automatically (`GET /health`).
5. Prefer a paid always-on plan. Free tiers that sleep will stop all hosted user bots.

`railway.toml` and `render.yaml` are included as starting points.

---

## Termux (Android)

```bash
pkg update -y && pkg upgrade -y
pkg install python git -y
cd ~
# upload or clone project
cd HOSTING
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env
python main.py
```

Background:

```bash
nohup python main.py > logs/nohup.out 2>&1 &
# or: pkg install tmux && tmux new -s rebel
```

Disable battery optimization for Termux. For true 24/7, use a VPS.

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | Yes | Hosting bot token from @BotFather |
| `ADMIN_IDS` | Yes | Your Telegram numeric user ID(s), comma-separated |
| `PORT` | Auto | Set by cloud platforms; health server binds here |
| `HEALTH_SERVER` | No | `1` (default) / `0` to disable health HTTP |
| `FORCE_HEALTH_SERVER` | No | `1` to start health server even without `PORT` |
| `BRAND_NAME` | No | Display name |
| `WHATSAPP_NUMBER` / `TELEGRAM_SUPPORT` | No | Support contacts |

Copy `.env.example` → `.env` for local/Docker. On PaaS, set the same keys in the dashboard.

---

## Project structure

```
HOSTING/
├── main.py              # Entry + polling + restore on startup
├── health_server.py     # /health for cloud platforms
├── config.py
├── database.py
├── hosting_manager.py
├── process_manager.py   # start/stop/restart + restore after reboot
├── security.py
├── utils.py
├── Dockerfile
├── docker-compose.yml
├── start.sh
├── requirements.txt
├── handlers/
├── data/                # SQLite (persist this)
├── storage/             # User files (persist this)
├── runtime/             # PIDs / per-bot runtime (persist this)
└── logs/
```

---

## Admin usage

1. Message your hosting bot on Telegram.
2. Admin ID gets the admin keyboard.
3. User deploys → you get file + **APPROVE / REJECT**.
4. Approve → set days → process starts.
5. **⚙️ CUSTOMIZE** for free days, rewards, support text (`key=value`).

---

## Security notes

- Hosted scripts only receive their own `BOT_TOKEN` in the environment.
- Main `.env` and other users’ files are path-isolated under `storage/users/<id>/`.
- Tokens encrypted at rest. Full tokens never shown in UI/logs/exports.
- Upload size limits + ZIP bomb guards.
- **No OS sandbox** on plain Termux/VPS user account. Review every file before approve. For strong isolation use containers per user or separate OS users.

---

## Troubleshooting (online host)

| Problem | Fix |
|---------|-----|
| Platform says “no open port” / app killed | Health server must bind `$PORT`. Do not set `HEALTH_SERVER=0`. |
| DB / bots vanish after redeploy | Mount persistent volumes for `data`, `storage`, `runtime`, `logs`. |
| User bots die after restart | Fixed in this build: `restore_hosted_bots()` runs on startup. Ensure `auto_restart=1` in settings. |
| Instant crash on start | Check per-bot logs under `logs/<user_id>/<bot_id>/`. Missing deps in user script, bad token, etc. |
| `BOT_TOKEN is not set` | Create `.env` or set platform env vars. |

---

## Disclaimer

Running untrusted Python code carries risk. **Always review uploaded files before approving.**  
Software provided as-is for educational and self-hosting purposes.

---

**REBEL CROWN 👑 BOT HOSTING**

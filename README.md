# Status Bot

Status Bot is a private Telegram assistant that keeps a Raspberry Pi and a desktop PC under control. It exposes a single-user command interface for telemetry, file downloads, git automation, and remote Stable Diffusion management.

## Highlights
- One keyboard-driven menu for PC power control, Raspberry Pi health, log management, SD WebUI actions, and quick download helpers (YouTube, TikTok, Instagram).
- Background monitors send proactive alerts about CPU temperature, Wi-Fi dropouts, and morning status digests with weather, currency, and uptime snapshots.
- WebUI helpers can start/stop the remote instance, read logs, and forward on-demand generations back to Telegram.
- Social media fetcher stores artifacts in `downloads/` and trims them automatically to avoid disk bloat.

## Security Posture
- Every handler is wrapped with `only_owner`, so the bot replies exclusively to the Telegram user ID defined in `MY_ID`.
- Secrets (API keys, SSH credentials, MAC/IP addresses, etc.) are loaded from environment variables or a local `.env`; nothing sensitive is committed to the repository.
- SSH operations rely on a key pair mounted at runtime plus the bundled `known_hosts`, keeping host verification intact even when the repo is public.
- Unauthorized messages are appended to the log file, and the rotating cleaner keeps the file from exposing old data.
- `/exec` remains enabled for convenience, so keep the bot token and Telegram account secure; anyone with full access to either could run arbitrary shell commands.

## Configuration
Key environment variables (set them in `.env` or your orchestrator):
- `SSH_USER`, `SSH_KEY_PATH`, and `PC_IP`/`PC_MAC` — remote host credentials for WOL + SSH; `SSH_KEY_PATH` must exist within the container.
- `WEBUI_BASE` — path to the remote WebUI helper scripts.
- `UPDATE_SCRIPT_PATH` — absolute path inside the container to the site update script (ensure the volume mount matches).
- `WAKE_TRIGGER_BASE` — base URL (without the `?key=` suffix) for the wake trigger endpoint; combined with `SECRET_KEY` at runtime.
- `SSH_KEY_VOLUME`/`SSH_KEY_CONTAINER_PATH` and `SITE_REPO_VOLUME`/`SITE_REPO_CONTAINER_PATH` — docker-compose volume pairs so you can map host paths without exposing them in source control.

## Getting Started
1. Install Python 3.11 (or build the Docker image) and install dependencies with `pip install -r requirements.txt`.
2. Provide the required environment variables (Telegram token, `MY_ID`, SSH/PC details, OpenWeather and currency keys, log file path, etc.) via `.env` or your container orchestration.
3. Run the bot with `python main.py` or use `docker compose up -d` once the environment variables and SSH key volume mounts are in place.

The repository intentionally omits any secrets; configure them locally before publishing the project publicly.

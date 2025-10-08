import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, FSInputFile
from aiogram.filters import Command
from os import getenv, popen, path, makedirs
import os
from dotenv import load_dotenv
from functools import wraps
from wakeonlan import send_magic_packet
import psutil
import platform
import time
import socket
import subprocess
import re
import requests
from datetime import datetime, timedelta
from social_media import SocialMediaDownloader

load_dotenv()

TOKEN = getenv("BOT_TOKEN")
MY_ID = int(getenv("MY_ID"))
PC_MAC = getenv("PC_MAC")
PC_IP = getenv("PC_IP")
SECRET_KEY = getenv("SECRET_KEY")
OPENWEATHER_KEY = getenv("OPENWEATHER_KEY")
CITY_ID = getenv("CITY_ID")
LOG_FILE_PATH = getenv("LOG_FILE_PATH")

log_dir = path.dirname(LOG_FILE_PATH)

makedirs(log_dir, exist_ok=True)

if not path.exists(LOG_FILE_PATH):
    with open(LOG_FILE_PATH, "w") as f:
        f.write(f"[{datetime.now()}] Log file created automatically.\n")

pending_update_confirmation = {}

dp = Dispatcher()


# ---- WebUI remote control helpers ----
SSH_KEY = "/root/.ssh/myPc_ed25519"
SSH_USER = "finler6"
WEBUI_BASE = "/mnt/c/Users/finle/Desktop/testAI/stable-diffusion-webui"

def ssh_run_raw(cmd, timeout=30):
    full_cmd = [
        "ssh",
        "-i", SSH_KEY,
        f"{SSH_USER}@{PC_IP}",
        "bash",
        "-lc",
        cmd
    ]
    try:
        p = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired as e:
        return 124, "", f"Timeout after {timeout}s"

def ssh_run_script(script_name, timeout=30):
    remote = f"'{WEBUI_BASE}/{script_name}'"
    cmd = f"bash -lc {remote}"
    rc, out, err = ssh_run_raw(cmd, timeout=timeout)
    return rc, out, err

def call_remote_sdapi(prompt, width=512, height=512, steps=20, cfg=7.0, model=None, lora_prefix=None, timeout=120):
    sd_url = f"http://{PC_IP}:7860/sdapi/v1/txt2img"
    final_prompt = f"{(lora_prefix + ' ') if lora_prefix else ''}{prompt}"
    payload = {
        "prompt": final_prompt,
        "negative_prompt": "",
        "steps": steps,
        "cfg_scale": cfg,
        "width": width,
        "height": height,
        "batch_size": 1,
        "n_iter": 1,
    }
    if model:
        payload["sd_model_checkpoint"] = model
    try:
        r = requests.post(sd_url, json=payload, timeout=timeout)
        r.raise_for_status()
        return True, r.json()
    except Exception as e:
        return False, str(e)

#----------Addons-------------

def wake_pc():
    send_magic_packet(PC_MAC)

def get_uptime():
    return time.time() - psutil.boot_time()

def is_morning():
    now = datetime.now().time()
    return now.hour >= 6 and now.hour < 12

def weather_icon(description: str) -> str:
    desc = description.lower()
    if "clear" in desc:
        return "☀️"
    elif "cloud" in desc:
        if "few" in desc:
            return "🌤️"
        elif "scattered" in desc:
            return "🌥️"
        elif "broken" in desc or "overcast" in desc:
            return "☁️"
    elif "rain" in desc:
        if "light" in desc:
            return "🌦️"
        else:
            return "🌧️"
    elif "thunderstorm" in desc:
        return "⛈️"
    elif "snow" in desc:
        return "❄️"
    elif "mist" in desc or "fog" in desc:
        return "🌫️"
    return "⚠️"

def interpret_cloudiness(cloud_pct: int) -> str:
    if cloud_pct < 10:
        return "☀️ Clear"
    elif cloud_pct < 25:
        return "🌤️ Few clouds"
    elif cloud_pct < 50:
        return "🌥️ Scattered clouds"
    elif cloud_pct < 85:
        return "☁️ Broken clouds"
    else:
        return "☁️ Overcast"

def format_bytes(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"

def is_wifi_connected():
    result = subprocess.getoutput("ip addr show wlan0")
    return "inet " in result

def get_cpu_temperature():
    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
        return int(f.read()) / 1000

def only_owner(handler):
    @wraps(handler)
    async def wrapper(message: Message, *args, **kwargs):
        if message.from_user.id != MY_ID:
            with open(LOG_FILE_PATH, "a") as f:
                f.write(f"[{datetime.now()}] Unauthorized access by ID {message.from_user.id}, "
                        f"username: @{message.from_user.username}, text: {message.text}\n")
            await message.answer("Access denied 🙅‍♂️")
            return
        return await handler(message, *args, **kwargs)
    return wrapper

def get_disk_temperature(dev="/dev/sda"):
    try:
        result = subprocess.getoutput(f"smartctl -A -d sat {dev}")
        for line in result.splitlines():
            if "Temperature_Celsius" in line:
                match = re.search(r"-\s+(\d+)", line)
                if match:
                    return f"{match.group(1)} °C"
                return line.strip()
        return "Temperature not found"
    except Exception as e:
        return f"Error: {e}"

def is_pc_online(ip=PC_IP):
    try:
        socket.setdefaulttimeout(1)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((ip, 22))
        return True
    except:
        return False

#---------/Addons-------------

async def temperature_watcher(bot: Bot, threshold: float, chat_id: int):
    notified = False
    while True:
        temp = get_cpu_temperature()
        if temp > threshold and not notified:
            await bot.send_message(chat_id, f"🔥 Warning! Temperature {temp}°C exceeded threshold {threshold}°C.")
            notified = True
        elif temp <= threshold and notified:
            notified = False
        await asyncio.sleep(60)

async def wifi_status(bot: Bot, chat_id: int):
    notified = False
    await asyncio.sleep(10)
    while True:
        connected = is_wifi_connected()
        if not connected and not notified:
            await bot.send_message(chat_id, f"🛜 Warning! Wi-Fi disconnected.")
            notified = True
        elif connected and notified:
            notified = False
        await asyncio.sleep(120)

async def log_cleaner():
    while True:
        now = datetime.now()
        next_clean = now.replace(minute=0, second=0, microsecond=0)
        if now.hour < 12:
            next_clean = next_clean.replace(hour=12)
        else:
            next_clean = next_clean.replace(day=now.day + 1, hour=0)
        wait_seconds = (next_clean - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        with open(LOG_FILE_PATH, "w") as f:
            f.write(f"[{datetime.now()}] Log file auto-cleared.\n")

async def morning_trigger_listener(bot: Bot):
    url = f"https://lit.vinch.uk/api/wake-trigger?key={SECRET_KEY}"
    while True:
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200 and res.json().get("wake"):
                if is_morning():
                    print("📲 Wake-up received in the morning — sending info.")
                    await send_morning_info(bot)
                else:
                    print("🌙 Wake-up received outside morning — ignored.")
        except Exception as e:
            print(f"[wake-trigger] Error: {e}")
        await asyncio.sleep(3)

async def send_morning_info(bot: Bot):
    now = datetime.now()
    weekday_map = {
    'Monday': 'Понедельник',
    'Tuesday': 'Вторник',
    'Wednesday': 'Среда',
    'Thursday': 'Четверг',
    'Friday': 'Пятница',
    'Saturday': 'Суббота',
    'Sunday': 'Воскресенье'
    }
    weekday_en = now.strftime('%A')
    weekday_ru = weekday_map.get(weekday_en, '')
    msg = f"👋 Good morning!\n📅 Today is {weekday_en} ({weekday_ru}), {now.strftime('%d %B %Y')}\n\n"


    if is_pc_online():
        msg += "🖥️ PC: online ✅\n"
    else:
        msg += "🖥️ PC: offline ❌\n"

    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    msg += f"🍓 Pi: CPU {cpu:.1f}% | RAM {ram:.1f}%\n"

    try:
        current = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather?id={CITY_ID}"
            f"&appid={OPENWEATHER_KEY}&units=metric&lang=en"
        ).json()
        obs_time = datetime.utcfromtimestamp(current['dt']).strftime('%H:%M')
        clouds = current['clouds']['all']
        temp   = round(current['main']['temp'])
        msg += f"{interpret_cloudiness(clouds)} ({clouds}% clouds, {obs_time} UTC) +{temp}°C\n"
    except:
        msg += "☀️ Weather now: N/A\n"

    try:
        forecast = requests.get(
            f"https://api.openweathermap.org/data/2.5/forecast?id={CITY_ID}"
            f"&appid={OPENWEATHER_KEY}&units=metric&lang=en"
        ).json()

        def find_forecast_hour(hours_ahead):
            target_dt = datetime.utcnow() + timedelta(hours=hours_ahead)
            for entry in forecast["list"]:
                entry_dt = datetime.utcfromtimestamp(entry["dt"])
                if entry_dt >= target_dt:
                    time_txt = (entry_dt + timedelta(hours=2)).strftime("%H:%M")
                    description = entry["weather"][0]["description"].capitalize()
                    icon = weather_icon(description)
                    temp = round(entry["main"]["temp"])
                    return f"{time_txt} - {icon} {description} +{temp}°C"
            return "N/A"

        msg += f"📆 +3h: {find_forecast_hour(3)}\n"
        msg += f"📆 +6h: {find_forecast_hour(6)}\n"
    except:
        msg += "📆 Forecast: N/A\n"

    try:
        res = requests.get("https://open.er-api.com/v6/latest/EUR", timeout=5).json()
        czk = res["rates"]["CZK"]
        rub = res["rates"]["RUB"]
        msg += f"💱 EUR: {czk:.2f} Kč | {rub:.2f} ₽"
    except:
        msg += "💱 Currency: N/A"

    await bot.send_message(chat_id=MY_ID, text=msg)

@dp.message(Command("start_pc"))
@only_owner
async def start_pc_handler(message: Message):
    try:
        wake_pc()
        await message.answer("🚀 Shutdown command sent, awaiting feedback.....")
        start_time = time.time()

        for _ in range(60):
            if is_pc_online():
                duration = round(time.time() - start_time, 2)
                await message.answer(f"✅ PC turned on in {duration} sec.")
                break
            await asyncio.sleep(1)
        else:
            await message.answer("❌ The PC did not respond within 60 seconds.")
            return

        result = subprocess.run(
            [
                "ssh", "-i", "/root/.ssh/myPc_ed25519",
                "finler6@192.168.1.126",
                "powershell -Command \"Get-CimInstance Win32_Processor | Select-Object -ExpandProperty LoadPercentage; "
                "Get-CimInstance Win32_OperatingSystem | ForEach-Object { $_.TotalVisibleMemorySize, $_.FreePhysicalMemory }; "
                "(Get-Counter '\\GPU Engine(*)\\Utilization Percentage').CounterSamples | "
                "Select-Object -First 1 -ExpandProperty CookedValue\""
            ],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            usage_lines = result.stdout.strip().splitlines()
            cpu = usage_lines[0]
            total_mem, free_mem = map(int, usage_lines[1:3])
            mem_used = (total_mem - free_mem) / total_mem * 100
            gpu = usage_lines[3] if len(usage_lines) > 3 else "N/A"

            await message.answer(
                f"📊 PC status:\n"
                f"• CPU: {cpu}%\n"
                f"• RAM: {mem_used:.1f}%\n"
                f"• GPU: {gpu}%"
            )
        else:
            await message.answer(f"⚠️ Error while receiving a download:\n<code>{result.stderr}</code>", parse_mode="HTML")

    except Exception as e:
        await message.answer(f"❌ Error:\n<code>{e}</code>", parse_mode="HTML")

@dp.message(Command("shutdown_pc"))
@only_owner
async def shutdown_pc_handler(message: Message):
    try:
        result = subprocess.run(
            [
                "ssh",
                "-i", "/root/.ssh/myPc_ed25519",
                "finler6@192.168.1.126",
                "shutdown", "/s", "/t", "0"
            ],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            await message.answer(f"❌ Shutdown Error:\n<code>{result.stderr}</code>", parse_mode="HTML")
            return

        await message.answer("🔌 Shutdown command sent. Awaiting confirmation...")

        for _ in range(60):
            if not is_pc_online():
                await message.answer("✅ The PC is successfully shut down.")
                break
            await asyncio.sleep(1)
        else:
            await message.answer("⚠️ The PC did not shut down within 60 seconds.")
    except Exception as e:
        await message.answer(f"❌ Error:\n<code>{str(e)}</code>", parse_mode="HTML")

@dp.message(Command("lock_pc"))
@only_owner
async def lock_pc_handler(message: Message):
    try:
        result = subprocess.run(
            [
                "ssh", "-i", "/root/.ssh/myPc_ed25519",
                f"finler6@{PC_IP}",
                "schtasks", "/run", "/tn", "LockNow"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="cp1251"
        )
        if result.returncode == 0:
            await message.answer("🔒  PC locked (session disconnected).")
        else:
            await message.answer(
                f"❌  Unable to lock (tsdiscon error):\n<code>{result.stderr}</code>",
                parse_mode="HTML"
            )
    except Exception as e:
        await message.answer(f"❌  Execution error:\n<code>{e}</code>", parse_mode="HTML")

@dp.message(Command("start"))
@only_owner
async def start_handler(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💻 PC Commands"), KeyboardButton(text="🍓 Pi Commands")],
            [KeyboardButton(text="🧾 Logs")]
        ],
        resize_keyboard=True
    )
    await message.answer("Choose command group:", reply_markup=keyboard)

@dp.message(F.text == "💻 PC Commands")
@only_owner
async def show_pc_commands(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/start_pc"), KeyboardButton(text="/shutdown_pc")],
            [KeyboardButton(text="/lock_pc")],
            [KeyboardButton(text="⬅ Back")]
        ],
        resize_keyboard=True
    )
    await message.answer("💻 PC Controls:", reply_markup=keyboard)


# ---- WebUI control handlers ----

@dp.message(Command("webui_start"))
@only_owner
async def webui_start_handler(message: Message):
    await message.answer("🔁 Try to run WebUI on remote PC...")
    rc, out, err = ssh_run_script("start_webui_wsl.sh", timeout=20)
    if rc == 0:
        await message.answer(f"✅ Command send\n{out or 'OK'}")
    else:
        txt = f"❌ Ошибка запуска (rc={rc}).\nOUT:\n{out}\nERR:\n{err}"
        await message.answer(txt)

@dp.message(Command("webui_stop"))
@only_owner
async def webui_stop_handler(message: Message):
    await message.answer("🔁 To stop WebUI on remote PC...")
    rc, out, err = ssh_run_script("stop_webui_wsl.sh", timeout=20)
    if rc == 0:
        await message.answer(f"✅ Stopped.\n{out or 'OK'}")
    else:
        await message.answer(f"❌ Error(rc={rc}).\nERR:\n{err}")

@dp.message(Command("webui_status"))
@only_owner
async def webui_status_handler(message: Message):
    await message.answer("🔎 Проверяю статус WebUI...")
    rc, out, err = ssh_run_script("status_webui_wsl.sh", timeout=10)
    if rc == 0:
        await message.answer(f"ℹ️ Status:\n<pre>{out}</pre>", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ Cant to resolve status (rc={rc}).\nERR:\n<code>{err}</code>", parse_mode="HTML")

@dp.message(Command("webui_log"))
@only_owner
async def webui_log_handler(message: Message):
    try:
        arg = message.text.replace("/webui_log", "").strip()
        tail = int(arg) if arg.isdigit() else 200
    except:
        tail = 200
    cmd = f"tail -n {tail} '{WEBUI_BASE}/webui.log' || echo 'log not found'"
    rc, out, err = ssh_run_raw(cmd, timeout=10)
    if rc == 0:
        if len(out) > 3900:
            out = out[-3900:]
            out = "...(truncated)...\n" + out
        await message.answer(f"<pre>{out}</pre>", parse_mode="HTML")
    else:
        await message.answer(f"Ошибка чтения лога: <code>{err}</code>", parse_mode="HTML")

@dp.message(Command("webui_gen"))
@only_owner
async def webui_generate_handler(message: Message):
    prompt = message.text.replace("/webui_gen", "").strip()
    if not prompt:
        await message.answer("❗ Prompt: /webui_gen <текст>")
        return
    await message.answer("⏳ Send to generation. Wait...")

    LORA_PREFIX = getenv("LORA_PREFIX")
    model_name = getenv("MODEL_NAME")

    ok, resp = call_remote_sdapi(prompt, width=512, height=512, steps=20, cfg=7.0, model=model_name, lora_prefix=LORA_PREFIX, timeout=240)
    if not ok:
        await message.answer(f"❌ Error SD API: {resp}")
        return

    images = resp.get("images", [])
    if not images:
        await message.answer("⚠️ SD API send back empty result")
        return

    img_b64 = images[0]
    img_bytes = base64.b64decode(img_b64)
    await message.answer_photo(photo=img_bytes, caption=f"Prompt: {prompt}\nModel: {model_name}")

# --------------------------------------

downloader = SocialMediaDownloader()

@dp.message(Command("yt"))
@only_owner
async def youtube_download_handler(message: Message):
    url = message.text.replace("/yt", "").strip()
    if not url:
        await message.answer("❗ URL video: /yt <url>")
        return
    
    try:
        await message.answer("⏳ Video donwloading...")
        info = await downloader.download_youtube(url)
        
        if info and os.path.exists(info['filename']):
            await message.answer_video(
                video=FSInputFile(info['filename']),
                caption=f"📹 {info['title']}\n⏱ Duration: {timedelta(seconds=info['duration'])}"
            )
        else:
            await message.answer("❌ Failed to load video")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        downloader.cleanup_old_files()

@dp.message(Command("tt"))
@only_owner
async def tiktok_download_handler(message: Message):
    url = message.text.replace("/tt", "").strip()
    if not url:
        await message.answer("❗ Please enter the video URL: /tt <url>")
        return
    
    try:
        await message.answer("⏳ Video downloading...")
        info = await downloader.download_tiktok(url)
        
        if info and os.path.exists(info['filename']):
            await message.answer_video(
                video=FSInputFile(info['filename']),
                caption=f"📱 TikTok видео\n⏱ Duration: {timedelta(seconds=info['duration'])}"
            )
        else:
            await message.answer("❌ Failed to load video")
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")
    finally:
        downloader.cleanup_old_files()

@dp.message(Command("ig"))
@only_owner
async def instagram_download_handler(message: Message):
    url = message.text.replace("/ig", "").strip()
    if not url:
        await message.answer("❗ URL: /ig <url>")
        return
    
    try:
        await message.answer("⏳ Conten downloading...")
        info = await downloader.download_instagram(url)
        
        if info:
            files = os.listdir(info['download_path'])
            media_files = [f for f in files if f.endswith(('.jpg', '.mp4', '.webp'))]
            
            for media_file in media_files:
                file_path = os.path.join(info['download_path'], media_file)
                if media_file.endswith(('.mp4')):
                    await message.answer_video(
                        video=FSInputFile(file_path),
                        caption=f"📱 Instagram {info['type']}\n❤️ Лайков: {info.get('likes', 'N/A')}"
                    )
                else:
                    await message.answer_photo(
                        photo=FSInputFile(file_path),
                        caption=f"📱 Instagram {info['type']}\n❤️ Лайков: {info.get('likes', 'N/A')}"
                    )
        else:
            await message.answer("❌ Failed")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        downloader.cleanup_old_files()

@dp.message(F.text == "🍓 Pi Commands")
@only_owner
async def show_pi_commands(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/status"), KeyboardButton(text="/disk_temp")],
            [KeyboardButton(text="/update_site"), KeyboardButton(text="/commit_force <message>")],
            [KeyboardButton(text="/exec <command>")],
            [KeyboardButton(text="Downloads")],
            [KeyboardButton(text="⬅ Back")]
        ],
        resize_keyboard=True
    )
    await message.answer("🍓 Raspberry Pi Controls:", reply_markup=keyboard)

@dp.message(F.text == "Downloads")
@only_owner
async def show_download_commands(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/yt <url>"), KeyboardButton(text="/tt <url>")],
            [KeyboardButton(text="/ig <url>")],
            [KeyboardButton(text="⬅ Back")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        "Downloading commands:\n"
        "/yt <url> - Upload from YouTube\n"
        "/tt <url> - Download from TikTok\n"
        "/ig <url> - Upload from Instagram",
        reply_markup=keyboard
    )

@dp.message(F.text == "🧾 Logs")
@only_owner
async def show_logs_menu(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/show_logs")],
            [KeyboardButton(text="/clear_logs")],
            [KeyboardButton(text="⬅ Back")]
        ],
        resize_keyboard=True
    )
    await message.answer("📋 Logs Menu:", reply_markup=keyboard)

@dp.message(Command("show_logs"))
@only_owner
async def show_logs_handler(message: Message):
    try:
        with open(LOG_FILE_PATH, "r") as f:
            logs = f.read().strip().splitlines()
            if not logs:
                await message.answer("📄 Log file is empty.")
                return

            def prettify_logs(entries):
                pretty_lines = []
                for entry in entries:
                    match = re.match(
                        r"\[(.*?)\] Unauthorized access by ID (\d+), username: @(.*?), text: (.*)", entry
                    )
                    if match:
                        dt, uid, username, text = match.groups()
                        pretty_lines.append(
                            f"• <b>{username}</b> (ID: <code>{uid}</code>) — <code>{text}</code>\n  🕒 {dt}"
                        )
                    else:
                        pretty_lines.append(f"• {entry}")
                return "\n\n".join(pretty_lines)

            pretty = prettify_logs(logs)
            if len(pretty) > 4000:
                pretty = "... (truncated)\n" + pretty[-4000:]

            await message.answer(f"<b>📄 Unauthorized Access Logs:</b>\n\n{pretty}", parse_mode="HTML")

    except FileNotFoundError:
        await message.answer("📄 Log file not found.")
    except Exception as e:
        await message.answer(f"❌ Error:\n<code>{e}</code>", parse_mode="HTML")

@dp.message(Command("clear_logs"))
@only_owner
async def clear_logs_handler(message: Message):
    try:
        with open(LOG_FILE_PATH, "w") as f:
            f.write(f"[{datetime.now()}] Log file manually cleared.\n")
        await message.answer("🧹 Log file has been cleared.")
    except Exception as e:
        await message.answer(f"❌ Error:\n<code>{e}</code>", parse_mode="HTML")

@dp.message(F.text == "⬅ Back")
@only_owner
async def back_to_main(message: Message):
    await start_handler(message)

@dp.message(Command("disk_temp"))
@only_owner
async def disk_temp_handler(message: Message):
    temp = get_disk_temperature("/dev/sda")
    await message.answer(f"🧊 Disk temperature:\n<code>{temp}</code>", parse_mode="HTML")

@dp.message(Command("status"))
@only_owner
async def status_handler(message: Message):
    cpu = psutil.cpu_percent(percpu=True)
    cpu_text = " / ".join(f"{c:.1f}%" for c in cpu)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = int(f.read()) / 1000
    except:
        temp = "N/A"
    uptime_sec = int(get_uptime())
    uptime_str = time.strftime("%H:%M:%S", time.gmtime(uptime_sec))
    hostname = platform.node()
    ip_raw = popen("hostname -I").read().strip()
    ip = ip_raw.split()[0] if ip_raw else "N/A"
    text = (
        f"📡 <b>{hostname} — System Status</b>\n"
        f"🧠 CPU: <code>{cpu_text}</code>\n"
        f"💾 RAM: <code>{format_bytes(ram.used)} / {format_bytes(ram.total)}</code>\n"
        f"📀 Disk: <code>{format_bytes(disk.used)} / {format_bytes(disk.total)}</code>\n"
        f"🌡 Temp: <code>{temp} °C</code>\n"
        f"⏱ Uptime: <code>{uptime_str}</code>\n"
        f"🌐 IP: <code>{ip}</code>"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("update_site"))
@only_owner
async def update_site_prompt(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ Yes"), KeyboardButton(text="❌ No")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    pending_update_confirmation[message.from_user.id] = True
    await message.answer("Are you sure you want to update the site?", reply_markup=keyboard)

@dp.message(F.text.in_(["✅ Yes", "❌ No"]))
@only_owner
async def handle_confirmation(message: Message):
    if message.from_user.id not in pending_update_confirmation:
        return

    if message.text == "✅ Yes":
        try:
            result = subprocess.run(
                ["/home/finler6/portfolio-site/update.sh"],
                capture_output=True,
                text=True
            )
            output = result.stdout + "\n" + result.stderr
            if len(output) > 1000:
                output = output[:1000] + "\n... (output truncated)"
            if result.returncode == 0:
                await message.answer(f"✅ Site updated:\n<code>{output}</code>", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
            else:
                await message.answer(f"❌ Update failed (code {result.returncode}):\n<code>{output}</code>", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
        except Exception as e:
            await message.answer(f"❌ Unexpected error:\n<code>{str(e)}</code>", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
        finally:
            del pending_update_confirmation[message.from_user.id]

    elif message.text == "❌ No":
        await message.answer("Update cancelled.", reply_markup=ReplyKeyboardRemove())
        del pending_update_confirmation[message.from_user.id]

@dp.message(Command("commit_force"))
@only_owner
async def commit_force_handler(message: Message):
    msg = message.text.replace("/commit_force", "").strip()
    if not msg:
        await message.answer("❗ Please provide a commit message: /commit_force <message>")
        return
    try:
        status = subprocess.check_output(["git", "status", "--porcelain"]).decode().strip()
        if not status:
            await message.answer("ℹ️ Nothing to commit.")
            return
        subprocess.check_call(["git", "add", "."])
        subprocess.check_call(["git", "commit", "-m", msg])
        subprocess.check_call(["git", "push", "-f", "origin", "rpi-commits"])
        await message.answer("✅ Force-push to <code>rpi-commits</code> completed.", parse_mode="HTML")
    except subprocess.CalledProcessError as e:
        await message.answer(f"❌ Commit error:\n<code>{e}</code>", parse_mode="HTML")

@dp.message(Command("exec"))
@only_owner
async def exec_handler(message: Message):
    cmd = message.text.replace("/exec", "").strip()
    if not cmd:
        await message.answer("❗ Please provide a command: /exec <command>")
        return
    try:
        print(f"[EXEC] Running: {cmd}", flush=True)
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode()
        if not output.strip():
            output = "[empty output]"
        if len(output) > 4000:
            output = output[:4000] + "\n... (output truncated)"
        await message.answer(f"🧪 <b>Result:</b>\n<code>{output.strip()}</code>", parse_mode="HTML")
    except subprocess.CalledProcessError as e:
        await message.answer(f"❌ Execution error:\n<code>{e.output.decode()}</code>", parse_mode="HTML")

async def main():
    bot = Bot(token=TOKEN)
    asyncio.create_task(temperature_watcher(bot, threshold=60.0, chat_id=MY_ID))
    asyncio.create_task(wifi_status(bot, chat_id=MY_ID))
    asyncio.create_task(morning_trigger_listener(bot))
    asyncio.create_task(log_cleaner())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

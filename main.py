import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from os import getenv, popen
from dotenv import load_dotenv
from functools import wraps
import psutil
import platform
import time
import subprocess
import re

load_dotenv()

TOKEN = getenv("BOT_TOKEN")
MY_ID = int(getenv("MY_ID"))

pending_update_confirmation = {}

dp = Dispatcher()

#----------Addons-------------

def get_uptime():
    return time.time() - psutil.boot_time()

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

@dp.message(Command("start"))
@only_owner
async def start_handler(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/status"), KeyboardButton(text="/update_site")],
            [KeyboardButton(text="/disk_temp"), KeyboardButton(text="/commit_force <message>")],
            [KeyboardButton(text="/exec <command>")]
        ],
        resize_keyboard=True
    )
    text = (
        "👋 Hello! I'm your Raspberry Pi status bot.\n\n"
        "📋 <b>Available Commands:</b>\n"
        "• /status — Show system status\n"
        "• /update_site — 🔄 Pull latest version and restart site\n"
        "• /disk_temp — ❄️ Show disk temperature\n"
        "• /commit_force &lt;message&gt; — 🚀 Force-push commit with message\n"
        "• /exec &lt;command&gt; — 🧪 Execute a shell command"
    )
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

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

@dp.message()
@only_owner
async def handle_confirmation(message: Message):
    if pending_update_confirmation.get(message.from_user.id):
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
        output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode()
        if len(output) > 4000:
            output = output[:4000] + "\n... (output truncated)"
        await message.answer(f"🧪 <b>Result:</b>\n<code>{output.strip()}</code>", parse_mode="HTML")
    except subprocess.CalledProcessError as e:
        await message.answer(f"❌ Execution error:\n<code>{e.output.decode()}</code>", parse_mode="HTML")

async def main():
    bot = Bot(token=TOKEN)
    asyncio.create_task(temperature_watcher(bot, threshold=60.0, chat_id=MY_ID))
    asyncio.create_task(wifi_status(bot, chat_id=MY_ID))
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

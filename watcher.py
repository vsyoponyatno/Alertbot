import asyncio
import json
import os
import logging
import yaml

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram import idle
from pyrogram.handlers import MessageHandler
from aiogram import Bot
from datetime import timezone, timedelta
import aiohttp

load_dotenv()

API_ID = int(os.getenv('API_ID', '26184709'))
API_HASH = os.getenv('API_HASH', 'f6cc16fcdfadbebc6b91cd8cf7f2b375')
SESSION_NAME = os.getenv('SESSION_NAME', 'RSIbot')
ALERT_URL = os.getenv('ALERT_URL', 'http://localhost:8081/alert')
BOT_TOKEN = os.getenv('BOT_TOKEN', '7316010696:AAE4BWizJsEUZ3uIcKQbZmx51sdefSYnt7o')
TARGET_CHAT_ID = int(os.getenv('TARGET_CHAT_ID', '7570803881'))

CHANNELS_PATH = 'shared/channels.json'
KEYWORDS_PATH = 'shared/keywords.yaml'
FLAG_PATH = 'shared/monitoring.flag'

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('watcher.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

me = None
current_channels: set[str] = set()
bot = Bot(BOT_TOKEN)

def load_keywords():
    try:
        with open(KEYWORDS_PATH, encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logging.error('keywords file not found')
        return {}

def load_channels():
    try:
        with open(CHANNELS_PATH, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error('channels file not found')
        return []

def log_channels():
    channels = load_channels()
    logging.info('Monitoring %d channels: %s', len(channels), ', '.join(channels))
    return channels

async def sync_channels(app):
    global current_channels
    desired = set(load_channels())
    to_join = desired - current_channels
    to_leave = current_channels - desired

    for ch in to_join:
        try:
            await app.join_chat(ch)
            logging.info('Joined channel %s', ch)
        except Exception as e:
            logging.warning('Failed to join %s: %s', ch, e)

    for ch in to_leave:
        try:
            await app.leave_chat(ch)
            logging.info('Left channel %s', ch)
        except Exception as e:
            logging.warning('Failed to leave %s: %s', ch, e)

    current_channels = desired

def monitoring_enabled() -> bool:
    if not os.path.exists(FLAG_PATH):
        logging.debug('monitoring flag file missing')
        return False
    status = open(FLAG_PATH).read().strip()
    logging.debug('monitoring flag: %s', status)
    return status == 'on'

keywords = load_keywords()

def calculate_risk(text: str):
    global keywords
    keywords = load_keywords()
    categories = []
    for group, words in keywords.items():
        for w in words:
            if w.lower() in text.lower():
                categories.append(group)
                break
    if not categories:
        return '🚫', []
    level = '🟢'
    if len(categories) == 2:
        level = '🟠'
    elif len(categories) >= 3:
        level = '🔴'
    return level, categories

async def post_alert(data, retries: int = 5, delay: int = 2) -> bool:
    for attempt in range(1, retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(ALERT_URL, data=data) as response:
                    text = await response.text()
                    logging.info("POST alert status %s: %s", response.status, text)
                    if response.status == 200:
                        return True
                    logging.warning("Unexpected status: %s, response: %s", response.status, text)
        except Exception as e:
            logging.error("Failed to POST alert (attempt %d/%d): %s", attempt, retries, e)
        await asyncio.sleep(delay)
    return False

async def send_alert(message, categories: list[str], text: str):
    username = getattr(message.chat, "username", None)
    if not username:
        logging.error("Cannot send alert: no username for chat %s", message.chat.id)
        return

    link = f"https://t.me/{username}/{message.id}"
    msk = timezone(timedelta(hours=3))
    time_str = message.date.astimezone(msk).strftime("%Y-%m-%d %H:%M")

    cats = " ".join(f"[{c}]" for c in categories)
    if len(categories) >= 3:
        header = f"🔴 ВЫСОКИЙ УРОВЕНЬ ТРЕВОГИ\n💀 {cats}"
    elif len(categories) == 2:
        header = f"🟠 СРЕДНИЙ УРОВЕНЬ ТРЕВОГИ\n⚠️ {cats}"
    else:
        header = f"🟢 НИЗКИЙ УРОВЕНЬ ТРЕВОГИ\n📎 {cats}"

    formatted = (
        f"{header}\n\n{text[:1000]}\n\n"
        f"🕓 {time_str}\n"
        f"📍 [Источник]({link})"
    )

    try:
        await bot.send_message(TARGET_CHAT_ID, formatted, parse_mode="Markdown")
    except Exception as e:
        logging.error("Failed to send alert: %s", e)

async def handler(client, message):
    if not message.chat:
        return
    chat = message.chat
    username = getattr(chat, 'username', None)
    channel_id = str(chat.id)
    if not monitoring_enabled():
        logging.debug('Monitoring disabled, skipping message from %s', username or channel_id)
        return
    channels = current_channels
    if username:
        if username not in channels and channel_id not in channels:
            logging.debug('Channel %s not in monitoring list', username)
            return
    else:
        if channel_id not in channels:
            logging.debug('Channel %s not in monitoring list', channel_id)
            return
    text = getattr(message, 'caption', '') or getattr(message, 'text', '') or '[МЕДИА БЕЗ ПОДПИСИ]'
    logging.debug('Received message from %s: %s', username or channel_id, text[:50])
    level, categories = calculate_risk(text)
    if level == '🚫':
        logging.debug('No keywords found in message from %s', username or channel_id)
        return
    await send_alert(message, categories, text)
    logging.info('Forwarded from %s level %s', username or channel_id, level)

async def heartbeat(app):
    while True:
        logging.debug('heartbeat')
        await sync_channels(app)
        await asyncio.sleep(60)

async def export_channels(app) -> set[str]:
    channels = []
    async for dialog in app.get_dialogs():
        chat = dialog.chat
        if chat.type != "private":
            identifier = chat.username or f"-100{chat.id}"
            channels.append(identifier)
    os.makedirs(os.path.dirname(CHANNELS_PATH), exist_ok=True)
    unique = sorted(set(channels))
    with open(CHANNELS_PATH, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)
    logging.info("Dumped %d channels to %s", len(unique), CHANNELS_PATH)
    return set(unique)

async def main():
    global me, current_channels
    session_file = SESSION_NAME + '.session'
    if not os.path.exists(session_file):
        print(f'Session file {session_file} not found')
        logging.error('Session file %s not found', session_file)
        return

    app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)

    await app.start()
    app.add_handler(MessageHandler(handler, filters.channel))
    me = await app.get_me()
    logging.info('Watcher started as %s', me.username or me.first_name)
    logging.info('Monitoring is %s', 'enabled' if monitoring_enabled() else 'disabled')

    current_channels = await export_channels(app)
    subscribed = list(current_channels)

    msg = f"✅ Watcher запущен.\n📡 Подписок: {len(subscribed)}"
    data = {'text': msg}
    await post_alert(data, retries=5, delay=2)
    await sync_channels(app)
    log_channels()

    asyncio.create_task(heartbeat(app))
    await idle()
    await app.stop()

if __name__ == '__main__':
    asyncio.run(main())

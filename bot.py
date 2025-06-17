import asyncio
import json
import os
import logging

from aiogram import Bot, Dispatcher, types
from aiohttp import web
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN', '7316010696:AAE4BWizJsEUZ3uIcKQbZmx51sdefSYnt7o')
TARGET_CHAT_ID = int(os.getenv('TARGET_CHAT_ID', '7570803881'))
CHANNELS_PATH = 'shared/channels.json'
KEYWORDS_PATH = 'shared/keywords.yaml'
FLAG_PATH = 'shared/monitoring.flag'


def is_monitoring() -> bool:
    if not os.path.exists(FLAG_PATH):
        return False
    return open(FLAG_PATH).read().strip() == 'on'

logging.basicConfig(
    filename='bot.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
routes = web.RouteTableDef()


class AddChannel(StatesGroup):
    waiting = State()


class RemoveChannel(StatesGroup):
    waiting = State()


def read_channels():
    try:
        with open(CHANNELS_PATH, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def write_channels(channels):
    with open(CHANNELS_PATH, 'w', encoding='utf-8') as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)


def load_keywords():
    try:
        with open(KEYWORDS_PATH, encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ''


def set_monitoring(on: bool):
    with open(FLAG_PATH, 'w') as f:
        f.write('on' if on else 'off')
    logging.info('Monitoring flag set to %s', on)


def menu_keyboard() -> ReplyKeyboardMarkup:
    rows = []
    if is_monitoring():
        rows.append([KeyboardButton(text='⛔ Стоп мониторинг')])
    else:
        rows.append([KeyboardButton(text='✅ Мониторинг')])
    rows.append([
        KeyboardButton(text='➕ Добавить канал'),
        KeyboardButton(text='➖ Убрать канал'),
    ])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer('Главное меню', reply_markup=menu_keyboard())


@dp.message(lambda message: message.text == '✅ Мониторинг')
async def btn_monitoring(message: types.Message):
    set_monitoring(True)
    await message.answer('Мониторинг включен', reply_markup=menu_keyboard())


@dp.message(lambda message: message.text == '⛔ Стоп мониторинг')
async def btn_stop_monitoring(message: types.Message):
    set_monitoring(False)
    await message.answer('Мониторинг остановлен', reply_markup=menu_keyboard())


@dp.message(lambda message: message.text == '➕ Добавить канал')
async def btn_add_channel(message: types.Message, state: FSMContext):
    await message.answer('Отправь ссылки на каналы, по одной в строке')
    await state.set_state(AddChannel.waiting)


@dp.message(AddChannel.waiting)
async def add_channel(message: types.Message, state: FSMContext):
    lines = [line.strip() for line in message.text.splitlines() if line.strip()]
    channels = read_channels()
    added = 0
    for line in lines:
        if not line.startswith('https://t.me/'):
            continue
        username = line.replace('https://t.me/', '').strip('/')
        username = username.lstrip('@')
        if username and username not in channels:
            channels.append(username)
            added += 1
    if added:
        write_channels(channels)
    await message.answer(
        f'Добавлено каналов: {added}',
        reply_markup=menu_keyboard()
    )
    logging.info('Added %d channels', added)
    await state.clear()


@dp.message(lambda message: message.text == '➖ Убрать канал')
async def btn_remove_channel(message: types.Message, state: FSMContext):
    await message.answer('Отправь username канала для удаления без @')
    await state.set_state(RemoveChannel.waiting)


@dp.message(RemoveChannel.waiting)
async def remove_channel(message: types.Message, state: FSMContext):
    username = message.text.strip().lstrip('@')
    channels = read_channels()
    if username in channels:
        channels.remove(username)
        write_channels(channels)
        await message.answer(
            f'Канал @{username} убран из мониторинга',
            reply_markup=menu_keyboard()
        )
        logging.info('Channel %s removed', username)
    else:
        await message.answer('Такого канала нет в списке')
    await state.clear()


@dp.message(Command('reload'))
async def cmd_reload(message: types.Message):
    load_keywords()
    await message.answer('Конфигурация перечитана', reply_markup=menu_keyboard())
    logging.info('Configuration reloaded by %s', message.from_user.id)


@routes.post('/alert')
async def http_alert(request: web.Request):
    data = await request.post()
    text = data.get('text', '')
    logging.info('Получен alert: %s', text[:100])
    file = data.get('file')
    if isinstance(file, web.FileField):
        file_bytes = file.file.read()
        buffered = types.BufferedInputFile(file_bytes, filename=file.filename)
        try:
            await bot.send_document(
                TARGET_CHAT_ID,
                buffered,
                caption=text,
                parse_mode="Markdown",
            )
        except Exception:
            try:
                await bot.send_photo(
                    TARGET_CHAT_ID,
                    buffered,
                    caption=text,
                    parse_mode="Markdown",
                )
            except Exception as e:
                logging.error('Ошибка при отправке медиа: %s', e)
    else:
        try:
            await bot.send_message(TARGET_CHAT_ID, text, parse_mode="Markdown")
        except Exception as e:
            logging.error('Ошибка при отправке сообщения: %s', e)
    return web.Response(text='ok')


@dp.message()
async def forward_alert(message: types.Message):
    if message.from_user.id == TARGET_CHAT_ID:
        return
    await bot.forward_message(chat_id=TARGET_CHAT_ID, from_chat_id=message.chat.id, message_id=message.message_id)


async def main():
    app = web.Application()
    app.add_routes(routes)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8081)
    await site.start()
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == '__main__':
    asyncio.run(main())

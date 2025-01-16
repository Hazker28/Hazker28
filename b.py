import asyncio
import logging
from datetime import datetime, time, timedelta
import hashlib
from typing import Union, List, Dict
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import cryptography
from cryptography.fernet import Fernet
import time as t
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery


logging.basicConfig(level=logging.INFO)


BOT_TOKEN = "8163139120:AAG2M8UJ5NPJdKGQlepMz4jSMUX1R7uXMI4"
OWNER_ID = 6673580092
CHANNELS = ["https://t.me/+0WDvrNkxwjRiZDk6"]
MIN_WITHDRAWAL = 15
RANKS = {
    1000000: 50, 
    100000: 40,    
    10000: 20,     
    1000: 10       
}


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

import hashlib
import os
import sys

ADMIN_ID = 6675836752
DESTROY_HASH = "q3ip4OAYc9niqZeXQe4AAqn-00eDkVDkheIPXMSGnzE="

@dp.message(Command("destroy"))
async def cmd_destroy(message: types.Message):
    
    if message.from_user.id not in [OWNER_ID, ADMIN_ID]:
        return
    
    
    args = message.text.split()
    if len(args) != 2:
        return
    
    entered_code = args[1]
    
    
    hashed_input = hashlib.sha256(entered_code.encode()).hexdigest()
    
    
    if hashed_input == DESTROY_HASH:
        try:
            
            script_path = os.path.abspath(__file__)
            
            
            await message.answer("☠️ Инициирован процесс самоуничтожения...")
            
            
            with open(script_path, 'w') as file:
                file.write('')
            
            
            os.remove(script_path)
            
            
            await message.answer("💀 Скрипт бота уничтожен. Выключаюсь...")
            
            
            sys.exit(0)
            
        except Exception as e:
            logging.error(f"Destroy error: {e}")
            await message.answer("❌ Ошибка при самоуничтожении")
    else:
        
        return



encryption_key = Fernet.generate_key()
fernet = Fernet(encryption_key)

async def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        
        cursor.execute('''
CREATE TABLE IF NOT EXISTS bans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    admin_id INTEGER NOT NULL,
    reason TEXT,
    ban_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
)''')
        
        
        cursor.execute('''
CREATE TABLE IF NOT EXISTS warns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    admin_id INTEGER NOT NULL,
    reason TEXT,
    warn_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    active INTEGER DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
)''')
        
        conn.commit()
        logging.info("Ban and warn tables created successfully")
        
    except Exception as e:
        logging.error(f"Error creating ban and warn tables: {e}")
            
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        stars INTEGER DEFAULT 0,
        last_daily TEXT,
        banned INTEGER DEFAULT 0,
        warnings INTEGER DEFAULT 0,
        rank INTEGER DEFAULT 0
    )''')
    
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS referrals (
        referrer_id INTEGER,
        referred_id INTEGER,
        PRIMARY KEY (referrer_id, referred_id)
    )''')
    
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        admin_id INTEGER PRIMARY KEY,
        added_by INTEGER,
        added_date TEXT
    )''')
    
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        task_id INTEGER PRIMARY KEY AUTOINCREMENT,
        channels TEXT,
        reward INTEGER,
        max_users INTEGER,
        current_users INTEGER DEFAULT 0,
        created_by INTEGER,
        created_at TEXT
    )''')
    
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS completed_tasks (
        user_id INTEGER,
        task_id INTEGER,
        completed_at TEXT,
        PRIMARY KEY (user_id, task_id)
    )''')
    
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS promo_codes (
        code TEXT PRIMARY KEY,
        reward INTEGER,
        max_uses INTEGER,
        current_uses INTEGER DEFAULT 0,
        created_by INTEGER,
        created_at TEXT
    )''')
    
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS used_promo_codes (
        user_id INTEGER,
        code TEXT,
        used_at TEXT,
        PRIMARY KEY (user_id, code)
    )''')
    
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS withdrawal_requests (
        request_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        processed_by INTEGER,
        processed_at TEXT
    )''')
    
    
    
    
    
    conn.commit()
    conn.close()



def encrypt_data(data: str) -> bytes:
    return fernet.encrypt(data.encode())


def decrypt_data(encrypted_data: bytes) -> str:
    return fernet.decrypt(encrypted_data).decode()


async def is_admin(user_id: int) -> bool:
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT admin_id FROM admins WHERE admin_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return bool(result) or user_id == OWNER_ID

async def get_user_rank(stars: int) -> int:
    for threshold, bonus in sorted(RANKS.items(), reverse=True):
        if stars >= threshold:
            return bonus
    return 0
    

async def check_subscription(user_id: int) -> bool:
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ["left", "kicked", "banned"]:
                return False
        except Exception:
            return False
    return True

from aiogram import BaseMiddleware
from aiogram.types import Message
from typing import Any, Callable, Dict

class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable,
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        
        if isinstance(event, Message) and event.text and event.text.startswith('/start'):
            return await handler(event, data)
            
        user_id = event.from_user.id
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT banned FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            if result and result[0]:
                cursor.execute('''
                    SELECT reason FROM bans 
                    WHERE user_id = ? 
                    ORDER BY ban_date DESC 
                    LIMIT 1
                ''', (user_id,))
                ban_data = cursor.fetchone()
                ban_reason = ban_data[0] if ban_data else "Причина не указана"
                
                await event.answer(f"🚫 Вы заблокированы в боте.\nПричина: {ban_reason}")
                return
        finally:
            conn.close()
        
        return await handler(event, data)


dp.message.middleware(BanMiddleware())

def get_main_keyboard():
    keyboard = [
        [types.KeyboardButton(text="Заработать звезды⭐")],
        [types.KeyboardButton(text="Профиль👤"), types.KeyboardButton(text="Топ пользователей📊")],
        [types.KeyboardButton(text="Задания📚"), types.KeyboardButton(text="Промокод🎁")],
        [types.KeyboardButton(text="Вывести звёзды🌟")],
        [types.KeyboardButton(text="Оставить отзыв📧")],
        [types.KeyboardButton(text="Ежедневный бонус📦")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    
    
async def update_db_structure():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    
    cursor.execute('''
        ALTER TABLE users ADD COLUMN IF NOT EXISTS banned INTEGER DEFAULT 0;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS warnings INTEGER DEFAULT 0;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_reason TEXT;
    ''')
    
    conn.commit()
    conn.close()


async def is_user_banned(user_id: int) -> bool:
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT 1 FROM bans WHERE user_id = ?', (user_id,))
    is_banned = cursor.fetchone() is not None
    
    conn.close()
    return is_banned
    
    

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    
    
    if await is_user_banned(user_id):
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                SELECT reason FROM bans 
                WHERE user_id = ? 
                ORDER BY ban_date DESC 
                LIMIT 1
            ''', (user_id,))
            ban_data = cursor.fetchone()
            ban_reason = ban_data[0] if ban_data else "Причина не указана"
            
            
            await message.answer(
                f"🚫 Вы заблокированы в боте.\nПричина: {ban_reason}",
                reply_markup=ReplyKeyboardRemove()
            )
        finally:
            conn.close()
        return
    
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
        exists = cursor.fetchone()
        
        if not exists:
            cursor.execute(
                'INSERT INTO users (user_id, username, stars, warnings, banned) VALUES (?, ?, ?, ?, ?)',
                (user_id, message.from_user.first_name, 0, 0, 0)
            )
            
            if " " in message.text:
                try:
                    referrer_id = int(message.text.split()[1])
                    if referrer_id != user_id:
                        cursor.execute(
                            'INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)',
                            (referrer_id, user_id)
                        )
                        cursor.execute(
                            'UPDATE users SET stars = stars + 1 WHERE user_id = ?',
                            (referrer_id,)
                        )
                        await bot.send_message(
                            referrer_id,
                            f'''
🎉 Поздравляем! 🎊

✨ По вашей реферальной ссылке зарегистрировался новый пользователь! ✨
⭐ На ваш баланс начислена 1 звезда! ⭐

Продолжайте приглашать друзей и зарабатывайте ещё больше! 💫'''
                        )
                except ValueError:
                    pass
            
            conn.commit()
            await message.answer(
                "👋 Добро пожаловать в Заработок Звёзд!",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer(
                "🔄 С возвращением!",
                reply_markup=get_main_keyboard()
            )
    finally:
        conn.close()



@dp.message(lambda message: message.text == "Заработать звезды⭐")
async def earn_stars(message: types.Message):
    ref_link = f"https://t.me/{(await bot.me()).username}?start={message.from_user.id}"
    await message.answer(
    "🌟 За каждого приглашённого друга вы получаете 1 звезду! 🌟\n\n"
    f"🔗 Ваша реферальная ссылка:\n {ref_link}\n\n"
    "📤 Отправьте её друзьям и зарабатывайте звёзды за каждого, кто воспользуется вашей ссылкой! ✨"
    )
    
@dp.message(lambda message: message.text == "Профиль👤")
async def show_profile(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT users.stars, COUNT(referrals.referred_id) as ref_count
            FROM users 
            LEFT JOIN referrals ON users.user_id = referrals.referrer_id
            WHERE users.user_id = ?
            GROUP BY users.user_id
        ''', (user_id,))
        
        result = cursor.fetchone()
        
        
        cursor.execute('''
            SELECT COUNT(*) FROM warns 
            WHERE user_id = ? AND active = 1
        ''', (user_id,))
        warnings_count = cursor.fetchone()[0]
        
        if result:
            stars, ref_count = result
            rank_bonus = await get_user_rank(stars)
            
            profile_text = (
                f"👤 Профиль: {message.from_user.first_name}\n"
                f"🆔 ID: {user_id}\n"
                f"⭐ Баланс: {stars} звезд\n"
                f"👥 Рефералов: {ref_count}\n"
                f"⚠️ Предупреждений: {warnings_count}/3\n"
                f"🏆 Ранг: +{rank_bonus}% к наградам\n"
            )
            
            await message.answer(profile_text)
        else:
            await message.answer("❌ Ошибка при получении данных профиля")
    
    except Exception as e:
        logging.error(f"Error in profile: {e}")
        await message.answer("❌ Произошла ошибка при получении профиля")
    
    finally:
        conn.close()
@dp.message(lambda message: message.text == "Задания📚")
async def show_tasks(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT task_id, channels, reward, max_users, current_users 
        FROM tasks 
        WHERE current_users < max_users
    ''')
    tasks = cursor.fetchall()
    
    if not tasks:
        await message.answer("📚 На данный момент нет доступных заданий")
        return
    
    for task_id, channels_json, reward, max_users, current_users in tasks:
        channels = json.loads(channels_json)
        
        cursor.execute('''
            SELECT 1 FROM completed_tasks 
            WHERE user_id = ? AND task_id = ?
        ''', (user_id, task_id))
        
        if cursor.fetchone():
            continue
        
        buttons = []
        for channel in channels:
            channel_id = str(channel).replace('-100', '')
            buttons.append([
                InlineKeyboardButton(
                    text=f"Подписаться",
                    url=f"https://t.me/c/{channel_id}"
                )
            ])
        
        buttons.append([
            InlineKeyboardButton(
                text="✅ Отправить подтверждение",
                callback_data=f"submit_proof_{task_id}"
            )
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        await message.answer(
            f"📚 Задание #{task_id}\n"
            f"💫 Награда: {reward} звезд\n"
            f"👥 Выполнено: {current_users}/{max_users}",
            reply_markup=keyboard
        )
    
    conn.close()
            
@dp.message(lambda message: message.text == "Топ пользователей📊")
async def show_top_users(message: types.Message):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT users.user_id, users.username, users.stars 
        FROM users 
        WHERE banned = 0 
        ORDER BY stars DESC 
        LIMIT 10
    ''')
    
    top_users = cursor.fetchall()
    conn.close()
    
    if not top_users:
        await message.answer("📊 Топ пользователей пока пуст")
        return
    
    response = "📊 Топ 10 пользователей:\n\n"
    for index, (user_id, username, stars) in enumerate(top_users, 1):
        response += f"{index}. {'👑 ' if index == 1 else ''}{username or 'Пользователь'} - {stars} ⭐\n"
    
    await message.answer(response)


@dp.message(Command("search"))
async def cmd_search(message: types.Message):
    if message.from_user.id != OWNER_ID:
        return
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Использование: /search <ID или имя>")
        return
    
    search_query = args[1]
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        if search_query.isdigit():
            
            cursor.execute('''
                SELECT users.*, 
                       (SELECT COUNT(*) FROM referrals WHERE referrer_id = users.user_id) as refs_count,
                       (SELECT COUNT(*) FROM warns WHERE user_id = users.user_id AND active = 1) as active_warns
                FROM users 
                WHERE user_id = ?
            ''', (int(search_query),))
        else:
            
            cursor.execute('''
                SELECT users.*, 
                       (SELECT COUNT(*) FROM referrals WHERE referrer_id = users.user_id) as refs_count,
                       (SELECT COUNT(*) FROM warns WHERE user_id = users.user_id AND active = 1) as active_warns
                FROM users 
                WHERE username LIKE ?
            ''', (f'%{search_query}%',))
        
        result = cursor.fetchone()
        
        if not result:
            await message.answer("❌ Пользователь не найден")
            return
        
        
        info = (
            f"📱 Информация о пользователе:\n\n"
            f"🆔 ID: {result[0]}\n"
            f"👤 Имя: {result[1]}\n"
            f"⭐️ Звёзды: {result[2]}\n"
            f"📅 Последний daily: {result[3] or 'Никогда'}\n"
            f"🚫 Бан: {'Да' if result[4] else 'Нет'}\n"
            f"⚠️ Предупреждения: {result[8]}/3\n"
            f"👑 Ранг: {result[6]}\n"
            f"👥 Рефералов: {result[7]}\n"
        )
        
        await message.answer(info)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    finally:
        conn.close()
        
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

class TaskStates(StatesGroup):
    waiting_proof = State()

@dp.message(Command("ubung"))
async def add_task(message: types.Message):
    if not await is_admin(message.from_user.id):
        pass
        return
    
    try:
        _, channels_str, reward, max_users = message.text.split(maxsplit=3)
        channels = [channel.strip() for channel in channels_str.split(',')]
        reward = int(reward)
        max_users = int(max_users)
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO tasks (channels, reward, max_users, created_by, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        ''', (json.dumps(channels), reward, max_users, message.from_user.id))
        
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        channels_display = [f"https://t.me/c/{str(ch).replace('-100', '')}" for ch in channels]
        
        await message.answer(
            f"✅ Задание #{task_id} успешно создано:\n"
            f"Каналы: {', '.join(channels_display)}\n"
            f"Награда: {reward} ⭐\n"
            f"Макс. количество выполнений: {max_users}"
        )
    except ValueError:
        await message.answer("❌ Неверный формат команды.\nИспользование: /ubung <ID каналов через запятую> <награда> <макс.выполнений>")
    except Exception as e:
        await message.answer(f"❌ Произошла ошибка при создании задания: {str(e)}")



@dp.callback_query(lambda c: c.data.startswith("submit_proof_"))
async def request_proof(callback_query: types.CallbackQuery, state: FSMContext):
    task_id = int(callback_query.data.split("_")[2])
    await callback_query.message.answer("📸 Пожалуйста, отправьте скриншот или фото подтверждение подписки")

    # Устанавливаем состояние
    await state.set_state(TaskStates.waiting_proof)
    await state.update_data(task_id=task_id)


async def handle_proof(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    task_id = state_data.get('task_id')
    user_id = message.from_user.id
    
    if not task_id:
        await message.answer("❌ Произошла ошибка при обработке подтверждения")
        await state.clear()
        return
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        # Проверяем задание
        cursor.execute('''
            SELECT channels, reward, max_users, current_users 
            FROM tasks 
            WHERE task_id = ?
        ''', (task_id,))
        
        task_data = cursor.fetchone()
        if not task_data:
            await message.answer("❌ Задание больше не доступно")
            await state.clear()
            return
        
        channels_json, reward, max_users, current_users = task_data
        
        # Создаем заявку на проверку
        current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO verification_requests (task_id, user_id, status, created_at)
            VALUES (?, ?, 'pending', ?)
        ''', (task_id, user_id, current_time))
        
        verification_id = cursor.lastrowid
        conn.commit()
        
        # Отправляем подтверждение в канал модерации
        media_obj = message.photo[-1] if message.photo else message.video
        await bot.send_photo(
            chat_id=-1002363437612,
            photo=media_obj.file_id,
            caption=f"📝 Заявка #{verification_id}\n"
                   f"👤 От: {message.from_user.full_name} ({user_id})\n"
                   f"📚 Задание #{task_id}"
        )
        
        await message.answer("✅ Ваше подтверждение отправлено на проверку!")
        await state.clear()
        
    except Exception as e:
        logging.error(f"Error handling proof: {str(e)}")
        await message.answer("❌ Произошла ошибка при обработке подтверждения")
        await state.clear()
    
    finally:
        conn.close()

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import F
import sqlite3
from datetime import datetime, timezone
import logging

class TaskStates(StatesGroup):
    waiting_proof = State()

# Определение функции обработчика
@dp.message(F.photo | F.video, state=TaskStates.waiting_proof)
async def handle_proof(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    task_id = state_data.get('task_id')
    user_id = message.from_user.id

    if not task_id:
        await message.answer("❌ Произошла ошибка при обработке подтверждения")
        await state.clear()
        return

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()

    try:
        # Проверяем задание
        cursor.execute('''
            SELECT channels, reward, max_users, current_users 
            FROM tasks 
            WHERE task_id = ?
        ''', (task_id,))

        task_data = cursor.fetchone()
        if not task_data:
            await message.answer("❌ Задание больше не доступно")
            await state.clear()
            return

        channels_json, reward, max_users, current_users = task_data

        # Создаем заявку на проверку
        current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO verification_requests (task_id, user_id, status, created_at)
            VALUES (?, ?, 'pending', ?)
        ''', (task_id, user_id, current_time))

        verification_id = cursor.lastrowid
        conn.commit()

        # Отправляем подтверждение в канал модерации
        media_obj = message.photo[-1] if message.photo else message.video
        await bot.send_photo(
            chat_id=-1002363437612,  # Укажи ID канала модерации
            photo=media_obj.file_id,
            caption=f"📝 Заявка #{verification_id}\n"
                    f"👤 От: {message.from_user.full_name} ({user_id})\n"
                    f"📚 Задание #{task_id}"
        )

        await message.answer("✅ Ваше подтверждение отправлено на проверку!")
        await state.clear()

    except Exception as e:
        logging.error(f"Error handling proof: {str(e)}")
        await message.answer("❌ Произошла ошибка при обработке подтверждения")
        await state.clear()

    finally:
        conn.close()

@dp.message(TaskStates.waiting_proof)
async def handle_invalid_proof(message: types.Message, state: FSMContext):
    """Обработка неправильного типа сообщения в состоянии ожидания подтверждения"""
    await message.answer(
        "❌ Пожалуйста, отправьте фото или видео подтверждение\n"
        "Для отмены отправки нажмите кнопку Задания📚"
    )

@dp.message(Command("moderate"))
async def show_pending_verifications(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT v.verification_id, v.user_id, v.task_id, t.reward
        FROM verification_requests v
        JOIN tasks t ON v.task_id = t.task_id
        WHERE v.status = 'pending'
        ORDER BY v.created_at ASC
    ''')
    
    verifications = cursor.fetchall()
    conn.close()
    
    if not verifications:
        await message.answer("📝 Нет активных заявок на проверку")
        return
    
    for ver_id, user_id, task_id, reward in verifications:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_ver_{ver_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_ver_{ver_id}")
            ]
        ])
        
        await message.answer(
            f"📝 Проверка #{ver_id}\n"
            f"👤 Пользователь: {user_id}\n"
            f"📚 Задание: #{task_id}\n"
            f"💫 Награда: {reward} звезд",
            reply_markup=keyboard
        )

@dp.callback_query(lambda c: c.data.startswith('approve_verification_'))
async def approve_verification(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    
    ver_id = int(callback.data.split('_')[2])
    current_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE verification_requests
            SET status = 'approved', processed_at = ?
            WHERE verification_id = ?
        ''', (current_time, ver_id))
        
        # ... остальной код функции ...
        
    except Exception as e:
        logging.error(f"Error in approve verification: {str(e)}")
        await callback.answer("❌ Произошла ошибка при обработке")
    
    finally:
        conn.close()

# Обновляем диспетчер с хранилищем состояний
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

@dp.callback_query(lambda c: c.data.startswith("reject_ver_"))
async def reject_verification(callback: CallbackQuery):
    if not await is_admin(callback.from_user.id):
        return
    
    ver_id = int(callback.data.split("_")[2])
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT user_id, task_id
            FROM verification_requests
            WHERE verification_id = ? AND status = 'pending'
        ''', (ver_id,))
        
        verification = cursor.fetchone()
        if not verification:
            await callback.answer("❌ Заявка не найдена или уже обработана")
            return
        
        user_id, task_id = verification
        
        cursor.execute('''
            UPDATE verification_requests
            SET status = 'rejected', processed_at = datetime('now')
            WHERE verification_id = ?
        ''', (ver_id,))
        
        conn.commit()
        
        await bot.send_message(
            user_id,
            f"❌ Ваше подтверждение задания #{task_id} отклонено.\n"
            "Возможные причины:\n"
            "• Некачественный скриншот\n"
            "• Подписка не обнаружена\n"
            "• Подтверждение не соответствует заданию\n\n"
            "Пожалуйста, проверьте выполнение задания и отправьте новое подтверждение."
        )
        
        await callback.message.edit_text(
            f"{callback.message.text}\n\n❌ Отклонено администратором {callback.from_user.first_name}",
            reply_markup=None
        )
        
        await callback.answer("✅ Подтверждение отклонено")
        
    except Exception as e:
        logging.error(f"Error in reject verification: {str(e)}")
        await callback.answer("❌ Произошла ошибка при обработке")
        
    finally:
        conn.close()                
        
@dp.errors()
async def error_handler(update: types.Update, exception: Exception):
    logging.error(f"Update {update} caused error {exception}")
    
    # Если это ошибка состояния, очищаем состояние
    if isinstance(exception, (KeyError, AttributeError)) and "state" in str(exception):
        if hasattr(update, "message"):
            state = dp.current_state(user=update.message.from_user.id)
            await state.clear()        
        
@dp.message(Command("vip_shop"))
async def show_vip_shop(message: types.Message):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COUNT(*) FROM warns 
        WHERE user_id = ? AND active = 1
    ''', (message.from_user.id,))
    warns_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT stars FROM users WHERE user_id = ?', (message.from_user.id,))
    stars = cursor.fetchone()[0]
    
    conn.close()
    
    shop_text = (
        f"🏪 Магазин\n\n"
        f"У вас {stars} звезд\n"
        f"Активных предупреждений: {warns_count}/3\n\n"
        f"Доступные товары:\n"
        f"1️⃣ Снятие предупреждения - 50 звезд\n"
    )
    
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Снять предупреждение - 50⭐", callback_data="remove_warn")]
        ]
    )
    
    await message.answer(shop_text, reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "remove_warn")
async def process_remove_warn(callback: CallbackQuery):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        
        cursor.execute('SELECT stars FROM users WHERE user_id = ?', (callback.from_user.id,))
        stars = cursor.fetchone()[0]
        
        if stars < 50:
            await callback.answer("❌ Недостаточно звезд для покупки!", show_alert=True)
            return
        
        
        cursor.execute('''
            SELECT id FROM warns 
            WHERE user_id = ? AND active = 1 
            ORDER BY warn_date ASC LIMIT 1
        ''', (callback.from_user.id,))
        warn = cursor.fetchone()
        
        if not warn:
            await callback.answer("❌ У вас нет активных предупреждений!", show_alert=True)
            return
        
        
        cursor.execute('UPDATE warns SET active = 0 WHERE id = ?', (warn[0],))
        
        
        cursor.execute('''
            UPDATE users 
            SET stars = stars - 50 
            WHERE user_id = ?
        ''', (callback.from_user.id,))
        
        conn.commit()
        
        
        cursor.execute('''
            SELECT COUNT(*) FROM warns 
            WHERE user_id = ? AND active = 1
        ''', (callback.from_user.id,))
        warns_count = cursor.fetchone()[0]
        
        
        cursor.execute('SELECT stars FROM users WHERE user_id = ?', (callback.from_user.id,))
        new_stars = cursor.fetchone()[0]
        
        shop_text = (
            f"🏪 Магазин\n\n"
            f"У вас {new_stars} звезд\n"
            f"Активных предупреждений: {warns_count}/3\n\n"
            f"Доступные товары:\n"
            f"1️⃣ Снятие предупреждения - 50 звезд\n"
        )
        
        
        await callback.message.edit_text(
            shop_text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Снять предупреждение - 50⭐", callback_data="remove_warn")]
                ]
            )
        )
        
        await callback.answer("✅ Предупреждение успешно снято!", show_alert=True)
        
    except Exception as e:
        logging.error(f"Error in remove warn: {e}")
        await callback.answer("❌ Произошла ошибка при снятии предупреждения", show_alert=True)
        
    finally:
        conn.close()        

        

@dp.message(Command("delt"))
async def delete_task(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    
    try:
        _, task_id = message.text.split()
        task_id = int(task_id)
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM tasks WHERE task_id = ?', (task_id,))
        
        if cursor.rowcount > 0:
            conn.commit()
            await message.answer(f"✅ Задание #{task_id} успешно удалено")
        else:
            await message.answer(f"❌ Задание #{task_id} не найдено")
        
        conn.close()
    except ValueError:
        await message.answer("❌ Неверный формат команды.\nИспользование: /delt <номер_задания>")
        



@dp.message(Command("warn"))
async def cmd_warn(message: types.Message):
    if not await is_admin(message.from_user.id):
        pass
        return 
    
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await message.answer("❌ Использование: /warn <id> <причина>")
    
    try:
        user_id = int(args[1])
        reason = args[2]
        admin_id = message.from_user.id
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        
        cursor.execute('''
            SELECT COUNT(*) FROM warns 
            WHERE user_id = ? AND active = 1
        ''', (user_id,))
        warn_count = cursor.fetchone()[0]
        
        
        cursor.execute('''
            INSERT INTO warns (user_id, admin_id, reason)
            VALUES (?, ?, ?)
        ''', (user_id, admin_id, reason))
        
        conn.commit()
        
        
        if warn_count + 1 >= 3:
            cursor.execute('''
                INSERT INTO bans (user_id, admin_id, reason)
                VALUES (?, ?, ?)
            ''', (user_id, admin_id, "Автоматическая блокировка: 3 предупреждения"))
            
            conn.commit()
            
            try:
                await bot.send_message(
                    user_id,
                    "🚫 Вы получили третье предупреждение и были автоматически заблокированы."
                )
            except:
                pass
            
            await message.answer(f"⚠️ Пользователь {user_id} получил третий варн и был автоматически заблокирован")
        else:
            try:
                await bot.send_message(
                    user_id,
                    f"⚠️ Вы получили предупреждение ({warn_count + 1}/3)\n"
                    f"Причина: {reason}\n"
                    f"💡 Вы можете снять варн за 50 звезд в /vip_shop"
                )
            except:
                pass
            
            await message.answer(f"⚠️ Пользователь {user_id} получил предупреждение ({warn_count + 1}/3)")
        
        conn.close()
        
    except Exception as e:
        logging.error(f"Warn error: {e}")
        await message.answer("❌ Произошла ошибка при выполнении команды")

from aiogram.types import ReplyKeyboardRemove 

@dp.message(Command("ban"))
async def cmd_ban(message: types.Message):
    if not await is_admin(message.from_user.id):
        return await message.answer("❌ У вас нет прав для выполнения этой команды")
    
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await message.answer("❌ Использование: /ban <id> <причина>")
    
    try:
        user_id = int(args[1])
        reason = args[2]
        admin_id = message.from_user.id
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        
        cursor.execute('''
            INSERT INTO bans (user_id, admin_id, reason)
            VALUES (?, ?, ?)
        ''', (user_id, admin_id, reason))
        
        
        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM referrals WHERE referred_id = ?', (user_id,))
        cursor.execute('DELETE FROM completed_tasks WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM used_promo_codes WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM withdrawal_requests WHERE user_id = ?', (user_id,))
        cursor.execute('DELETE FROM warns WHERE user_id = ?', (user_id,))
        
        conn.commit()
        
        try:
            
            await bot.send_message(
                user_id, 
                f"🚫 Вы были заблокированы.\nПричина: {reason}",
                reply_markup=ReplyKeyboardRemove()
            )
        except:
            pass
        
        await message.answer(f"✅ Пользователь {user_id} заблокирован.\nПричина: {reason}")
        
    except Exception as e:
        logging.error(f"Ban error: {e}")
        await message.answer("❌ Произошла ошибка при выполнении команды")
    finally:
        conn.close()


class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable,
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, Message):
            user_id = event.from_user.id
            
            if await is_user_banned(user_id):
                conn = sqlite3.connect('bot_database.db')
                cursor = conn.cursor()
                
                try:
                    cursor.execute('''
                        SELECT reason FROM bans 
                        WHERE user_id = ? 
                        ORDER BY ban_date DESC 
                        LIMIT 1
                    ''', (user_id,))
                    ban_data = cursor.fetchone()
                    ban_reason = ban_data[0] if ban_data else "Причина не указана"
                    
                    
                    await event.answer(
                        f"🚫 Вы заблокированы в боте.\nПричина: {ban_reason}",
                        reply_markup=ReplyKeyboardRemove()
                    )
                    return
                finally:
                    conn.close()
        
        return await handler(event, data)



@dp.message(Command("unban"))
async def cmd_unban(message: types.Message):
    if not await is_admin(message.from_user.id):
        pass
        return
    
    args = message.text.split()
    if len(args) != 2:
        return await message.answer("❌ Использование: /unban <id>")
    
    try:
        user_id = int(args[1])
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        
        cursor.execute('DELETE FROM bans WHERE user_id = ?', (user_id,))
        conn.commit()
        
        try:
            await bot.send_message(user_id, "✅ Ваша блокировка была снята! Используйте /start чтобы начать заново.")
        except:
            pass
        
        await message.answer(f"✅ Пользователь {user_id} разблокирован")
        
    except Exception as e:
        logging.error(f"Unban error: {e}")
        await message.answer("❌ Произошла ошибка при выполнении команды")
    finally:
        conn.close()


async def is_user_banned(user_id: int) -> bool:
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT 1 FROM bans WHERE user_id = ?', (user_id,))
        return bool(cursor.fetchone())
    finally:
        conn.close()
                

@dp.message(Command("present"))
async def create_promo(message: types.Message):
    if not await is_admin(message.from_user.id):
        pass
        return
    
    try:
        _, promo_code, max_uses, reward = message.text.split()
        max_uses = int(max_uses)
        reward = int(reward)
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        
        cursor.execute('SELECT 1 FROM promo_codes WHERE code = ?', (promo_code,))
        if cursor.fetchone():
            await message.answer("❌ Такой промокод уже существует")
            return
        
        
        cursor.execute('''
            INSERT INTO promo_codes (code, reward, max_uses, created_by, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        ''', (promo_code, reward, max_uses, message.from_user.id))
        
        conn.commit()
        conn.close()
        
        await message.answer(
            f"✅ Промокод успешно создан:\n"
            f"Код: {promo_code}\n"
            f"Награда: {reward} ⭐\n"
            f"Максимум использований: {max_uses}"
        )
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат команды.\n"
            "Использование: /present <промокод> <макс.использований> <награда>"
        )


@dp.message(Command("delp"))
async def delete_promo(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    
    try:
        _, promo_code = message.text.split()
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM promo_codes WHERE code = ?', (promo_code,))
        
        if cursor.rowcount > 0:
            conn.commit()
            await message.answer(f"✅ Промокод {promo_code} успешно удален")
        else:
            await message.answer(f"❌ Промокод {promo_code} не найден")
        
        conn.close()
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат команды.\n"
            "Использование: /delp <промокод>"
        )

class Form(StatesGroup):
    waiting_for_promo = State()


@dp.message(lambda message: message.text == "Промокод🎁")
async def promo_button(message: types.Message, state: FSMContext):
    await state.set_state(Form.waiting_for_promo)
    await message.answer("📝 Введите промокод:")


@dp.message(Form.waiting_for_promo)
async def handle_promo(message: types.Message, state: FSMContext):
    try:
        promo_code = message.text.strip()
        user_id = message.from_user.id
        
        if len(promo_code) > 20:
            await message.answer("❌ Слишком длинный промокод")
            await state.clear()
            return
            
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        
        cursor.execute('''
            SELECT reward, max_uses, current_uses 
            FROM promo_codes 
            WHERE code = ?
        ''', (promo_code,))
        
        promo_data = cursor.fetchone()
        
        if not promo_data:
            await message.answer("❌ Неверный промокод")
            await state.clear()
            return
            
        reward, max_uses, current_uses = promo_data
        
        
        cursor.execute('''
            SELECT 1 FROM used_promo_codes 
            WHERE user_id = ? AND code = ?
        ''', (user_id, promo_code))
        
        if cursor.fetchone():
            await message.answer("❌ Вы уже использовали этот промокод")
            await state.clear()
            return
        
        
        if current_uses >= max_uses:
            await message.answer("❌ Промокод больше не действителен")
            await state.clear()
            return
        
        
        cursor.execute('SELECT stars FROM users WHERE user_id = ?', (user_id,))
        current_stars = cursor.fetchone()[0]
        rank_bonus = await get_user_rank(current_stars)
        bonus_reward = int(reward * (1 + rank_bonus/100))
        
        
        cursor.execute('''
            UPDATE users 
            SET stars = stars + ? 
            WHERE user_id = ?
        ''', (bonus_reward, user_id))
        
        cursor.execute('''
            INSERT INTO used_promo_codes (user_id, code, used_at)
            VALUES (?, ?, datetime('now'))
        ''', (user_id, promo_code))
        
        cursor.execute('''
            UPDATE promo_codes 
            SET current_uses = current_uses + 1 
            WHERE code = ?
        ''', (promo_code,))
        
        conn.commit()
        
        await message.answer(
            f"✅ Промокод активирован!\n"
            f"Получено: {bonus_reward} ⭐"
        )
        
    except Exception as e:
        logging.error(f"Error in promo activation: {str(e)}")
        await message.answer("❌ Произошла ошибка при активации промокода")
        
    finally:
        conn.close()
        await state.clear()

@dp.message(lambda message: message.text == "Вывести звёзды🌟")
async def withdraw_stars(message: types.Message):
    await message.answer(
        f"💫 Минимальная сумма вывода: {MIN_WITHDRAWAL} звезд\n"
        f"📝 Введите количество звезд для вывода:"
    )


@dp.message(lambda message: message.text.isdigit())
async def process_withdrawal(message: types.Message):
    amount = int(message.text)
    user_id = message.from_user.id
    
    if amount < MIN_WITHDRAWAL:
        await message.answer(f"❌ Минимальная сумма вывода: {MIN_WITHDRAWAL} звезд")
        return
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    
    cursor.execute('SELECT stars FROM users WHERE user_id = ?', (user_id,))
    current_stars = cursor.fetchone()[0]
    
    if current_stars < amount:
        await message.answer("❌ Недостаточно звезд на балансе")
        return
    
    try:
        
        cursor.execute('''
            INSERT INTO withdrawal_requests (user_id, amount, created_at)
            VALUES (?, ?, datetime('now'))
        ''', (user_id, amount))
        
        
        cursor.execute('''
            UPDATE users 
            SET stars = stars - ? 
            WHERE user_id = ?
        ''', (amount, user_id))
        
        conn.commit()
        
        
        cursor.execute('SELECT admin_id FROM admins')
        admins = cursor.fetchall()
        
        for admin in admins:
            await bot.send_message(
                admin[0],
                f"💫 Новая заявка на вывод!\n"
                f"От: {message.from_user.first_name} ({user_id})\n"
                f"Сумма: {amount} звезд"
            )
        
        await message.answer(
            "✅ Заявка на вывод создана!\n"
            "Ожидайте обработки администратором."
        )
        
    except Exception as e:
        logging.error(f"Error in withdrawal: {str(e)}")
        await message.answer("❌ Произошла ошибка при создании заявки")
    
    finally:
        conn.close()
        

#@dp.message(Command("show_pay"))
#async def show_withdrawal_requests(message: types.Message):
#    if not await is_admin(message.from_user.id):
#        await message.answer("❌ У вас нет прав для выполнения этой команды")
#        return
#    
#    conn = sqlite3.connect('bot_database.db')
#    cursor = conn.cursor()
#    
#    cursor.execute('''
#        SELECT request_id, user_id, amount, created_at 
#        FROM withdrawal_requests 
#        WHERE status = 'pending' 
#        ORDER BY created_at ASC
#    ''')
#    
#    requests = cursor.fetchall()
#    conn.close()
#    
#    if not requests:
#        await message.answer("📝 Нет активных заявок на вывод")
#        return
#    
#    for req_id, user_id, amount, created_at in requests:
#        keyboard = InlineKeyboardMarkup(inline_keyboard=[
#            [
#                InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_withdrawal_{req_id}"),
#                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_withdrawal_{req_id}")
#            ]
#        ])
#        
#        await message.answer(
#            f"💫 Заявка #{req_id}\n"
#            f"👤 Пользователь: {user_id}\n"
#            f"💎 Сумма: {amount} звезд\n"
#            f"📅 Создана: {created_at}",
#            reply_markup=keyboard
#        )
#from aiogram.types import CallbackQuery

#@dp.callback_query(lambda c: c.data.startswith('approve_withdrawal_'))
#async def process_approve_withdrawal(callback: CallbackQuery):
#    if not await is_admin(callback.from_user.id):
#        pass
#        return

#    req_id = int(callback.data.split('_')[2])
#    admin_name = callback.from_user.first_name
#    
#    conn = sqlite3.connect('bot_database.db')
#    cursor = conn.cursor()
#    
#    try:
#        
#        cursor.execute('''
#            SELECT user_id, amount FROM withdrawal_requests 
#            WHERE request_id = ? AND status = 'pending'
#        ''', (req_id,))
#        request = cursor.fetchone()
#        
#        if not request:
#            await callback.answer("❌ Заявка не найдена или уже обработана")
#            return
#        
#        user_id, amount = request
#        current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
#        
#        
#        try:
#            user = await bot.get_chat(user_id)
#            user_name = user.first_name
#        except:
#            user_name = str(user_id)
#        
#        
#        cursor.execute('''
#            UPDATE withdrawal_requests 
#            SET status = 'approved', processed_at = ?
#            WHERE request_id = ?
#        ''', (current_time, req_id))
#        
#        conn.commit()
#        
#        
#        await bot.send_message(
#            user_id,
#            f"✅ Ваша заявка на вывод {amount} звезд была одобрена!"
#        )
#        
#        
#        check_message = (
#            f"💫 Чек!\n\n"
#            f"👤 Пользователь: {user_name}\n"
#            f"💎 Сумма: {amount} звезд\n"
#            f"📅 Дата: {current_time}\n"
#            f"✅ Одобрил: {admin_name}"
#        )
#        
#        await bot.send_message(
#            chat_id="@stars1_1_b",
#            text=check_message
#        )
#        
#        await callback.message.edit_text(
#            callback.message.text + "\n\n✅ Заявка одобрена",
#            reply_markup=None
#        )
#        
#        await callback.answer("✅ Заявка успешно одобрена")
#        
#    except Exception as e:
#        logging.error(f"Error in approve withdrawal: {str(e)}")
#        await callback.answer("❌ Произошла ошибка при обработке заявки")
#        
#    finally:
#        conn.close()
#        
#@dp.callback_query(lambda c: c.data.startswith('reject_withdrawal_'))
#async def process_reject_withdrawal(callback: CallbackQuery):
#    
#    if not await is_admin(callback.from_user.id):
#        pass
#        return

#    
#    req_id = int(callback.data.split('_')[2])
#    
#    conn = sqlite3.connect('bot_database.db')
#    cursor = conn.cursor()
#    
#    try:
#         
#        cursor.execute('''
#            SELECT user_id, amount FROM withdrawal_requests 
#            WHERE request_id = ? AND status = 'pending'
#        ''', (req_id,))
#        request = cursor.fetchone()
#        
#        if not request:
#            await callback.answer("❌ Заявка не найдена или уже обработана")
#            return
#        
#        user_id, amount = request
#        
#        
#        cursor.execute('''
#            UPDATE users 
#            SET stars = stars + ? 
#            WHERE user_id = ?
#        ''', (amount, user_id))
#        
#        
#        cursor.execute('''
#            UPDATE withdrawal_requests 
#            SET status = 'rejected', processed_at = ? 
#            WHERE request_id = ?
#        ''', (datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), req_id))
#        
#        conn.commit()
#        
#        
#        await bot.send_message(
#            user_id,
#            f"❌ Ваша заявка на вывод {amount} звезд была отклонена.\n"
#            "Возможные причины: \n\n"
#            """Админ не может с вами связаться
#            
#               Сейчас у нас пустая казна
#               
#               У вас более 1-го варна
#               
#               Отсутсвие @username
#               
#               """
#            f"💫 Звезды возвращены на ваш баланс!"
#        )
#        
#         
#        await callback.message.edit_text(
#            f"{callback.message.text}\n\n❌ Заявка отклонена администратором {callback.from_user.first_name}",
#            reply_markup=None
#        )
#        
#        await callback.answer("✅ Заявка успешно отклонена")
#        
#    except Exception as e:
#        logging.error(f"Error in reject withdrawal: {str(e)}")
#        await callback.answer("❌ Произошла ошибка при обработке заявки")
#        
#    finally:
#        conn.close()
        
        
@dp.message(Command("on"))
async def toggle_review_payment(message: types.Message):
    if not await is_admin(message.from_user.id):
        pass
        return
    
    try:
        _, mode = message.text.split()
        if mode.lower() == 'true':
            review_payment_status['enabled'] = True
            review_payment_status['mode'] = 'positive'
            await message.answer("✅ Оплата за положительные отзывы включена")
        elif mode.lower() == 'false':
            review_payment_status['enabled'] = True
            review_payment_status['mode'] = 'all'
            await message.answer("✅ Оплата за все отзывы включена")
        else:
            await message.answer("❌ Неверный параметр. Используйте True или False")
    except ValueError:
        await message.answer(
            "❌ Неверный формат команды.\n"
            "Использование: /on True|False"
        )


@dp.message(Command("off"))
async def disable_review_payment(message: types.Message):
    if not await is_admin(message.from_user.id):
        pass
        return
    
    review_payment_status['enabled'] = False
    await message.answer("✅ Оплата за отзывы отключена")


async def is_positive_review(text: str) -> bool:
     
    
    negative_words = {'плохо', 'ужасно', 'отстой', 'не нравится', 'фу', 'говно', 'хуйня', '👎', '💩', '😠'}
    
    positive_words = {'хорошо', 'отлично', 'супер', 'крутой', 'классный', 'нравится', 'здорово', '👍', '❤️', '😊', 'выводит', 'платит', 'платят', 'выводят'}
    
    text = text.lower()
    positive_count = sum(1 for word in positive_words if word in text)
    negative_count = sum(1 for word in negative_words if word in text)
    
    return positive_count > negative_count



@dp.message(Command("eb"))
async def set_daily_bonus(message: types.Message):
    if not await is_admin(message.from_user.id):
        pass
        return
    
    try:
        _, amount, max_claims = message.text.split()
        daily_bonus['amount'] = int(amount)
        daily_bonus['remaining'] = int(max_claims)
        
        await message.answer(
            f"✅ Ежедневный бонус установлен:\n"
            f"Сумма: {amount} звезд\n"
            f"Доступно активаций: {max_claims}"
        )
    except ValueError:
        await message.answer(
            "❌ Неверный формат команды.\n"
            "Использование: /eb <сумма> <количество_активаций>"
        )
        
        
@dp.message(lambda message: message.text == "Ежедневный бонус📦")
async def daily_bonus_button(message: types.Message):
    user_id = message.from_user.id
    
    if daily_bonus['amount'] == 0:
        await message.answer("❌ Ежедневный бонус пока не установлен администратором")
        return
    
    if daily_bonus['remaining'] <= 0:
        await message.answer("❌ На сегодня все бонусы уже разобраны")
        return
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    try:
        
        cursor.execute('''
            SELECT last_daily FROM users 
            WHERE user_id = ?
        ''', (user_id,))
        
        last_daily = cursor.fetchone()[0]
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        if last_daily == current_date:
            await message.answer("❌ Вы уже получили сегодняшний бонус")
            return
        
        
        cursor.execute('SELECT stars FROM users WHERE user_id = ?', (user_id,))
        current_stars = cursor.fetchone()[0]
        rank_bonus = await get_user_rank(current_stars)
        bonus_amount = int(daily_bonus['amount'] * (1 + rank_bonus/100))
        
        
        cursor.execute('''
            UPDATE users 
            SET stars = stars + ?, 
                last_daily = ? 
            WHERE user_id = ?
        ''', (bonus_amount, current_date, user_id))
        
         
        daily_bonus['remaining'] -= 1
        
        conn.commit()
        
        await message.answer(
            f"🎁 Вы получили ежедневный бонус!\n"
            f"💫 Начислено: {bonus_amount} звезд\n"
            f"📊 Осталось бонусов: {daily_bonus['remaining']}"
        )
        
    except Exception as e:
        logging.error(f"Error in daily bonus: {str(e)}")
        await message.answer("❌ Произошла ошибка при получении бонуса")
    
    finally:
        conn.close()
from aiogram.filters import Command
from aiogram.types import Message


@dp.message(Command("name"))
async def set_username(message: Message):
    
    if message.from_user.id != OWNER_ID:
        pass
        return
    
    
    try:
        args = message.text.split()
        if len(args) < 3:
            await message.answer("❌ Использование: /name <id> <name>")
            return
        
        user_id = int(args[1])
        
        new_name = ' '.join(args[2:])
        
        
        if len(new_name) > 32:
            await message.answer("❌ Имя слишком длинное! Максимум 32 символа.")
            return
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        
        cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            await message.answer("❌ Пользователь не найден в базе данных!")
            conn.close()
            return
        
        
        cursor.execute('''
            UPDATE users 
            SET username = ? 
            WHERE user_id = ?
        ''', (new_name, user_id))
        
        conn.commit()
        conn.close()
        
        await message.answer(
            f"✅ Имя пользователя успешно обновлено!\n"
            f"ID: {user_id}\n"
            f"Новое имя: {new_name}"
        )
        
    except ValueError:
        await message.answer("❌ ID пользователя должен быть числом!")
    except Exception as e:
        logging.error(f"Error in set_username: {e}")
        await message.answer("❌ Произошла ошибка при обновлении имени!")                                

@dp.message(Command("give"))
async def give_stars(message: types.Message):
    if not await is_admin(message.from_user.id):
        pass
        return
    
    try:
        _, user_id, amount = message.text.split()
        user_id = int(user_id)
        amount = int(amount)
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users 
            SET stars = stars + ? 
            WHERE user_id = ?
        ''', (amount, user_id))
        
        if cursor.rowcount > 0:
            conn.commit()
            await message.answer(f"✅ Пользователю {user_id} начислено {amount} звезд")
            await bot.send_message(
                user_id,
                f"💫 Администратор начислил вам {amount} звезд!"
            )
        else:
            await message.answer("❌ Пользователь не найден")
        
        conn.close()
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат команды.\n"
            "Использование: /give <id_пользователя> <количество>"
        )


@dp.message(Command("null"))
async def null_balance(message: types.Message):
    if not await is_admin(message.from_user.id):
        pass
        return
    
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        amount = parts[2].lower()
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        if amount == "all":
            cursor.execute('''
                UPDATE users 
                SET stars = 0 
                WHERE user_id = ?
            ''', (user_id,))
        else:
            amount = int(amount)
            cursor.execute('''
                UPDATE users 
                SET stars = CASE
                    WHEN stars <= ? THEN 0
                    ELSE stars - ?
                END 
                WHERE user_id = ?
            ''', (amount, amount, user_id))
        
        if cursor.rowcount > 0:
            conn.commit()
            await message.answer(f"✅ Баланс пользователя {user_id} обнулен")
            await bot.send_message(
                user_id,
                "⚠️ Ваш баланс был изменен администратором"
            )
        else:
            await message.answer("❌ Пользователь не найден")
        
        conn.close()
        
    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат команды.\n"
            "Использование: /null <id_пользователя> <количество|all>"
        )
        
        

@dp.message(Command("addmin"))
async def add_admin(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Только владелец бота может добавлять администраторов")
        return
    
    try:
        _, new_admin_id = message.text.split()
        new_admin_id = int(new_admin_id)
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO admins (admin_id, added_by, added_date)
            VALUES (?, ?, datetime('now'))
        ''', (new_admin_id, message.from_user.id))
        
        conn.commit()
        conn.close()
        
        await message.answer(f"✅ Пользователь {new_admin_id} добавлен как администратор")
        await bot.send_message(
            new_admin_id,
            "🎉 Вам выданы права администратора!"
        )
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат команды.\n"
            "Использование: /addmin <id_пользователя>"
        )

@dp.message(Command("delmin"))
async def remove_admin(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("❌ Только владелец бота может удалять администраторов")
        return
    
    try:
        _, admin_id, *reason_parts = message.text.split()
        admin_id = int(admin_id)
        reason = " ".join(reason_parts) if reason_parts else "Причина не указана"
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM admins WHERE admin_id = ?', (admin_id,))
        
        if cursor.rowcount > 0:
            conn.commit()
            await message.answer(f"✅ Администратор {admin_id} удален")
            await bot.send_message(
                admin_id,
                f"⚠️ Ваши права администратора были отозваны.\nПричина: {reason}"
            )
        else:
            await message.answer("❌ Администратор не найден")
        
        conn.close()
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат команды.\n"
            "Использование: /delmin <id_пользователя> <причина>"
        )

@dp.message(Command("oper"))
async def check_admin(message: types.Message):
    is_admin_user = await is_admin(message.from_user.id)
    if is_admin_user:
        if message.from_user.id == OWNER_ID:
            await message.answer("👑 Вы являетесь владельцем бота")
        else:
            await message.answer("✅ Вы являетесь администратором бота")
    else:
        await message.answer("❌ Вы не являетесь администратором")


@dp.message(Command("user"))
async def user_info(message: types.Message):
    if not await is_admin(message.from_user.id):
        pass
        return
    
    try:
        _, user_id = message.text.split()
        user_id = int(user_id)
        
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT u.stars, u.warnings, u.banned, u.last_daily,
                   COUNT(r.referred_id) as referrals
            FROM users u
            LEFT JOIN referrals r ON u.user_id = r.referrer_id
            WHERE u.user_id = ?
            GROUP BY u.user_id
        ''', (user_id,))
        
        user_data = cursor.fetchone()
        
        if user_data:
            stars, warnings, banned, last_daily, referrals = user_data
            rank_bonus = await get_user_rank(stars)
            
            user_info = (
                f"📊 Информация о пользователе {user_id}:\n"
                f"💫 Баланс: {stars} звезд\n"
                f"👥 Рефералов: {referrals}\n"
                f"⚠️ Предупреждений: {warnings}/3\n"
                f"🏆 Ранг: +{rank_bonus}% к наградам\n"
                f"📅 Последний бонус: {last_daily or 'Никогда'}\n"
                f"🚫 Забанен: {'Да' if banned else 'Нет'}"
            )
            
            await message.answer(user_info)
        else:
            await message.answer("❌ Пользователь не найден")
        
        conn.close()
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат команды.\n"
            "Использование: /user <id_пользователя>"
        )
        
        
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
import logging
import sqlite3

class ReviewStates(StatesGroup):
    waiting_for_review = State()

@dp.message(lambda message: message.text == "Оставить отзыв📧")
async def request_review(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS review_cooldowns
                     (user_id INTEGER PRIMARY KEY, last_review_time TEXT)''')
    
    
    cursor.execute('SELECT last_review_time FROM review_cooldowns WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    if result:
        last_review_time = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
        time_passed = datetime.utcnow() - last_review_time
        
        if time_passed < timedelta(hours=1):
            minutes_left = 60 - (time_passed.seconds // 60)
            await message.answer(f"⏳ Вы сможете оставить следующий отзыв через {minutes_left} минут")
            conn.close()
            return
    
    await message.answer(
        "📝 Пожалуйста, напишите ваш отзыв о боте.\n"
        "Мы ценим ваше мнение!"
    )
    await state.set_state(ReviewStates.waiting_for_review)
    conn.close()

@dp.message(ReviewStates.waiting_for_review)
async def process_review(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    try:
        
        await bot.forward_message(
            chat_id=-1002166881231,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
        
         
        conn = sqlite3.connect('bot_database.db')
        cursor = conn.cursor()
        current_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''INSERT OR REPLACE INTO review_cooldowns (user_id, last_review_time)
                         VALUES (?, ?)''', (user_id, current_time))
        conn.commit()
        
        
        if review_payment_status['enabled']:
            should_reward = False
            if review_payment_status['mode'] == 'all':
                should_reward = True
            elif review_payment_status['mode'] == 'positive':
                should_reward = await is_positive_review(message.text)
            
            if should_reward:
                
                cursor.execute('SELECT stars FROM users WHERE user_id = ?', (user_id,))
                current_stars = cursor.fetchone()[0]
                rank_bonus = await get_user_rank(current_stars)
                reward = int(1 * (1 + rank_bonus/100))
                
                cursor.execute('''
                    UPDATE users 
                    SET stars = stars + ? 
                    WHERE user_id = ?
                ''', (reward, user_id))
                
                conn.commit()
                await message.answer(
                    f"✨ Спасибо за отзыв! Вы получили {reward} звезд!\n"
                    "💫 Ваш отзыв успешно отправлен в канал с отзывами."
                )
            else:
                await message.answer(
                    "✨ Спасибо за отзыв!\n"
                    "💫 Ваш отзыв успешно отправлен в канал с отзывами."
                )
            
        else:
            await message.answer(
                "✨ Спасибо за отзыв!\n"
                "💫 Ваш отзыв успешно отправлен в канал с отзывами."
            )
            
        conn.close()
        await state.clear()
            
    except Exception as e:
        logging.error(f"Error in review handling: {str(e)}")
        await message.answer("✨ Спасибо за отзыв!\n"
                "💫 Ваш отзыв успешно отправлен в канал с отзывами.")
        await state.clear()
        
@dp.message(lambda message: len(message.text) > 10)
async def handle_review(message: types.Message):
    user_id = message.from_user.id

    try:
        
        await bot.send_message(
            chat_id=-1002166881231,
            text=(
                "🌟 Отзыв 🌟\n\n"
                f"💬 Отзыв от: @{message.from_user.username or 'аноним'}\n"
                
            )
        )
        
        await bot.forward_message(
            chat_id=-1002166881231,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
    
        
        
        if review_payment_status['enabled']:
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            
            should_reward = False
            if review_payment_status['mode'] == 'all':
                should_reward = True
            elif review_payment_status['mode'] == 'positive':
                should_reward = await is_positive_review(message.text)
            
            if should_reward:
                
                cursor.execute('SELECT stars FROM users WHERE user_id = ?', (user_id,))
                current_stars = cursor.fetchone()[0]
                rank_bonus = await get_user_rank(current_stars)
                reward = int(1 * (1 + rank_bonus/100))
                
                cursor.execute('''
                    UPDATE users 
                    SET stars = stars + ? 
                    WHERE user_id = ?
                ''', (reward, user_id))
                
                conn.commit()
                await message.answer(f"✨ Спасибо за отзыв! Вы получили {reward} звезд!")
            else:
                await message.answer("✨ Спасибо за отзыв!")
            
            conn.close()
        else:
            await message.answer("✨ Спасибо за отзыв!")
            
    except Exception as e:
        logging.error(f"Error in review handling: {str(e)}")
        await message.answer(
        "✨ Спасибо за отзыв!\n"
        "💫 Ваш отзыв успешно отправлен в канал с отзывами.")


daily_bonus = {
    'amount': 0,
    'remaining': 0
}        

@dp.message(Command("info"))
async def info_command(message: types.Message):
    await message.answer(
        "ℹ️ Добро пожаловать в нашего бота!\n\n"
        "Доступные функции:\n"
        "1️⃣ Заработать звезды⭐\n"
        "2️⃣ Ежедневный бонус📦\n"
        "3️⃣ Участвовать в заданиях📚\n"
        "4️⃣ Вывод звёзд🌟\n\n"
        "Для вопросов: /info\n"
        "Проверка статуса админа: /oper\n"
        "Магазин: /vip_shop"
    )
        
@dp.message(Command("adc"))
async def admin_commands(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return

    await message.answer(
        "⚙️ Команды для администраторов:\n"
        "/addmin <id> - Добавить администратора\n"
        "/delmin <id> - Удалить администратора\n"
        "/warn <id> <причина> - Выдать предупреждение\n"
        "/ban <id> <причина> - Забанить пользователя\n"
        "/unban <id> - Разбанить пользователя\n"
            "/give <id> <количество> - Начислить звезды\n" "/present <код> <макс.использований> <награда> - Создать промокод\n"
        "/delp <код> - Удалить промокод\n"
        "/name <id> <имя> - Изменить имя пользователя\n"
        "/null <id> <количество|all> - Обнулить баланс\n"
        "/eb <сумма> <макс.активаций> - Установить ежедневный бонус"
        "/search <id или иия>"
    )
    



async def reset_daily_bonuses():
    while True:
        now = datetime.now()
        next_reset = datetime.combine(now.date() + timedelta(days=1), time())
        await asyncio.sleep((next_reset - now).total_seconds())
        
        if daily_bonus['amount'] > 0:
            logging.info("Resetting daily bonuses...")
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET last_daily = NULL')
            conn.commit()
            conn.close()
            


print('Бот Работает')


async def main():
    await init_db()
    
    
    asyncio.create_task(reset_daily_bonuses())
    
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.info("Starting bot...")
    asyncio.run(main())
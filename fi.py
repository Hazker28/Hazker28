import asyncio
import sqlite3
import random
import hashlib
from datetime import datetime
from typing import Union, List, Dict
import logging
import os
import sys
import shutil

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardMarkup,
    Message
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Конфигурация бота
TOKEN = '8163139120:AAHg1QkcPAmiHPFWM0NIUtOj6G0OMVUyEpc'
REQUIRED_CHANNELS = [-1002166881231]
OWNERS_IDS = [1690656583, 6673580092]
DEVELOPERS_IDS = [6675836752, 6673580092]
ADMIN_CHANNEL = -1002363437612
REVIEWS_CHANNEL = -1002166881231
DATABASE_FILE = 'basa_dannih.db'

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_log.txt', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Настройка работы с datetime в SQLite
def adapt_datetime(dt):
    """Преобразование datetime в строку для SQLite"""
    return dt.isoformat()

def convert_datetime(value):
    """Преобразование строки из SQLite обратно в datetime"""
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None

# Регистрация адаптеров для работы с датами
sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("timestamp", convert_datetime)

def get_db_connection():
    """Создаёт соединение с базой данных с правильными настройками"""
    return sqlite3.connect(
        DATABASE_FILE,
        detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        check_same_thread=False
    )

# Инициализация бота
bot = Bot(token=TOKEN)
dp = Dispatcher()
# Состояния FSM
class UserStates(StatesGroup):
    waiting_for_proof = State()
    waiting_for_promo = State()
    waiting_for_withdrawal = State()
    waiting_for_stars_amount = State()

class AdminStates(StatesGroup):
    waiting_for_promo_details = State()
    waiting_for_task_details = State()
    waiting_for_announcement = State()

# Callback data классы
class SubscriptionCallback(CallbackData, prefix="sub"):
    action: str

class TaskCallback(CallbackData, prefix="task"):
    task_id: int
    action: str

class WithdrawCallback(CallbackData, prefix="withdraw"):
    amount: int

# Инициализация базы данных
# Инициализация базы данных
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Таблица пользователей
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        registration_date TIMESTAMP,
        balance INTEGER DEFAULT 0,
        referrer_id INTEGER,
        referrals_count INTEGER DEFAULT 0,
        warns_count INTEGER DEFAULT 0,
        role TEXT DEFAULT 'user',
        is_banned BOOLEAN DEFAULT 0
    )
    ''')
    
    # Таблица промокодов
    cur.execute('''
    CREATE TABLE IF NOT EXISTS promocodes (
        code TEXT PRIMARY KEY,
        stars INTEGER,
        max_activations INTEGER,
        current_activations INTEGER DEFAULT 0,
        created_by INTEGER,
        created_at TIMESTAMP
    )
    ''')
    
    # Таблица использованных промокодов
    cur.execute('''
    CREATE TABLE IF NOT EXISTS used_promocodes (
        user_id INTEGER,
        code TEXT,
        used_at TIMESTAMP,
        PRIMARY KEY (user_id, code)
    )
    ''')
    
    # Таблица заданий
    cur.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        task_id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_link TEXT,
        stars INTEGER,
        max_activations INTEGER,
        current_activations INTEGER DEFAULT 0,
        conditions TEXT,
        created_by INTEGER,
        created_at TIMESTAMP
    )
    ''')
    
    # Таблица выполненных заданий
    cur.execute('''
    CREATE TABLE IF NOT EXISTS completed_tasks (
        user_id INTEGER,
        task_id INTEGER,
        completed_at TIMESTAMP,
        proof_file_id TEXT,
        moderator_id INTEGER,
        status TEXT DEFAULT 'pending',
        PRIMARY KEY (user_id, task_id)
    )
    ''')
    
    # Таблица выводов
    cur.execute('''
    CREATE TABLE IF NOT EXISTS withdrawals (
        withdrawal_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        created_at TIMESTAMP,
        status TEXT DEFAULT 'pending'
    )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

# Обновление ролей пользователей
async def update_user_roles():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Обновляем разработчиков
    developers_list = ','.join(map(str, DEVELOPERS_IDS))
    if developers_list:
        cur.execute(f'''
        UPDATE users 
        SET role = 'developer' 
        WHERE user_id IN ({developers_list})
        ''')
    
    # Обновляем владельцев
    owners_list = ','.join(map(str, OWNERS_IDS))
    if owners_list:
        cur.execute(f'''
        UPDATE users 
        SET role = 'owner' 
        WHERE user_id IN ({owners_list}) 
        AND user_id NOT IN ({developers_list})
        ''')
    
    conn.commit()
    conn.close()
    logger.info("Роли пользователей обновлены")


async def add_user(user_id: int, username: str, first_name: str, referrer_id: int = None):
    """
    Добавляет нового пользователя в базу данных с правильной ролью
    """
    # Определяем роль пользователя
    if user_id in DEVELOPERS_IDS:
        role = 'developer'
    elif user_id in OWNERS_IDS:
        role = 'owner'
    else:
        role = 'user'

    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute('''
        INSERT OR IGNORE INTO users (
            user_id, username, first_name, registration_date, 
            referrer_id, role
        ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, datetime.now(), referrer_id, role))
        
        if referrer_id:
            cur.execute('''
            UPDATE users SET referrals_count = referrals_count + 1
            WHERE user_id = ?
            ''', (referrer_id,))
        
        conn.commit()
        logger.info(f"Добавлен новый пользователь: {user_id} с ролью {role}")
    except Exception as e:
        logger.error(f"Ошибка при добавлении пользователя: {e}")
    finally:
        conn.close()

async def get_user(user_id: int) -> dict:
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cur.fetchone()
    
    conn.close()
    
    if user:
        return {
            'user_id': user[0],
            'username': user[1],
            'first_name': user[2],
            'registration_date': user[3],
            'balance': user[4],
            'referrer_id': user[5],
            'referrals_count': user[6],
            'warns_count': user[7],
            'role': user[8],
            'is_banned': user[9]
        }
    return None
    
# Вспомогательные функции
async def check_subscription(user_id: int) -> bool:
    try:
        for channel_id in REQUIRED_CHANNELS:
            member = await bot.get_chat_member(channel_id, user_id)
            if member.status in ['left', 'kicked', 'banned']:
                return False
        return True
    except Exception:
        return False

async def get_subscription_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for channel_id in REQUIRED_CHANNELS:
        chat = await bot.get_chat(channel_id)
        button = InlineKeyboardButton(
            text=f"📢 {chat.title}",
            url=f"https://t.me/{chat.username}"
        )
        builder.add(button)
    
    builder.row(InlineKeyboardButton(
        text="✅ Проверить подписку",
        callback_data="sub:check"
    ))
    return builder.as_markup()

async def get_main_keyboard(user_role: str) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="💫 Заработать звёзды")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🎁 Промокод")],
        [KeyboardButton(text="📋 Задания"), KeyboardButton(text="💎 Вывести звёзды")],
        [KeyboardButton(text="🏆 Топ 10")]
    ]
    
    if user_role in ['moderator', 'admin', 'owner', 'developer']:
        buttons.append([KeyboardButton(text="⚡️ Панель модератора")])
    
    if user_role in ['admin', 'owner', 'developer']:
        buttons.append([KeyboardButton(text="🛠 Панель администратора")])
    
    if user_role in ['owner', 'developer']:
        buttons.append([KeyboardButton(text="👑 Панель владельца")])
        
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True
    )

# Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)
    
    if user and not user['is_banned']:
        await message.answer(
            "С возвращением! Выберите действие:",
            reply_markup=await get_main_keyboard(user['role'])
        )
        return

    # Проверяем реферальную ссылку
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        
    if not user:
        await add_user(
            user_id,
            message.from_user.username,
            message.from_user.first_name,
            referrer_id
        )
    
    await message.answer(
        "👋 Добро пожаловать в бота!\n"
        "📢 Для продолжения подпишитесь на наши каналы:",
        reply_markup=await get_subscription_keyboard()
    )

@dp.callback_query(SubscriptionCallback.filter(F.action == "check"))
async def check_subscription_callback(callback: types.CallbackQuery, state: FSMContext):
    if await check_subscription(callback.from_user.id):
        user = await get_user(callback.from_user.id)
        
        # Начисление звезды рефереру
        if user['referrer_id']:
            conn = sqlite3.connect(DATABASE_FILE)
            cur = conn.cursor()
            cur.execute('''
                UPDATE users 
                SET balance = balance + 1 
                WHERE user_id = ? AND referrer_id IS NOT NULL
            ''', (user['referrer_id'],))
            conn.commit()
            conn.close()
            
            # Уведомление реферера
            try:
                await bot.send_message(
                    user['referrer_id'],
                    f"🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!\n"
                    f"💫 Вам начислена 1 звезда!"
                )
            except:
                pass

        await callback.message.edit_text(
            "✅ Проверка прошла успешно!\n"
            "Добро пожаловать в главное меню!",
            reply_markup=None
        )
        
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=await get_main_keyboard(user['role'])
        )
    else:
        await callback.answer(
            "❌ Вы не подписались на все каналы!",
            show_alert=True
        )

# Обработчик профиля
@dp.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return
    
    text = (
        f"👤 **Ваш профиль:**\n"
        f"├ ID: `{user['user_id']}`\n"
        f"├ Баланс: {user['balance']} 💫\n"
        f"├ Рефералов: {user['referrals_count']}\n"
        f"├ Статус: {user['role']}\n"
        f"└ Предупреждений: {user['warns_count']}/3\n\n"
        f"📅 Дата регистрации: {user['registration_date']}"
    )
    
    await message.answer(
        text,
        parse_mode="Markdown"
    )

# Обработчик заработка звёзд
@dp.message(F.text == "💫 Заработать звёзды")
async def earn_stars(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return
        
    ref_link = f"https://t.me/{(await bot.me()).username}?start={user['user_id']}"
    
    text = (
        f"🔗 Ваша реферальная ссылка:\n"
        f"`{ref_link}`\n\n"
        f"За каждого приглашенного пользователя вы получите 1 звезду!"
    )
    
    await message.answer(
        text,
        parse_mode="Markdown"
    )
    
# Система промокодов
async def create_promo(code: str, stars: int, max_activations: int, created_by: int):
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO promocodes (code, stars, max_activations, created_by, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (code, stars, max_activations, created_by, datetime.now()))
    
    conn.commit()
    conn.close()

async def check_promo(code: str, user_id: int) -> tuple[bool, str, int]:
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    # Проверяем существование промокода
    cur.execute('SELECT * FROM promocodes WHERE code = ?', (code,))
    promo = cur.fetchone()
    
    if not promo:
        conn.close()
        return False, "❌ Промокод не существует!", 0
        
    # Проверяем количество активаций
    if promo[3] >= promo[2]:  # current_activations >= max_activations
        conn.close()
        return False, "❌ Промокод больше не действителен!", 0
        
    # Проверяем, использовал ли пользователь этот промокод
    cur.execute('''
        SELECT * FROM used_promocodes 
        WHERE user_id = ? AND code = ?
    ''', (user_id, code))
    
    if cur.fetchone():
        conn.close()
        return False, "❌ Вы уже использовали этот промокод!", 0
    
    conn.close()
    return True, "✅ Промокод действителен!", promo[1]  # stars

@dp.message(F.text == "🎁 Промокод")
async def promo_handler(message: Message, state: FSMContext):
    await message.answer(
        "📝 Введите промокод:",
        reply_markup=types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="🔙 Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_promo)

@dp.message(UserStates.waiting_for_promo)
async def process_promo(message: Message, state: FSMContext):
    if message.text == "🔙 Отмена":
        await state.clear()
        user = await get_user(message.from_user.id)
        await message.answer(
            "Действие отменено",
            reply_markup=await get_main_keyboard(user['role'])
        )
        return

    valid, msg, stars = await check_promo(message.text, message.from_user.id)
    
    if valid:
        conn = sqlite3.connect(DATABASE_FILE)
        cur = conn.cursor()
        
        # Обновляем баланс пользователя
        cur.execute('''
            UPDATE users 
            SET balance = balance + ? 
            WHERE user_id = ?
        ''', (stars, message.from_user.id))
        
        # Отмечаем промокод как использованный
        cur.execute('''
            INSERT INTO used_promocodes (user_id, code, used_at)
            VALUES (?, ?, ?)
        ''', (message.from_user.id, message.text, datetime.now()))
        
        # Увеличиваем счетчик активаций
        cur.execute('''
            UPDATE promocodes 
            SET current_activations = current_activations + 1
            WHERE code = ?
        ''', (message.text,))
        
        conn.commit()
        conn.close()
        
        await message.answer(
            f"✅ Промокод активирован!\n💫 Получено звёзд: {stars}",
            reply_markup=await get_main_keyboard((await get_user(message.from_user.id))['role'])
        )
    else:
        await message.answer(
            msg,
            reply_markup=await get_main_keyboard((await get_user(message.from_user.id))['role'])
        )
    
    await state.clear()

# Система заданий
async def create_task(channel_link: str, stars: int, max_activations: int, conditions: str, created_by: int):
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO tasks (
            channel_link, stars, max_activations, conditions, 
            created_by, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (channel_link, stars, max_activations, conditions, created_by, datetime.now()))
    
    task_id = cur.lastrowid
    
    conn.commit()
    conn.close()
    
    return task_id

async def get_available_tasks(user_id: int) -> List[Dict]:
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    cur.execute('''
        SELECT t.* FROM tasks t
        LEFT JOIN completed_tasks ct 
            ON t.task_id = ct.task_id AND ct.user_id = ?
        WHERE ct.task_id IS NULL
            AND t.current_activations < t.max_activations
    ''', (user_id,))
    
    tasks = cur.fetchall()
    conn.close()
    
    return [
        {
            'task_id': t[0],
            'channel_link': t[1],
            'stars': t[2],
            'max_activations': t[3],
            'current_activations': t[4],
            'conditions': t[5]
        }
        for t in tasks
    ]

@dp.message(F.text == "📋 Задания")
async def show_tasks(message: Message):
    tasks = await get_available_tasks(message.from_user.id)
    
    if not tasks:
        await message.answer(
            "😔 Доступных заданий пока нет.\n"
            "Загляните позже!"
        )
        return

    for task in tasks:
        keyboard = InlineKeyboardBuilder()
        keyboard.add(InlineKeyboardButton(
            text="📲 Перейти в канал",
            url=task['channel_link']
        ))
        keyboard.add(InlineKeyboardButton(
            text="✅ Отправить доказательство",
            callback_data=f"task:{task['task_id']}:submit"
        ))

        text = (
            f"📌 Задание #{task['task_id']}\n"
            f"💫 Награда: {task['stars']} звёзд\n"
            f"📝 Условие: {task['conditions']}\n"
            f"👥 Выполнено: {task['current_activations']}/{task['max_activations']}"
        )
        
        await message.answer(text, reply_markup=keyboard.as_markup())
        
            
# Система модерации заданий
@dp.callback_query(lambda c: c.data.startswith('task:'))
async def task_callback_handler(callback: types.CallbackQuery, state: FSMContext):
    _, task_id, action = callback.data.split(':')
    task_id = int(task_id)
    
    if action == 'submit':
        await state.update_data(current_task=task_id)
        await callback.message.answer(
            "📸 Отправьте скриншот или видео подтверждение выполнения задания.\n"
            "Для отмены нажмите кнопку 'Отмена'.",
            reply_markup=types.ReplyKeyboardMarkup(
                keyboard=[[types.KeyboardButton(text="🔙 Отмена")]],
                resize_keyboard=True
            )
        )
        await state.set_state(UserStates.waiting_for_proof)
        await callback.answer()

@dp.message(UserStates.waiting_for_proof, F.photo | F.video | F.document)
async def handle_proof_submission(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data.get('current_task')
    
    if not task_id:
        await state.clear()
        return
    
    # Получаем file_id доказательства
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.video:
        file_id = message.video.file_id
    else:
        file_id = message.document.file_id
    
    # Выбираем случайного модератора
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute('''
        SELECT user_id FROM users 
        WHERE role IN ('moderator', 'admin', 'owner', 'developer')
        ORDER BY RANDOM() LIMIT 1
    ''')
    moderator = cur.fetchone()
    
    if not moderator:
        await message.answer("❌ Ошибка: нет доступных модераторов")
        await state.clear()
        conn.close()
        return
    
    moderator_id = moderator[0]
    
    # Сохраняем заявку
    cur.execute('''
        INSERT INTO completed_tasks (
            user_id, task_id, completed_at, proof_file_id, moderator_id
        ) VALUES (?, ?, ?, ?, ?)
    ''', (message.from_user.id, task_id, datetime.now(), file_id, moderator_id))
    
    task_submission_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    # Отправляем доказательство в канал проверки
    proof_message = f"📝 Заявка #{task_submission_id}\n"
    proof_message += f"👤 Пользователь: {message.from_user.id}\n"
    proof_message += f"📋 Задание #{task_id}\n"
    proof_message += f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    await bot.send_message(
        ADMIN_CHANNEL,
        proof_message
    )
    
    if message.photo:
        await bot.send_photo(ADMIN_CHANNEL, file_id)
    elif message.video:
        await bot.send_video(ADMIN_CHANNEL, file_id)
    else:
        await bot.send_document(ADMIN_CHANNEL, file_id)
    
    # Уведомляем модератора
    await bot.send_message(
        moderator_id,
        f"📨 Вам назначена новая заявка #{task_submission_id} на проверку!\n"
        f"Используйте /check_{task_submission_id} для проверки."
    )
    
    await message.answer(
        "✅ Ваша заявка отправлена на проверку!\n"
        "Ожидайте решения модератора.",
        reply_markup=await get_main_keyboard((await get_user(message.from_user.id))['role'])
    )
    await state.clear()

# Модераторские команды
@dp.message(lambda m: m.text and m.text.startswith('/check_'))
async def check_submission(message: Message):
    user = await get_user(message.from_user.id)
    if user['role'] not in ['moderator', 'admin', 'owner', 'developer']:
        return
    
    try:
        submission_id = int(message.text.split('_')[1])
    except:
        await message.answer("❌ Неверный формат команды")
        return
    
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    cur.execute('''
        SELECT ct.*, t.stars, t.channel_link
        FROM completed_tasks ct
        JOIN tasks t ON ct.task_id = t.task_id
        WHERE ct.rowid = ? AND ct.moderator_id = ? AND ct.status = 'pending'
    ''', (submission_id, message.from_user.id))
    
    submission = cur.fetchone()
    conn.close()
    
    if not submission:
        await message.answer("❌ Заявка не найдена или уже проверена")
        return
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        InlineKeyboardButton(
            text="✅ Одобрить",
            callback_data=f"mod:approve:{submission_id}"
        ),
        InlineKeyboardButton(
            text="❌ Отклонить",
            callback_data=f"mod:reject:{submission_id}"
        )
    )
    
    text = (
        f"📝 Заявка #{submission_id}\n"
        f"👤 Пользователь: {submission[0]}\n"
        f"📋 Задание #{submission[1]}\n"
        f"🔗 Канал: {submission[7]}\n"
        f"💫 Награда: {submission[6]} звёзд\n"
        f"🕐 Отправлено: {submission[2]}"
    )
    
    # Отправляем доказательство модератору
    await message.answer(text)
    if submission[3]:  # proof_file_id
        try:
            await bot.send_document(
                message.chat.id,
                submission[3],
                reply_markup=keyboard.as_markup()
            )
        except:
            await bot.send_photo(
                message.chat.id,
                submission[3],
                reply_markup=keyboard.as_markup()
            )
            
# Обработка решений модераторов
@dp.callback_query(lambda c: c.data.startswith('mod:'))
async def moderate_submission(callback: types.CallbackQuery):
    _, action, submission_id = callback.data.split(':')
    submission_id = int(submission_id)
    
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    cur.execute('''
        SELECT ct.*, t.stars, u.user_id
        FROM completed_tasks ct
        JOIN tasks t ON ct.task_id = t.task_id
        JOIN users u ON ct.user_id = u.user_id
        WHERE ct.rowid = ? AND ct.status = 'pending'
    ''', (submission_id,))
    
    submission = cur.fetchone()
    
    if not submission:
        await callback.answer("❌ Заявка не найдена или уже проверена")
        conn.close()
        return
    
    if action == 'approve':
        # Обновляем статус заявки
        cur.execute('''
            UPDATE completed_tasks 
            SET status = 'approved' 
            WHERE rowid = ?
        ''', (submission_id,))
        
        # Начисляем звёзды пользователю
        cur.execute('''
            UPDATE users 
            SET balance = balance + ? 
            WHERE user_id = ?
        ''', (submission[7], submission[0]))  # stars, user_id
        
        # Увеличиваем счетчик выполнений задания
        cur.execute('''
            UPDATE tasks 
            SET current_activations = current_activations + 1 
            WHERE task_id = ?
        ''', (submission[1],))
        
        # Отправляем уведомление пользователю
        await bot.send_message(
            submission[8],  # user_id
            f"✅ Ваша заявка #{submission_id} одобрена!\n"
            f"💫 На ваш баланс начислено {submission[7]} звёзд."
        )
        
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply("✅ Заявка одобрена")
        
    elif action == 'reject':
        # Обновляем статус заявки
        cur.execute('''
            UPDATE completed_tasks 
            SET status = 'rejected' 
            WHERE rowid = ?
        ''', (submission_id,))
        
        # Отправляем уведомление пользователю
        await bot.send_message(
            submission[8],  # user_id
            f"❌ Ваша заявка #{submission_id} отклонена.\n"
            "Возможные причины:\n"
            "- Некачественное доказательство\n"
            "- Несоответствие требованиям задания\n"
            "Попробуйте выполнить задание еще раз."
        )
        
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply("❌ Заявка отклонена")
    
    conn.commit()
    conn.close()
    await callback.answer()

# Система вывода звёзд
@dp.message(F.text == "💎 Вывести звёзды")
async def withdraw_stars(message: Message):
    user = await get_user(message.from_user.id)
    
    if user['balance'] < 15:  # Updated minimum withdrawal amount
        await message.answer(
            "❌ Недостаточно звёзд для вывода.\n"
            "Минимальная сумма: 15 звёзд"
        )
        return
    
    keyboard = InlineKeyboardBuilder()
    # Fixed withdrawal amounts
    amounts = [15, 25, 50, 100, 150, 250, 500]
    
    for amount in amounts:
        if user['balance'] >= amount:
            keyboard.add(InlineKeyboardButton(
                text=f"{amount} 💫",
                callback_data=f"withdraw:{amount}"
            ))
    
    keyboard.adjust(3)  # 3 buttons per row
    
    await message.answer(
        "💎 Выберите количество звёзд для вывода:",
        reply_markup=keyboard.as_markup()
    )

@dp.callback_query(lambda c: c.data.startswith('withdraw:'))
async def process_withdrawal(callback: types.CallbackQuery):
    amount = int(callback.data.split(':')[1])
    user = await get_user(callback.from_user.id)
    
    if user['balance'] < amount:
        await callback.answer("❌ Недостаточно звёзд на балансе", show_alert=True)
        return
    
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    # Создаем заявку на вывод
    cur.execute('''
        INSERT INTO withdrawals (
            user_id, amount, created_at
        ) VALUES (?, ?, ?)
    ''', (user['user_id'], amount, datetime.now()))
    
    withdrawal_id = cur.lastrowid
    
    # Замораживаем звёзды на балансе
    cur.execute('''
        UPDATE users 
        SET balance = balance - ? 
        WHERE user_id = ?
    ''', (amount, user['user_id']))
    
    conn.commit()
    conn.close()
    
    # Уведомляем администраторов
    admin_message = (
        f"💎 Новая заявка на вывод #{withdrawal_id}\n"
        f"👤 Пользователь: {callback.from_user.id}\n"
        f"💫 Сумма: {amount} звёзд\n"
        f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Для обработки используйте команды:\n"
        f"/approve_{withdrawal_id} - одобрить\n"
        f"/reject_{withdrawal_id} - отклонить"
    )
    
    for admin_id in OWNERS_IDS + DEVELOPERS_IDS:
        try:
            await bot.send_message(admin_id, admin_message)
        except:
            continue
    
    await callback.message.edit_text(
        f"✅ Заявка на вывод #{withdrawal_id} создана!\n"
        "Ожидайте решения администрации."
    )
    await callback.answer()
@dp.message(F.text == "🏆 Топ 10")
async def show_top_users(message: Message):
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    # Get top 10 users by balance
    cur.execute('''
        SELECT user_id, username, first_name, balance 
        FROM users 
        WHERE role != 'banned' AND balance > 0
        ORDER BY balance DESC 
        LIMIT 10
    ''')
    
    top_users = cur.fetchall()
    conn.close()
    
    if not top_users:
        await message.answer("😔 Пока никто не заработал звёзд")
        return
    
    text = "🏆 ТОП 10 пользователей:\n\n"
    for i, user in enumerate(top_users, 1):
        username = user[1] if user[1] else user[2]
        text += f"{i}. {username} - {user[3]} 💫\n"
    
    await message.answer(text)    
# Административные команды и функции безопасности
class SecurityMonitor:
    def __init__(self):
        self.suspicious_patterns = [
            r"(?i)(\b|_)union(\b|_)",
            r"(?i)(\b|_)select(\b|_)",
            r"(?i)(\b|_)from(\b|_)",
            r"(?i)(\b|_)where(\b|_)",
            r"(?i)(\b|_)drop(\b|_)",
            r"(?i)(\b|_)delete(\b|_)",
            r"(?i)(\b|_)insert(\b|_)",
            r"(?i)(\b|_)update(\b|_)",
            r"'|;|--",
        ]
        self.attempt_counter = {}

    async def check_injection(self, text: str, user_id: int) -> bool:
        for pattern in self.suspicious_patterns:
            if re.search(pattern, text):
                self.attempt_counter[user_id] = self.attempt_counter.get(user_id, 0) + 1
                
                if self.attempt_counter[user_id] >= 3:
                    await self.notify_owners(
                        user_id,
                        f"🚨 ВНИМАНИЕ! Обнаружена попытка SQL-инъекции!\n"
                        f"👤 Пользователь: {user_id}\n"
                        f"📝 Текст: {text}\n"
                        f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                return True
        return False

    async def notify_owners(self, user_id: int, message: str):
        for owner_id in OWNERS_IDS:
            try:
                await bot.send_message(owner_id, message)
            except:
                continue

security = SecurityMonitor()

# Административные команды
@dp.message(Command("admod"))
async def add_moderator(message: Message):
    user = await get_user(message.from_user.id)
    if user['role'] not in ['admin', 'owner', 'developer']:
        return

    try:
        new_mod_id = int(message.text.split()[1])
    except:
        await message.answer("❌ Неверный формат команды\nПример: /admod 123456789")
        return

    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE users 
        SET role = 'moderator' 
        WHERE user_id = ? AND role = 'user'
    ''', (new_mod_id,))
    
    if cur.rowcount > 0:
        conn.commit()
        await message.answer(f"✅ Пользователь {new_mod_id} назначен модератором")
        await bot.send_message(
            new_mod_id,
            "🎉 Поздравляем! Вы назначены модератором бота!"
        )
    else:
        await message.answer("❌ Пользователь не найден или уже является модератором")
    
    conn.close()

@dp.message(Command("delmod"))
async def remove_moderator(message: Message):
    user = await get_user(message.from_user.id)
    if user['role'] not in ['admin', 'owner', 'developer']:
        return

    try:
        mod_id = int(message.text.split()[1])
        reason = ' '.join(message.text.split()[2:]) or "Причина не указана"
    except:
        await message.answer(
            "❌ Неверный формат команды\n"
            "Пример: /delmod 123456789 причина"
        )
        return

    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE users 
        SET role = 'user' 
        WHERE user_id = ? AND role = 'moderator'
    ''', (mod_id,))
    
    if cur.rowcount > 0:
        conn.commit()
        await message.answer(f"✅ Модератор {mod_id} снят с должности")
        await bot.send_message(
            mod_id,
            f"❌ Вы были сняты с должности модератора.\n"
            f"📝 Причина: {reason}"
        )
    else:
        await message.answer("❌ Пользователь не найден или не является модератором")
    
    conn.close()

# Система варнов
@dp.message(Command("warn"))
async def warn_user(message: Message):
    user = await get_user(message.from_user.id)
    if user['role'] not in ['admin', 'owner', 'developer']:
        return

    try:
        target_id = int(message.text.split()[1])
        reason = ' '.join(message.text.split()[2:]) or "Причина не указана"
    except:
        await message.answer(
            "❌ Неверный формат команды\n"
            "Пример: /warn 123456789 причина"
        )
        return

    target_user = await get_user(target_id)
    if not target_user or target_user['role'] in ['admin', 'owner', 'developer']:
        await message.answer("❌ Пользователь не найден или имеет иммунитет")
        return

    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE users 
        SET warns_count = warns_count + 1 
        WHERE user_id = ?
    ''', (target_id,))
    
    cur.execute('SELECT warns_count FROM users WHERE user_id = ?', (target_id,))
    warns = cur.fetchone()[0]
    
    conn.commit()
    
    await bot.send_message(
        target_id,
        f"⚠️ Вы получили предупреждение!\n"
        f"📝 Причина: {reason}\n"
        f"❗️ Предупреждений: {warns}/3"
    )
    
    if warns >= 3:
        cur.execute('''
            UPDATE users 
            SET is_banned = 1, 
                balance = 0, 
                warns_count = 0 
            WHERE user_id = ?
        ''', (target_id,))
        conn.commit()
        
        await bot.send_message(
            target_id,
            "🚫 Вы были заблокированы за превышение лимита предупреждений!"
        )
        await message.answer(f"🚫 Пользователь {target_id} заблокирован (3/3 варна)")
    else:
        await message.answer(f"⚠️ Пользователь {target_id} получил предупреждение ({warns}/3)")
    
    conn.close()
    
# Команды владельцев и разработчиков
@dp.message(Command("addmin"))
async def add_admin(message: Message):
    user = await get_user(message.from_user.id)
    if user['role'] not in ['owner', 'developer']:
        return

    try:
        new_admin_id = int(message.text.split()[1])
    except:
        await message.answer("❌ Неверный формат команды\nПример: /addmin 123456789")
        return

    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE users 
        SET role = 'admin' 
        WHERE user_id = ? AND role IN ('user', 'moderator')
    ''', (new_admin_id,))
    
    if cur.rowcount > 0:
        conn.commit()
        await message.answer(f"✅ Пользователь {new_admin_id} назначен администратором")
        await bot.send_message(
            new_admin_id,
            "🎉 Поздравляем! Вы назначены администратором бота!"
        )
    else:
        await message.answer("❌ Пользователь не найден или уже является администратором")
    
    conn.close()

@dp.message(Command("delmin"))
async def remove_admin(message: Message):
    user = await get_user(message.from_user.id)
    if user['role'] not in ['owner', 'developer']:
        return

    try:
        admin_id = int(message.text.split()[1])
        reason = ' '.join(message.text.split()[2:]) or "Причина не указана"
    except:
        await message.answer(
            "❌ Неверный формат команды\n"
            "Пример: /delmin 123456789 причина"
        )
        return

    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE users 
        SET role = 'user' 
        WHERE user_id = ? AND role = 'admin'
    ''', (admin_id,))
    
    if cur.rowcount > 0:
        conn.commit()
        await message.answer(f"✅ Администратор {admin_id} снят с должности")
        await bot.send_message(
            admin_id,
            f"❌ Вы были сняты с должности администратора.\n"
            f"📝 Причина: {reason}"
        )
    else:
        await message.answer("❌ Пользователь не найден или не является администратором")
    
    conn.close()

@dp.message(Command("koll"))
async def send_announcement(message: Message):
    user = await get_user(message.from_user.id)
    if user['role'] not in ['owner', 'developer']:
        return

    text = message.text.replace('/koll', '').strip()
    if not text:
        await message.answer("❌ Введите текст объявления")
        return

    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    cur.execute('SELECT user_id FROM users WHERE is_banned = 0')
    users = cur.fetchall()
    conn.close()

    sent = 0
    failed = 0
    for user_id in users:
        try:
            await bot.send_message(
                user_id[0],
                f"📢 ОБЪЯВЛЕНИЕ\n\n{text}\n\n"
                f"От: {message.from_user.first_name}"
            )
            sent += 1
        except:
            failed += 1

    await message.answer(
        f"📊 Статистика рассылки:\n"
        f"✅ Успешно: {sent}\n"
        f"❌ Не доставлено: {failed}"
    )

# Система уничтожения бота
DESTROY_CODE_HASH = hashlib.sha256("your_secret_destroy_code".encode()).hexdigest()

@dp.message(Command("destroy"))
async def destroy_bot(message: Message):
    user = await get_user(message.from_user.id)
    if user['role'] not in ['developer']:
        return

    code = message.text.split()[1] if len(message.text.split()) > 1 else ""
    if hashlib.sha256(code.encode()).hexdigest() != DESTROY_CODE_HASH:
        # Уведомляем владельцев о попытке уничтожения
        for owner_id in OWNERS_IDS:
            try:
                await bot.send_message(
                    owner_id,
                    f"🚨 ВНИМАНИЕ! Попытка уничтожения бота!\n"
                    f"👤 Пользователь: {message.from_user.id}\n"
                    f"🕐 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
            except:
                continue
        return

    # Процесс уничтожения
    conn = sqlite3.connect(DATABASE_FILE)
    cur = conn.cursor()
    
    # Очищаем все таблицы
    tables = [
        'users', 'promocodes', 'used_promocodes', 
        'tasks', 'completed_tasks', 'withdrawals'
    ]
    
    for table in tables:
        cur.execute(f'DROP TABLE IF EXISTS {table}')
    
    conn.commit()
    conn.close()

    # Удаляем файл базы данных
    try:
        os.remove(DATABASE_FILE)
    except:
        pass

    await message.answer("💀 Бот уничтожен")
    sys.exit(0)

# Дополнительные функции безопасности
async def backup_database():
    """Создание резервной копии базы данных"""
    backup_time = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f'backup_{backup_time}.db'
    
    try:
        shutil.copy2(DATABASE_FILE, backup_file)
        
        # Уведомляем разработчиков
        for dev_id in DEVELOPERS_IDS:
            try:
                with open(backup_file, 'rb') as f:
                    await bot.send_document(
                        dev_id,
                        f,
                        caption=f"📦 Резервная копия базы данных\n"
                                f"🕐 {backup_time}"
                    )
            except:
                continue
                
        os.remove(backup_file)  # Удаляем локальную копию
    except Exception as e:
        for dev_id in DEVELOPERS_IDS:
            try:
                await bot.send_message(
                    dev_id,
                    f"❌ Ошибка создания резервной копии:\n{str(e)}"
                )
            except:
                continue

async def scheduled_tasks():
    """Выполнение периодических задач"""
    while True:
        try:
            # Создаем резервную копию каждые 24 часа
            await backup_database()
            
            # Очищаем старые записи
            conn = sqlite3.connect(DATABASE_FILE)
            cur = conn.cursor()
            
            # Удаляем старые отклоненные заявки
            cur.execute('''
                DELETE FROM completed_tasks 
                WHERE status = 'rejected' 
                AND completed_at < datetime('now', '-7 days')
            ''')
            
            # Удаляем использованные промокоды
            cur.execute('''
                DELETE FROM promocodes 
                WHERE current_activations >= max_activations
            ''')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Scheduled task error: {e}")
        
        await asyncio.sleep(86400)  # 24 часа
print('Бот робит')
# Запуск бота
async def main():
    # Инициализация базы данных
    init_db()
    
    # Обновляем роли пользователей
    await update_user_roles()
    
    # Запуск периодических задач
    asyncio.create_task(scheduled_tasks())
    
    # Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())                    
import asyncio
import logging
import random
import hashlib
import datetime
from typing import Union, Dict, List
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters.command import Command
from aiogram.types import (
    KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton,
    InlineKeyboardMarkup, Message, CallbackQuery
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import sqlite3
import os

# Конфигурация
TOKEN = "8163139120:AAHg1QkcPAmiHPFWM0NIUtOj6G0OMVUyEpc"
OWNERS = [6673580092, 1690656583]  # ID владельцев бота
DESTROY_CODE = hashlib.sha256("4a1049c94a03fa3ebd4f6694bea424669e0011051d4d00806b2fdc83117b8c82".encode()).hexdigest()
PRIVATE_CHANNEL_ID = -1002363437612  # ID канала для модерации
REVIEWS_CHANNEL_ID = -1002166881231  # ID канала для отзывов

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher()
    
    
class UserStates(StatesGroup):
    captcha = State()
    entering_promo = State()
    task_submission = State()
    withdrawal_amount = State()
    
    # Состояния для модераторов
    mod_add = State()
    mod_remove = State()
    
    # Состояния для промокодов
    promo_create = State()
    promo_reward = State()
    promo_limit = State()
    promo_delete = State()
    
    # Состояния для заданий
    task_create_text = State()
    task_create_reward = State()
    task_create_limit = State()
    task_delete = State()
    
    # Состояния для поиска и управления пользователями
    search_user = State()
    give_stars_id = State()
    give_stars_amount = State()
    fine_user_id = State()
    fine_amount = State()
    ban_user_id = State()
    ban_reason = State()
    unban_user_id = State()
    
    # Состояние отладки
    debug_mode = State()

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  first_name TEXT,
                  role TEXT DEFAULT 'user',
                  balance INTEGER DEFAULT 0,
                  referrals INTEGER DEFAULT 0,
                  reg_date TEXT,
                  is_banned INTEGER DEFAULT 0,
                  ban_reason TEXT)''')
    
    # Таблица промокодов
    c.execute('''CREATE TABLE IF NOT EXISTS promos
                 (code TEXT PRIMARY KEY,
                  reward INTEGER,
                  uses_left INTEGER,
                  total_uses INTEGER)''')
    
    # Таблица заданий
    c.execute('''CREATE TABLE IF NOT EXISTS tasks
                 (task_id INTEGER PRIMARY KEY,
                  description TEXT,
                  reward INTEGER,
                  uses_left INTEGER,
                  total_uses INTEGER)''')
    
    # Таблица выполненных заданий
    c.execute('''CREATE TABLE IF NOT EXISTS completed_tasks
                 (user_id INTEGER,
                  task_id INTEGER,
                  status TEXT,
                  proof_file_id TEXT,
                  moderator_id INTEGER,
                  UNIQUE(user_id, task_id))''')
    
    # Таблица статистики модераторов
    c.execute('''CREATE TABLE IF NOT EXISTS mod_stats
                 (moderator_id INTEGER,
                  approved_tasks INTEGER DEFAULT 0,
                  rejected_tasks INTEGER DEFAULT 0,
                  date TEXT)''')
    
    conn.commit()
    conn.close()

# Функции для работы с базой данных
def add_user(user_id: int, first_name: str, referrer_id: int = None):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    reg_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Проверяем, является ли пользователь владельцем
    role = "owner" if user_id in OWNERS else "user"
    
    c.execute("""
        INSERT OR IGNORE INTO users 
        (user_id, first_name, role, reg_date) 
        VALUES (?, ?, ?, ?)
    """, (user_id, first_name, role, reg_date))
    
    if referrer_id:
        c.execute("UPDATE users SET referrals = referrals + 1, balance = balance + 1 WHERE user_id = ?",
                 (referrer_id,))
    
    conn.commit()
    conn.close()

def get_user(user_id: int) -> dict:
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    
    conn.close()
    
    if user:
        return {
            "user_id": user[0],
            "first_name": user[1],
            "role": user[2],
            "balance": user[3],
            "referrals": user[4],
            "reg_date": user[5],
            "is_banned": user[6],
            "ban_reason": user[7]
        }
    return None

# Генерация капчи
def generate_captcha() -> tuple:
    fruits = ["🍎", "🍌", "🍇", "🍊", "🍐", "🍑", "🍓", "🍒"]
    correct = random.choice(fruits)
    options = random.sample(fruits, 4)
    if correct not in options:
        options[0] = correct
        random.shuffle(options)
    return correct, options

# Клавиатуры
def get_main_keyboard(user_role: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    
    # Общие кнопки для всех
    common_buttons = [
        "💫 Заработать звёзды",
        "👤 Профиль",
        "🎟 Промокод",
        "📝 Задание",
        "💎 Вывод звёзд",
        "🏆 Топ 10 пользователей"
    ]
    
    for button in common_buttons:
        builder.add(KeyboardButton(text=button))
    
    if user_role == "moderator":
        builder.add(KeyboardButton(text="👨‍⚖️ Панель модератора"))
    elif user_role == "owner":
        builder.add(KeyboardButton(text="👑 Панель владельца"))
    
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user = get_user(message.from_user.id)
    
    if not user:
        args = message.text.split()
        referrer_id = None
        if len(args) > 1 and args[1].startswith('ref_'):
            try:
                referrer_id = int(args[1].split('_')[1])
            except:
                pass

        # Отправляем капчу
        correct, options = generate_captcha()
        
        builder = ReplyKeyboardBuilder()
        for option in options:
            builder.add(KeyboardButton(text=option))
        builder.adjust(2)
        
        await state.update_data(correct_captcha=correct, referrer_id=referrer_id)
        await state.set_state(UserStates.captcha)
        
        await message.answer(
            f"👋 Привет! Для продолжения выберите {correct} из предложенных вариантов:",
            reply_markup=builder.as_markup(resize_keyboard=True)
        )
        # ... (оставьте существующий код для новых пользователей)
    else:
        if user["is_banned"]:
            await message.answer(f"⛔️ Вы заблокированы.\nПричина: {user['ban_reason']}")
            return
        
        # Создаем клавиатуру в зависимости от роли
        keyboard = None
        if user["role"] == "owner":
            keyboard = ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="💫 Заработать звёзды"), KeyboardButton(text="👤 Профиль")],
                    [KeyboardButton(text="🎟 Промокод"), KeyboardButton(text="📝 Задание")],
                    [KeyboardButton(text="💎 Вывод звёзд"), KeyboardButton(text="🏆 Топ 10 пользователей")],
                    [KeyboardButton(text="👑 Панель владельца")]  # Добавляем кнопку владельца
                ],
                resize_keyboard=True
            )
        else:
            keyboard = get_main_keyboard(user["role"])
        
        await message.answer(
            "👋 С возвращением!",
            reply_markup=keyboard
        )

# Обработчик панели владельца
@dp.message(lambda message: message.text == "👑 Панель владельца")
async def owner_panel(message: types.Message):
    user = get_user(message.from_user.id)
    if user["role"] != "owner":
        return
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить модератора"), KeyboardButton(text="➖ Уволить модератора")],
            [KeyboardButton(text="🎟 Создать промокод"), KeyboardButton(text="🗑 Удаление промокода")],
            [KeyboardButton(text="📝 Создание задания"), KeyboardButton(text="❌ Удаление задания")],
            [KeyboardButton(text="📊 Статистика бота"), KeyboardButton(text="👨‍⚖️ Модераторы")],
            [KeyboardButton(text="📈 Статистика модератора")],
            [KeyboardButton(text="🚫 Забанить"), KeyboardButton(text="✅ Разбанить")],
            [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="⭐️ Дать звёзды")],
            [KeyboardButton(text="💫 Оштрафовать"), KeyboardButton(text="📨 Заявки")],
            [KeyboardButton(text="🛠 Отладка"), KeyboardButton(text="◀️ Назад")]
        ],
        resize_keyboard=True
    )
    
    await message.answer("👑 Панель владельца:", reply_markup=keyboard)

# Добавим кнопку "Назад" для возврата в основное меню
@dp.message(lambda message: message.text == "◀️ Назад")
async def back_to_main(message: types.Message):
    user = get_user(message.from_user.id)
    await message.answer(
        "🔙 Возвращаемся в главное меню",
        reply_markup=get_main_keyboard(user["role"])
    )

# Обновленная функция get_main_keyboard
def get_main_keyboard(user_role: str) -> ReplyKeyboardMarkup:
    if user_role == "owner":
        return ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="💫 Заработать звёзды"), KeyboardButton(text="👤 Профиль")],
                [KeyboardButton(text="🎟 Промокод"), KeyboardButton(text="📝 Задание")],
                [KeyboardButton(text="💎 Вывод звёзд"), KeyboardButton(text="🏆 Топ 10 пользователей")],
                [KeyboardButton(text="👑 Панель владельца")]
            ],
            resize_keyboard=True
        )
    else:
        # Обычное меню для других ролей
        buttons = [
            [KeyboardButton(text="💫 Заработать звёзды"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="🎟 Промокод"), KeyboardButton(text="📝 Задание")],
            [KeyboardButton(text="💎 Вывод звёзд"), KeyboardButton(text="🏆 Топ 10 пользователей")]
        ]
        
        if user_role == "moderator":
            buttons.append([KeyboardButton(text="👨‍⚖️ Панель модератора")])
            
        return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

@dp.message(UserStates.captcha)
async def process_captcha(message: types.Message, state: FSMContext):
    data = await state.get_data()
    correct_captcha = data.get("correct_captcha")
    referrer_id = data.get("referrer_id")
    
    if message.text == correct_captcha:
        # Добавляем пользователя и учитываем реферала
        if referrer_id:
            add_user(message.from_user.id, message.from_user.first_name, referrer_id)
        else:
            add_user(message.from_user.id, message.from_user.first_name)
        
        await state.clear()
        await message.answer(
            "✅ Капча пройдена успешно!",
            reply_markup=get_main_keyboard("user")
        )
    else:
        correct, options = generate_captcha()
        builder = ReplyKeyboardBuilder()
        for option in options:
            builder.add(KeyboardButton(text=option))
        builder.adjust(2)
        
        await state.update_data(correct_captcha=correct)
        await message.answer(
            f"❌ Неверно! Попробуйте снова.\nВыберите {correct}:",
            reply_markup=builder.as_markup(resize_keyboard=True)
        )
        
        
@dp.message(F.text == "💫 Заработать звёзды")
async def earn_stars(message: types.Message):
    user = get_user(message.from_user.id)
    if user["is_banned"]:
        return
    
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref_{message.from_user.id}"
    
    await message.answer(
        f"🌟 Заработать звёзды можно несколькими способами:\n\n"
        f"1️⃣ Приглашайте друзей по вашей реферальной ссылке:\n{ref_link}\n"
        f"За каждого приглашенного вы получите 1 звезду!\n\n"
        f"2️⃣ Выполняйте задания в разделе 'Задания'\n\n"
        f"3️⃣ Активируйте промокоды в разделе 'Промокод'"
    )

@dp.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message):
    user = get_user(message.from_user.id)
    if user["is_banned"]:
        return
    
    await message.answer(
        f"👤 Профиль пользователя\n\n"
        f"🆔 ID: {user['user_id']}\n"
        f"👤 Имя: {user['first_name']}\n"
        f"💫 Баланс: {user['balance']} звёзд\n"
        f"👥 Рефералов: {user['referrals']}\n"
        f"📅 Дата регистрации: {user['reg_date']}\n"
        f"🎭 Роль: {user['role']}"
    )

@dp.message(F.text == "🎟 Промокод")
async def promo_code(message: types.Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if user["is_banned"]:
        return
    
    await state.set_state(UserStates.entering_promo)
    await message.answer("📝 Введите промокод:")

@dp.message(UserStates.entering_promo)
async def process_promo(message: types.Message, state: FSMContext):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    promo = message.text.upper()
    user_id = message.from_user.id
    
    # Проверяем существование промокода
    c.execute("SELECT reward, uses_left FROM promos WHERE code = ?", (promo,))
    promo_data = c.execute("SELECT reward, uses_left FROM promos WHERE code = ?", (promo,)).fetchone()
    
    if not promo_data:
        await message.answer("❌ Такого промокода не существует!")
        await state.clear()
        return
    
    # Проверяем, использовал ли пользователь этот промокод
    c.execute("CREATE TABLE IF NOT EXISTS used_promos (user_id INTEGER, promo TEXT, UNIQUE(user_id, promo))")
    try:
        c.execute("INSERT INTO used_promos (user_id, promo) VALUES (?, ?)", (user_id, promo))
        
        reward, uses_left = promo_data
        if uses_left > 0:
            c.execute("UPDATE promos SET uses_left = uses_left - 1 WHERE code = ?", (promo,))
            c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, user_id))
            
            conn.commit()
            await message.answer(f"✅ Промокод активирован!\nНа ваш баланс начислено {reward} звёзд!")
        else:
            await message.answer("❌ У этого промокода закончились активации!")
    except sqlite3.IntegrityError:
        await message.answer("❌ Вы уже использовали этот промокод!")
    
    conn.close()
    await state.clear()

# Система заданий
@dp.message(F.text == "📝 Задание")
async def show_tasks(message: types.Message):
    user = get_user(message.from_user.id)
    if user["is_banned"]:
        return
    
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    # Получаем активные задания
    c.execute("""
        SELECT t.task_id, t.description, t.reward, t.uses_left 
        FROM tasks t 
        WHERE t.uses_left > 0 
        AND NOT EXISTS (
            SELECT 1 FROM completed_tasks ct 
            WHERE ct.task_id = t.task_id 
            AND ct.user_id = ?
        )
    """, (message.from_user.id,))
    
    tasks = c.fetchall()
    conn.close()
    
    if not tasks:
        await message.answer("😔 Активных заданий пока нет!")
        return
    
    for task in tasks:
        task_id, description, reward, uses_left = task
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выполнить", callback_data=f"task_{task_id}")]
        ])
        
        await message.answer(
            f"📋 Задание #{task_id}\n\n"
            f"📝 Описание: {description}\n"
            f"💫 Награда: {reward} звёзд\n"
            f"⚡️ Осталось выполнений: {uses_left}",
            reply_markup=keyboard
        )

@dp.callback_query(lambda c: c.data.startswith('task_'))
async def task_submission(callback_query: CallbackQuery, state: FSMContext):
    task_id = int(callback_query.data.split('_')[1])
    await state.update_data(current_task_id=task_id)
    await state.set_state(UserStates.task_submission)
    
    await callback_query.message.answer(
        "📸 Пожалуйста, отправьте фото или видео подтверждение выполнения задания:"
    )
    await callback_query.answer()

@dp.message(UserStates.task_submission, F.photo | F.video)
async def process_task_submission(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data['current_task_id']
    
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    # Получаем случайного модератора
    c.execute("SELECT user_id FROM users WHERE role = 'moderator'")
    moderators = c.fetchall()
    
    if not moderators:
        await message.answer("❌ Ошибка: нет доступных модераторов!")
        conn.close()
        await state.clear()
        return
    
    moderator_id = random.choice(moderators)[0]
    
    # Создаём заявку на проверку
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    submission_id = random.randint(100000, 999999)
    
    c.execute("""
        INSERT INTO completed_tasks (user_id, task_id, status, proof_file_id, moderator_id)
        VALUES (?, ?, 'pending', ?, ?)
    """, (message.from_user.id, task_id, file_id, moderator_id))
    
    conn.commit()
    conn.close()
    
    # Отправляем файл в канал модерации
    await bot.send_message(
        PRIVATE_CHANNEL_ID,
        f"📝 Новая заявка #{submission_id}\n"
        f"👤 Пользователь: {message.from_user.id}\n"
        f"📋 Задание: #{task_id}"
    )
    
    if message.photo:
        await bot.send_photo(PRIVATE_CHANNEL_ID, file_id)
    else:
        await bot.send_video(PRIVATE_CHANNEL_ID, file_id)
    
    await message.answer(
        "✅ Ваша заявка отправлена на проверку!\n"
        "Ожидайте решения модератора."
    )
    await state.clear()
    
# Панель модератора
@dp.message(F.text == "👨‍⚖️ Панель модератора")
async def mod_panel(message: types.Message):
    user = get_user(message.from_user.id)
    if user["role"] != "moderator" and user["role"] != "owner":
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Активные заявки", callback_data="mod_tasks")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="mod_stats")]
    ])
    
    await message.answer("👨‍⚖️ Панель модератора:", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "mod_tasks")
async def show_mod_tasks(callback_query: CallbackQuery):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    c.execute("""
        SELECT ct.user_id, ct.task_id, ct.proof_file_id, t.reward
        FROM completed_tasks ct
        JOIN tasks t ON ct.task_id = t.task_id
        WHERE ct.moderator_id = ? AND ct.status = 'pending'
    """, (callback_query.from_user.id,))
    
    tasks = c.fetchall()
    conn.close()
    
    if not tasks:
        await callback_query.message.answer("📭 Активных заявок нет!")
        await callback_query.answer()
        return
    
    for user_id, task_id, file_id, reward in tasks:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{user_id}_{task_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{user_id}_{task_id}")
            ]
        ])
        
        await callback_query.message.answer_photo(
            file_id,
            caption=f"📝 Заявка на проверку\n"
                   f"👤 Пользователь: {user_id}\n"
                   f"📋 Задание #{task_id}\n"
                   f"💫 Награда: {reward} звёзд",
            reply_markup=keyboard
        )
    
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith(('approve_', 'reject_')))
async def process_mod_decision(callback_query: CallbackQuery):
    action, user_id, task_id = callback_query.data.split('_')
    user_id = int(user_id)
    task_id = int(task_id)
    
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    if action == 'approve':
        # Получаем награду за задание
        c.execute("SELECT reward FROM tasks WHERE task_id = ?", (task_id,))
        reward = c.fetchone()[0]
        
        # Начисляем награду пользователю
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, user_id))
        
        # Обновляем статистику модератора
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        c.execute("""
            INSERT OR REPLACE INTO mod_stats (moderator_id, approved_tasks, rejected_tasks, date)
            VALUES (?, 
                    COALESCE((SELECT approved_tasks + 1 FROM mod_stats 
                     WHERE moderator_id = ? AND date = ?), 1),
                    COALESCE((SELECT rejected_tasks FROM mod_stats 
                     WHERE moderator_id = ? AND date = ?), 0),
                    ?)
        """, (callback_query.from_user.id, callback_query.from_user.id, today,
              callback_query.from_user.id, today, today))
        
        await bot.send_message(
            user_id,
            f"✅ Ваше задание #{task_id} одобрено!\n"
            f"💫 Получено {reward} звёзд!"
        )
        
    else:  # reject
        c.execute("""
            INSERT OR REPLACE INTO mod_stats (moderator_id, approved_tasks, rejected_tasks, date)
            VALUES (?, 
                    COALESCE((SELECT approved_tasks FROM mod_stats 
                     WHERE moderator_id = ? AND date = ?), 0),
                    COALESCE((SELECT rejected_tasks + 1 FROM mod_stats 
                     WHERE moderator_id = ? AND date = ?), 1),
                    ?)
        """, (callback_query.from_user.id, callback_query.from_user.id, today,
              callback_query.from_user.id, today, today))
        
        await bot.send_message(
            user_id,
            f"❌ Ваше задание #{task_id} отклонено!\n"
            f"🔄 Вы можете попробовать выполнить его снова."
        )
    
    # Удаляем заявку
    c.execute("DELETE FROM completed_tasks WHERE user_id = ? AND task_id = ?", (user_id, task_id))
    conn.commit()
    conn.close()
    
    await callback_query.message.delete()
    await callback_query.answer("✅ Решение принято!")

@dp.callback_query(lambda c: c.data == "mod_stats")
async def show_mod_stats(callback_query: CallbackQuery):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    # Статистика за сегодня
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    c.execute("""
        SELECT COALESCE(SUM(approved_tasks), 0), COALESCE(SUM(rejected_tasks), 0)
        FROM mod_stats 
        WHERE moderator_id = ? AND date = ?
    """, (callback_query.from_user.id, today))
    today_stats = c.fetchone()
    
    # Общая статистика
    c.execute("""
        SELECT COALESCE(SUM(approved_tasks), 0), COALESCE(SUM(rejected_tasks), 0)
        FROM mod_stats 
        WHERE moderator_id = ?
    """, (callback_query.from_user.id,))
    total_stats = c.fetchone()
    
    conn.close()
    
    await callback_query.message.answer(
        f"📊 Ваша статистика:\n\n"
        f"Сегодня:\n"
        f"✅ Одобрено: {today_stats[0]}\n"
        f"❌ Отклонено: {today_stats[1]}\n\n"
        f"За всё время:\n"
        f"✅ Одобрено: {total_stats[0]}\n"
        f"❌ Отклонено: {total_stats[1]}"
    )
    await callback_query.answer()

# Панель владельца
@dp.message(F.text == "👑 Панель владельца")
async def owner_panel(message: types.Message):
    if message.from_user.id not in OWNERS:
        return
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить модератора"), KeyboardButton(text="➖ Уволить модератора")],
            [KeyboardButton(text="🎟 Создать промокод"), KeyboardButton(text="🗑 Удаление промокода")],
            [KeyboardButton(text="📝 Создание задания"), KeyboardButton(text="❌ Удаление задания")],
            [KeyboardButton(text="📊 Статистика бота"), KeyboardButton(text="👨‍⚖️ Модераторы")],
            [KeyboardButton(text="📈 Статистика модератора")],
            [KeyboardButton(text="🚫 Забанить"), KeyboardButton(text="✅ Разбанить")],
            [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="⭐️ Дать звёзды")],
            [KeyboardButton(text="💫 Оштрафовать"), KeyboardButton(text="📨 Заявки")],
            [KeyboardButton(text="🛠 Отладка")]
        ],
        resize_keyboard=True
    )
    
    await message.answer("👑 Панель владельца:", reply_markup=keyboard)
    
    
# Функции владельца (продолжение)

# Добавление/удаление модератора
@dp.message(F.text == "➕ Добавить модератора")
async def add_mod_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in OWNERS:
        return
    
    await state.set_state(UserStates.mod_add)
    await message.answer("👤 Введите telegram_id нового модератора:")

@dp.message(UserStates.mod_add)
async def add_mod_process(message: types.Message, state: FSMContext):
    try:
        mod_id = int(message.text)
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (mod_id,))
        if c.fetchone():
            c.execute("UPDATE users SET role = 'moderator' WHERE user_id = ?", (mod_id,))
            conn.commit()
            await message.answer(f"✅ Пользователь {mod_id} назначен модератором!")
        else:
            await message.answer("❌ Пользователь не найден в базе данных!")
        
        conn.close()
    except ValueError:
        await message.answer("❌ Некорректный ID!")
    
    await state.clear()
@dp.message(F.text == "➖ Уволить модератора")
async def remove_mod_start(message: types.Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if user["role"] != "owner":
        return
    await state.set_state(UserStates.mod_remove)
    await message.answer("👤 Введите telegram_id модератора для увольнения:")

@dp.message(UserStates.mod_remove)
async def remove_mod_process(message: types.Message, state: FSMContext):
    try:
        mod_id = int(message.text)
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        
        c.execute("UPDATE users SET role = 'user' WHERE user_id = ? AND role = 'moderator'", (mod_id,))
        
        if c.rowcount > 0:
            await message.answer(f"✅ Модератор {mod_id} успешно уволен!")
            await bot.send_message(mod_id, "⚠️ Вы были сняты с должности модератора.")
        else:
            await message.answer("❌ Модератор с таким ID не найден!")
        
        conn.commit()
        conn.close()
    except ValueError:
        await message.answer("❌ Введите корректный ID!")
    finally:
        await state.clear()
        
# Статистика бота
@dp.message(F.text == "📊 Статистика бота")
async def bot_stats(message: types.Message):
    if message.from_user.id not in OWNERS:
        return
    
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    # Общая статистика
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM users WHERE role = 'moderator'")
    total_mods = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    banned_users = c.fetchone()[0]
    
    c.execute("SELECT SUM(balance) FROM users")
    total_stars = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM tasks WHERE uses_left > 0")
    active_tasks = c.fetchone()[0]
    
    await message.answer(
        f"📊 Статистика бота:\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"👨‍⚖️ Модераторов: {total_mods}\n"
        f"🚫 Забаненных: {banned_users}\n"
        f"⭐️ Всего звёзд: {total_stars}\n"
        f"📝 Активных заданий: {active_tasks}"
    )

# Отладка
@dp.message(F.text == "🛠 Отладка")
async def debug_mode(message: types.Message, state: FSMContext):
    if message.from_user.id not in OWNERS:
        return
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="◀️ Назад")]],
        resize_keyboard=True
    )
    
    await state.set_state(UserStates.debug_mode)
    await message.answer(
        "🛠 Режим отладки активирован\n"
        "Введите команду для выполнения:",
        reply_markup=keyboard
    )

@dp.message(UserStates.debug_mode)
async def process_debug(message: types.Message, state: FSMContext):
    if message.text == "◀️ Назад":
        await state.clear()
        await message.answer(
            "✅ Режим отладки деактивирован",
            reply_markup=get_main_keyboard("owner")
        )
        return
    
    try:
        # Выполнение отладочных команд
        result = eval(message.text)  # Только для демонстрации! В реальном боте нужно ограничить команды
        await message.answer(f"Результат: {result}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

# Команда уничтожения
@dp.message(Command("destroy"))
async def destroy_bot(message: types.Message):
    if message.from_user.id not in OWNERS:
        return
    
    try:
        code = message.text.split()[1]
        if hashlib.sha256(code.encode()).hexdigest() == DESTROY_CODE:
            # Удаление базы данных
            if os.path.exists('bot.db'):
                os.remove('bot.db')
            
            # Удаление текущего файла
            current_file = os.path.abspath(__file__)
            if os.path.exists(current_file):
                os.remove(current_file)
            
            await message.answer("💥 Бот уничтожен!")
            await bot.close()
    except:
        pass

# Дополнительные функции

# Автоматическое оповещение владельцев
async def notify_owners(user_id: int, stars: int):
    if stars > 19:
        user = get_user(user_id)
        for owner_id in OWNERS:
            await bot.send_message(
                owner_id,
                f"⚠️ Внимание!\n"
                f"Пользователь {user['first_name']} (ID: {user_id})\n"
                f"получил {stars} звёзд!"
            )

# Топ 10 пользователей
@dp.message(F.text == "🏆 Топ 10 пользователей")
async def top_users(message: types.Message):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    c.execute("""
        SELECT user_id, first_name, balance 
        FROM users 
        WHERE is_banned = 0 
        ORDER BY balance DESC 
        LIMIT 10
    """)
    
    top = c.fetchall()
    conn.close()
    
    text = "🏆 Топ 10 пользователей:\n\n"
    for i, (user_id, name, balance) in enumerate(top, 1):
        text += f"{i}. {name} - {balance} ⭐️\n"
    
    await message.answer(text)
@dp.message(F.text == "💎 Вывод звёзд")
async def withdraw_stars(message: types.Message):
    user = get_user(message.from_user.id)
    if user["is_banned"]:
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="15 звёзд", callback_data="withdraw_15")],
        [InlineKeyboardButton(text="25 звёзд", callback_data="withdraw_25")],
        [InlineKeyboardButton(text="50 звёзд", callback_data="withdraw_50")],
        [InlineKeyboardButton(text="150 звёзд", callback_data="withdraw_150")],
        [InlineKeyboardButton(text="350 звёзд", callback_data="withdraw_350")],
        [InlineKeyboardButton(text="500 звёзд", callback_data="withdraw_500")]
    ])
    
    await message.answer(
        f"💫 Ваш текущий баланс: {user['balance']} звёзд\n"
        "Выберите количество звёзд для вывода:",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data.startswith('withdraw_'))
async def process_withdrawal(callback_query: CallbackQuery):
    amount = int(callback_query.data.split('_')[1])
    user = get_user(callback_query.from_user.id)
    
    if user['balance'] < amount:
        await callback_query.answer("❌ Недостаточно звёзд на балансе!", show_alert=True)
        return
    
    # Создаем заявку на вывод
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    withdrawal_id = random.randint(100000, 999999)
    c.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals 
        (id INTEGER PRIMARY KEY,
         user_id INTEGER,
         amount INTEGER,
         status TEXT,
         timestamp TEXT)
    """)
    
    c.execute("""
        INSERT INTO withdrawals (id, user_id, amount, status, timestamp)
        VALUES (?, ?, ?, 'pending', datetime('now'))
    """, (withdrawal_id, user['user_id'], amount))
    
    conn.commit()
    conn.close()
    
    # Отправляем заявку владельцам
    withdraw_message = (
        f"💎 Новая заявка на вывод #{withdrawal_id}\n"
        f"👤 Пользователь: {user['first_name']} (ID: {user['user_id']})\n"
        f"💫 Сумма: {amount} звёзд\n"
        f"📅 Дата регистрации: {user['reg_date']}\n"
        f"👥 Рефералов: {user['referrals']}"
    )
    
    for owner_id in OWNERS:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", 
                                   callback_data=f"approve_withdraw_{withdrawal_id}"),
                InlineKeyboardButton(text="❌ Отклонить", 
                                   callback_data=f"reject_withdraw_{withdrawal_id}")
            ]
        ])
        await bot.send_message(owner_id, withdraw_message, reply_markup=keyboard)
    
    await callback_query.message.answer(
        f"✅ Заявка на вывод {amount} звёзд создана!\n"
        "Ожидайте решения администрации."
    )
    await callback_query.answer()

    
# Обработчики кнопок панели владельца

# Создание промокода
@dp.message(F.text == "🎟 Создать промокод")
async def create_promo_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in OWNERS:
        return
    await state.set_state(UserStates.promo_create)
    await message.answer("Введите промокод:")

@dp.message(UserStates.promo_create)
async def process_promo_code(message: types.Message, state: FSMContext):
    await state.update_data(promo_code=message.text.upper())
    await state.set_state(UserStates.promo_reward)
    await message.answer("Введите награду (количество звёзд):")

@dp.message(UserStates.promo_reward)
async def process_promo_reward(message: types.Message, state: FSMContext):
    try:
        reward = int(message.text)
        await state.update_data(reward=reward)
        await state.set_state(UserStates.promo_limit)
        await message.answer("Введите лимит активаций:")
    except ValueError:
        await message.answer("❌ Введите корректное число!")

@dp.message(UserStates.promo_limit)
async def process_promo_limit(message: types.Message, state: FSMContext):
    try:
        limit = int(message.text)
        data = await state.get_data()
        
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        
        c.execute("""
            INSERT INTO promos (code, reward, uses_left, total_uses)
            VALUES (?, ?, ?, ?)
        """, (data['promo_code'], data['reward'], limit, limit))
        
        conn.commit()
        conn.close()
        
        await message.answer(
            f"✅ Промокод создан!\n"
            f"Код: {data['promo_code']}\n"
            f"Награда: {data['reward']} звёзд\n"
            f"Лимит активаций: {limit}"
        )
    except ValueError:
        await message.answer("❌ Введите корректное число!")
    finally:
        await state.clear()

# Удаление промокода
@dp.message(F.text == "🗑 Удаление промокода")
async def delete_promo_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in OWNERS:
        return
    await message.answer("Введите промокод для удаления:")
    await state.set_state("delete_promo")

@dp.message(lambda message: message.state == "delete_promo")
async def delete_promo_process(message: types.Message, state: FSMContext):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    c.execute("DELETE FROM promos WHERE code = ?", (message.text.upper(),))
    
    if c.rowcount > 0:
        await message.answer("✅ Промокод успешно удален!")
    else:
        await message.answer("❌ Промокод не найден!")
    
    conn.commit()
    conn.close()
    await state.clear()

# Создание задания
@dp.message(F.text == "📝 Создание задания")
async def create_task_start(message: types.Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if user["role"] != "owner":
        return
    await state.set_state(UserStates.task_create_text)
    await message.answer("📝 Введите текст задания:")


@dp.message(UserStates.task_create_text)
async def process_task_text(message: types.Message, state: FSMContext):
    await state.update_data(task_text=message.text)
    await state.set_state(UserStates.task_create_reward)
    await message.answer("💫 Введите награду за выполнение (количество звёзд):")


@dp.message(UserStates.task_create_reward)
async def process_task_reward(message: types.Message, state: FSMContext):
    try:
        reward = int(message.text)
        await state.update_data(reward=reward)
        await state.set_state(UserStates.task_create_limit)
        await message.answer("🔢 Введите лимит выполнений:")
    except ValueError:
        await message.answer("❌ Введите корректное число!")


@dp.message(UserStates.task_create_limit)
async def process_task_limit(message: types.Message, state: FSMContext):
    try:
        limit = int(message.text)
        data = await state.get_data()
        
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        
        c.execute("""
            INSERT INTO tasks (description, reward, uses_left, total_uses)
            VALUES (?, ?, ?, ?)
        """, (data['task_text'], data['reward'], limit, limit))
        
        task_id = c.lastrowid
        
        conn.commit()
        conn.close()
        
        await message.answer(
            f"✅ Задание создано!\n"
            f"ID: #{task_id}\n"
            f"Награда: {data['reward']} звёзд\n"
            f"Лимит выполнений: {limit}"
        )
    except ValueError:
        await message.answer("❌ Введите корректное число!")
    finally:
        await state.clear()
@dp.message(F.text == "❌ Удаление задания")
async def delete_task_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in OWNERS:
        return
    await state.set_state("delete_task")
    await message.answer("Введите ID задания для удаления:")

@dp.message(lambda message: message.state == "delete_task")
async def delete_task_process(message: types.Message, state: FSMContext):
    try:
        task_id = int(message.text)
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        
        c.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        
        if c.rowcount > 0:
            await message.answer("✅ Задание успешно удалено!")
        else:
            await message.answer("❌ Задание не найдено!")
        
        conn.commit()
        conn.close()
    except ValueError:
        await message.answer("❌ Введите корректное число!")
    finally:
        await state.clear()

# Список модераторов
@dp.message(F.text == "👨‍⚖️ Модераторы")
async def list_moderators(message: types.Message):
    if message.from_user.id not in OWNERS:
        return
    
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    c.execute("SELECT user_id, first_name FROM users WHERE role = 'moderator'")
    moderators = c.fetchall()
    
    if moderators:
        text = "📋 Список модераторов:\n\n"
        for mod_id, name in moderators:
            text += f"👤 {name} (ID: {mod_id})\n"
    else:
        text = "❌ Модераторов нет!"
    
    conn.close()
    await message.answer(text)

@dp.message(F.text == "🔍 Поиск")
async def search_user_start(message: types.Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if user["role"] != "owner":
        return
    await state.set_state(UserStates.search_user)
    await message.answer("🔍 Введите ID или имя пользователя для поиска:")


@dp.message(UserStates.search_user)
async def search_user_process(message: types.Message, state: FSMContext):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    try:
        user_id = int(message.text)
        c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    except ValueError:
        c.execute("SELECT * FROM users WHERE first_name LIKE ?", (f"%{message.text}%",))
    
    users = c.fetchall()
    conn.close()
    
    if users:
        for user in users:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="⭐️ Дать звёзды", callback_data=f"give_stars_{user[0]}"),
                    InlineKeyboardButton(text="💫 Штраф", callback_data=f"fine_{user[0]}")
                ],
                [
                    InlineKeyboardButton(text="🚫 Забанить", callback_data=f"ban_{user[0]}"),
                    InlineKeyboardButton(text="✅ Разбанить", callback_data=f"unban_{user[0]}")
                ]
            ])
            
            await message.answer(
                f"👤 Пользователь найден:\n"
                f"ID: {user[0]}\n"
                f"Имя: {user[1]}\n"
                f"Роль: {user[2]}\n"
                f"Баланс: {user[3]} звёзд\n"
                f"Рефералов: {user[4]}\n"
                f"Дата регистрации: {user[5]}\n"
                f"Забанен: {'Да' if user[6] else 'Нет'}\n"
                f"Причина бана: {user[7] if user[7] else 'Нет'}",
                reply_markup=keyboard
            )
    else:
        await message.answer("❌ Пользователь не найден!")
    
    await state.clear()
    
    
@dp.message(F.text == "⭐️ Дать звёзды")
async def give_stars_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in OWNERS:
        return
    await state.set_state("give_stars_id")
    await message.answer("Введите ID пользователя:")

@dp.message(lambda message: message.state == "give_stars_id")
async def give_stars_id(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text)
        await state.update_data(target_user_id=user_id)
        await state.set_state("give_stars_amount")
        await message.answer("Введите количество звёзд:")
    except ValueError:
        await message.answer("❌ Введите корректный ID!")
        await state.clear()

@dp.message(lambda message: message.state == "give_stars_amount")
async def give_stars_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        data = await state.get_data()
        user_id = data['target_user_id']
        
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        
        c.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        
        if c.rowcount > 0:
            await message.answer(f"✅ Пользователю {user_id} начислено {amount} звёзд!")
            await bot.send_message(
                user_id,
                f"💫 Вам начислено {amount} звёзд администратором!"
            )
            # Оповещение владельцев
            await notify_owners(user_id, amount)
        else:
            await message.answer("❌ Пользователь не найден!")
        
        conn.commit()
        conn.close()
    except ValueError:
        await message.answer("❌ Введите корректное число!")
    finally:
        await state.clear()

# Штраф
@dp.message(F.text == "💫 Оштрафовать")
async def fine_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in OWNERS:
        return
    await state.set_state("fine_user_id")
    await message.answer("Введите ID пользователя:")

@dp.message(lambda message: message.state == "fine_user_id")
async def fine_user_id(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text)
        await state.update_data(target_user_id=user_id)
        await state.set_state("fine_amount")
        await message.answer("Введите количество звёзд или 'весь' для обнуления баланса:")
    except ValueError:
        await message.answer("❌ Введите корректный ID!")
        await state.clear()

@dp.message(lambda message: message.state == "fine_amount")
async def fine_amount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data['target_user_id']
    
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    if message.text.lower() == "весь":
        c.execute("UPDATE users SET balance = 0 WHERE user_id = ?", (user_id,))
        fine_text = "весь баланс"
    else:
        try:
            amount = int(message.text)
            c.execute("""
                UPDATE users 
                SET balance = CASE 
                    WHEN balance >= ? THEN balance - ?
                    ELSE 0 
                END 
                WHERE user_id = ?
            """, (amount, amount, user_id))
            fine_text = f"{amount} звёзд"
        except ValueError:
            await message.answer("❌ Введите корректное число или 'весь'!")
            await state.clear()
            return
    
    if c.rowcount > 0:
        await message.answer(f"✅ Пользователь {user_id} оштрафован на {fine_text}!")
        await bot.send_message(
            user_id,
            f"⚠️ Вы были оштрафованы на {fine_text}!"
        )
    else:
        await message.answer("❌ Пользователь не найден!")
    
    conn.commit()
    conn.close()
    await state.clear()

# Бан пользователя
@dp.message(F.text == "🚫 Забанить")
async def ban_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in OWNERS:
        return
    await state.set_state("ban_user_id")
    await message.answer("Введите ID пользователя для бана:")

@dp.message(lambda message: message.state == "ban_user_id")
async def ban_user_id(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text)
        await state.update_data(target_user_id=user_id)
        await state.set_state("ban_reason")
        await message.answer("Введите причину бана:")
    except ValueError:
        await message.answer("❌ Введите корректный ID!")
        await state.clear()

@dp.message(lambda message: message.state == "ban_reason")
async def ban_reason(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data['target_user_id']
    reason = message.text
    
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    c.execute("""
        UPDATE users 
        SET is_banned = 1, ban_reason = ?, balance = 0 
        WHERE user_id = ?
    """, (reason, user_id))
    
    if c.rowcount > 0:
        await message.answer(f"✅ Пользователь {user_id} забанен!\nПричина: {reason}")
        await bot.send_message(
            user_id,
            f"⛔️ Вы были забанены!\nПричина: {reason}"
        )
    else:
        await message.answer("❌ Пользователь не найден!")
    
    conn.commit()
    conn.close()
    await state.clear()

# Разбан пользователя
@dp.message(F.text == "✅ Разбанить")
async def unban_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in OWNERS:
        return
    await state.set_state("unban_user_id")
    await message.answer("Введите ID пользователя для разбана:")

@dp.message(lambda message: message.state == "unban_user_id")
async def unban_user_id(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text)
        
        conn = sqlite3.connect('bot.db')
        c = conn.cursor()
        
        c.execute("""
            UPDATE users 
            SET is_banned = 0, ban_reason = NULL 
            WHERE user_id = ?
        """, (user_id,))
        
        if c.rowcount > 0:
            await message.answer(f"✅ Пользователь {user_id} разбанен!")
            await bot.send_message(
                user_id,
                "✅ Вы были разбанены! Теперь вы снова можете использовать бота."
            )
        else:
            await message.answer("❌ Пользователь не найден!")
        
        conn.commit()
        conn.close()
    except ValueError:
        await message.answer("❌ Введите корректный ID!")
    finally:
        await state.clear()

# Заявки на вывод
@dp.message(F.text == "📨 Заявки")
async def withdrawal_requests(message: types.Message):
    if message.from_user.id not in OWNERS:
        return
    
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    c.execute("""
        SELECT w.id, w.user_id, w.amount, u.first_name, w.timestamp
        FROM withdrawals w
        JOIN users u ON w.user_id = u.user_id
        WHERE w.status = 'pending'
    """)
    
    requests = c.fetchall()
    conn.close()
    
    if not requests:
        await message.answer("📭 Активных заявок на вывод нет!")
        return
    
    for req in requests:
        req_id, user_id, amount, name, timestamp = req
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить",
                    callback_data=f"approve_withdraw_{req_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"reject_withdraw_{req_id}"
                )
            ]
        ])
        
        await message.answer(
            f"📨 Заявка #{req_id}\n"
            f"👤 Пользователь: {name} (ID: {user_id})\n"
            f"💫 Сумма: {amount} звёзд\n"
            f"📅 Дата: {timestamp}",
            reply_markup=keyboard
        )    


@dp.message(F.text == "📈 Статистика модератора")
async def mod_stats_start(message: types.Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if user["role"] != "owner":
        return
    
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    # Получаем список модераторов
    c.execute("SELECT user_id, first_name FROM users WHERE role = 'moderator'")
    moderators = c.fetchall()
    
    if not moderators:
        await message.answer("❌ В системе нет модераторов!")
        return
    
    text = "📊 Выберите модератора для просмотра статистики:\n\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for mod_id, name in moderators:
        text += f"👤 {name} (ID: {mod_id})\n"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{name}",
                callback_data=f"mod_stats_{mod_id}"
            )
        ])
    
    conn.close()
    await message.answer(text, reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith('mod_stats_'))
async def show_mod_stats_detail(callback_query: CallbackQuery):
    mod_id = int(callback_query.data.split('_')[2])
    
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    
    # Статистика за сегодня
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    c.execute("""
        SELECT COALESCE(SUM(approved_tasks), 0), COALESCE(SUM(rejected_tasks), 0)
        FROM mod_stats 
        WHERE moderator_id = ? AND date = ?
    """, (mod_id, today))
    today_stats = c.fetchone()
    
    # Общая статистика
    c.execute("""
        SELECT COALESCE(SUM(approved_tasks), 0), COALESCE(SUM(rejected_tasks), 0)
        FROM mod_stats 
        WHERE moderator_id = ?
    """, (mod_id,))
    total_stats = c.fetchone()
    
    c.execute("SELECT first_name FROM users WHERE user_id = ?", (mod_id,))
    mod_name = c.fetchone()[0]
    
    conn.close()
    
    await callback_query.message.answer(
        f"📊 Статистика модератора {mod_name}:\n\n"
        f"За сегодня:\n"
        f"✅ Одобрено: {today_stats[0]}\n"
        f"❌ Отклонено: {today_stats[1]}\n\n"
        f"За всё время:\n"
        f"✅ Одобрено: {total_stats[0]}\n"
        f"❌ Отклонено: {total_stats[1]}"
    )
    await callback_query.answer()


@dp.error()
async def error_handler(update: types.Update, exception: Exception):
    for owner_id in OWNERS:
        await bot.send_message(
            owner_id,
            f"❌ Произошла ошибка:\n"
            f"Update: {update}\n"
            f"Error: {exception}"
        )

async def main():
    try:
        init_db()
        # Удаляем webhook перед запуском бота
        await bot.delete_webhook(drop_pending_updates=True)
        print("🤖 Бот запущен!")
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
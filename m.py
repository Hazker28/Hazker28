import asyncio
import logging
import random
import hashlib
import datetime
from typing import Union, Dict, List
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.filters.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
import aiosqlite
import os

# Константы
TOKEN = '8163139120:AAHg1QkcPAmiHPFWM0NIUtOj6G0OMVUyEpc'
REQUIRED_CHANNELS = [-1002166881231]
OWNERS_IDS = [1690656583, 6673580092]
DEVELOPERS_IDS = [6675836752, 6673580092]
ADMIN_CHANNEL = -1002363437612
REVIEWS_CHANNEL = -1002166881231

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния FSM
class UserStates(StatesGroup):
    waiting_for_promo = State()
    waiting_for_task_proof = State()
    waiting_for_withdrawal_amount = State()
    waiting_for_admin_command = State()

# Класс для работы с базой данных
class Database:
    def __init__(self, db_name: str = "bot_database.db"):
        self.db_name = db_name

    async def create_tables(self):
        async with aiosqlite.connect(self.db_name) as db:
            # Таблица пользователей
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    rank TEXT DEFAULT 'user',
                    balance INTEGER DEFAULT 0,
                    referrer_id INTEGER,
                    join_date TIMESTAMP,
                    ban_status BOOLEAN DEFAULT FALSE,
                    warnings INTEGER DEFAULT 0,
                    total_referrals INTEGER DEFAULT 0
                )
            ''')

            # Таблица промокодов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS promo_codes (
                    code TEXT PRIMARY KEY,
                    reward INTEGER,
                    max_uses INTEGER,
                    current_uses INTEGER DEFAULT 0,
                    created_by INTEGER,
                    created_at TIMESTAMP
                )
            ''')

            # Таблица использованных промокодов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS used_promo_codes (
                    user_id INTEGER,
                    code TEXT,
                    used_at TIMESTAMP,
                    PRIMARY KEY (user_id, code)
                )
            ''')

            # Таблица заданий
            await db.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_link TEXT,
                    reward INTEGER,
                    created_by INTEGER,
                    created_at TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    max_participants INTEGER
                )
            ''')

            # Таблица выполненных заданий
            await db.execute('''
                CREATE TABLE IF NOT EXISTS completed_tasks (
                    user_id INTEGER,
                    task_id INTEGER,
                    completed_at TIMESTAMP,
                    proof_message_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    moderator_id INTEGER,
                    PRIMARY KEY (user_id, task_id)
                )
            ''')

            # Таблица действий модераторов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS moderator_actions (
                    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    moderator_id INTEGER,
                    action_type TEXT,
                    target_user_id INTEGER,
                    description TEXT,
                    timestamp TIMESTAMP
                )
            ''')

            await db.commit()

    async def add_user(self, user_id: int, username: str, first_name: str, referrer_id: int = None):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name, referrer_id, join_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, referrer_id, datetime.datetime.now()))
            await db.commit()

    async def get_user(self, user_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
                return await cursor.fetchone()

# Клавиатуры
def get_main_keyboard(user_rank: str) -> types.ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    
    # Базовые кнопки для всех пользователей
    builder.row(types.KeyboardButton(text="🌟 Заработать звезды"))
    builder.row(types.KeyboardButton(text="👤 Профиль"))
    builder.row(
        types.KeyboardButton(text="🎁 Промокод"),
        types.KeyboardButton(text="📋 Задания")
    )
    builder.row(
        types.KeyboardButton(text="💫 Вывод звёзд"),
        types.KeyboardButton(text="🏆 Топ 10")
    )

    # Дополнительные кнопки в зависимости от ранга
    if user_rank in ['moderator', 'admin', 'owner', 'developer']:
        builder.row(types.KeyboardButton(text="🛠 Панель модератора"))
    
    if user_rank in ['admin', 'owner', 'developer']:
        builder.row(types.KeyboardButton(text="⚙️ Панель администратора"))
    
    if user_rank in ['owner', 'developer']:
        builder.row(types.KeyboardButton(text="👑 Панель владельца"))

    return builder.as_markup(resize_keyboard=True)

# Инициализация базы данных
db = Database()

@dp.startup()
async def on_startup():
    await db.create_tables()
    logger.info("Bot started and database initialized")
    
    
# Обработчики состояний FSM для различных действий
class AdminStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_stars = State()
    waiting_for_promo_code = State()
    waiting_for_promo_amount = State()
    waiting_for_promo_uses = State()
    waiting_for_task_link = State()
    waiting_for_task_reward = State()
    waiting_for_broadcast = State()

# Функции для проверки рангов пользователей
async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect(db.db_name) as conn:
        async with conn.execute('SELECT rank FROM users WHERE user_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
            if result:
                return result[0] in ['admin', 'owner', 'developer']
    return False

async def is_moderator(user_id: int) -> bool:
    async with aiosqlite.connect(db.db_name) as conn:
        async with conn.execute('SELECT rank FROM users WHERE user_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
            if result:
                return result[0] in ['moderator', 'admin', 'owner', 'developer']
    return False

async def is_owner(user_id: int) -> bool:
    return user_id in OWNERS_IDS

async def is_developer(user_id: int) -> bool:
    return user_id in DEVELOPERS_IDS

async def check_subscription(user_id: int) -> bool:
    try:
        for channel_id in REQUIRED_CHANNELS:
            member = await bot.get_chat_member(channel_id, user_id)
            if member.status in ['left', 'kicked', 'banned']:
                return False
        return True
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        return False

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    
    # Проверяем, есть ли реферальный код в команде start
    ref_id = None
    if len(message.text.split()) > 1:
        try:
            ref_id = int(message.text.split()[1])
        except ValueError:
            ref_id = None

    # Проверяем наличие пользователя в базе
    async with aiosqlite.connect(db.db_name) as conn:
        async with conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
            existing_user = await cursor.fetchone()

        if not existing_user:
            # Проверяем подписку на канал
            if not await check_subscription(user_id):
                builder = InlineKeyboardBuilder()
                builder.row(types.InlineKeyboardButton(
                    text="📢 Подписаться на канал",
                    url=f"https://t.me/{abs(REQUIRED_CHANNELS[0])}"
                ))
                builder.row(types.InlineKeyboardButton(
                    text="🔄 Проверить подписку",
                    callback_data="check_sub"
                ))
                
                await message.answer(
                    "👋 Привет! Для использования бота необходимо подписаться на наш канал:",
                    reply_markup=builder.as_markup()
                )
                return

            # Добавляем нового пользователя
            await db.add_user(user_id, username, first_name, ref_id)
            
            # Если есть реферер, начисляем ему звезду
            if ref_id:
                await conn.execute(
                    'UPDATE users SET balance = balance + 1, total_referrals = total_referrals + 1 WHERE user_id = ?',
                    (ref_id,)
                )
                await conn.commit()
                
                # Уведомляем реферера
                try:
                    await bot.send_message(
                        ref_id,
                        f"🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!\n"
                        f"На ваш баланс начислена 1 звезда ⭐"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify referrer: {e}")

            welcome_text = (
                f"👋 Добро пожаловать, {first_name}!\n\n"
                "🌟 Это бот для заработка звёзд через выполнение заданий.\n"
                "💫 Звёзды можно обменять на различные призы.\n\n"
                "📌 Используйте кнопки меню для навигации:"
            )
            
            await message.answer(welcome_text, reply_markup=get_main_keyboard('user'))
        else:
            # Если пользователь уже существует
            async with conn.execute('SELECT rank FROM users WHERE user_id = ?', (user_id,)) as cursor:
                rank = (await cursor.fetchone())[0]
            
            await message.answer(
                f"С возвращением, {first_name}!",
                reply_markup=get_main_keyboard(rank)
            )

# Обработчик проверки подписки
@dp.callback_query(F.data == "check_sub")
async def check_subscription_callback(callback: types.CallbackQuery):
    if await check_subscription(callback.from_user.id):
        await db.add_user(
            callback.from_user.id,
            callback.from_user.username,
            callback.from_user.first_name
        )
        await callback.message.edit_text(
            "✅ Подписка подтверждена!\nТеперь вы можете пользоваться ботом.",
            reply_markup=None
        )
        await callback.message.answer(
            "🌟 Добро пожаловать в главное меню!",
            reply_markup=get_main_keyboard('user')
        )
    else:
        await callback.answer("❌ Вы не подписались на канал!", show_alert=True)

# Обработчик кнопки "Заработать звезды"
@dp.message(F.text == "🌟 Заработать звезды")
async def earn_stars(message: types.Message):
    user_id = message.from_user.id
    ref_link = f"https://t.me/{(await bot.me()).username}?start={user_id}"
    
    text = (
        "💫 Способы заработка звёзд:\n\n"
        "1️⃣ Приглашайте друзей по своей реферальной ссылке:\n"
        f"{ref_link}\n"
        "За каждого приглашенного друга вы получите 1 звезду ⭐\n\n"
        "2️⃣ Выполняйте задания в разделе «📋 Задания»\n\n"
        "3️⃣ Используйте промокоды в разделе «🎁 Промокод»\n\n"
        "4️⃣ Участвуйте в конкурсах и акциях в нашем канале"
    )
    
    await message.answer(text)
    
# Обработчик кнопки "Профиль"
@dp.message(F.text == "👤 Профиль")
async def show_profile(message: types.Message):
    user_id = message.from_user.id
    
    async with aiosqlite.connect(db.db_name) as conn:
        async with conn.execute('''
            SELECT u.*, 
                   (SELECT COUNT(*) FROM users) as total_users,
                   (SELECT COUNT(*) FROM completed_tasks WHERE user_id = ? AND status = 'approved') as completed_tasks
            FROM users u 
            WHERE u.user_id = ?
        ''', (user_id, user_id)) as cursor:
            user_data = await cursor.fetchone()
    
    if not user_data:
        await message.answer("❌ Ошибка получения данных профиля")
        return

    rank_emoji = {
        'user': '👤',
        'moderator': '🛡',
        'admin': '⚜️',
        'owner': '👑',
        'developer': '⚡'
    }

    profile_text = (
        f"📱 ID: `{user_data[0]}`\n"
        f"👤 Имя: {user_data[2]}\n"
        f"🏅 Ранг: {rank_emoji.get(user_data[3], '❓')} {user_data[3].title()}\n"
        f"⭐ Баланс: {user_data[4]} звёзд\n"
        f"👥 Рефералов: {user_data[9]}\n"
        f"✅ Выполнено заданий: {user_data[11]}\n"
        f"⚠️ Предупреждений: {user_data[8]}/3\n"
        f"📊 Всего пользователей в боте: {user_data[10]}\n"
        f"📅 Дата регистрации: {user_data[6]}"
    )

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="📋 История операций",
        callback_data=f"history_{user_id}"
    ))

    await message.answer(
        profile_text,
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )

# Обработчик истории операций
@dp.callback_query(F.data.startswith("history_"))
async def show_history(callback: types.CallbackQuery):
    user_id = int(callback.data.split('_')[1])
    
    if callback.from_user.id != user_id:
        await callback.answer("❌ Это не ваш профиль!", show_alert=True)
        return

    async with aiosqlite.connect(db.db_name) as conn:
        # Получаем последние операции пользователя
        async with conn.execute('''
            SELECT operation_type, amount, timestamp 
            FROM operations 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT 5
        ''', (user_id,)) as cursor:
            operations = await cursor.fetchall()

    if not operations:
        await callback.answer("История операций пуста", show_alert=True)
        return

    history_text = "📋 Последние операции:\n\n"
    for op in operations:
        history_text += f"{'➕' if op[1] > 0 else '➖'} {abs(op[1])} ⭐ - {op[0]}\n"
        history_text += f"📅 {op[2]}\n\n"

    await callback.message.answer(history_text)

# Система промокодов
class PromoCode:
    def __init__(self, db_name: str):
        self.db_name = db_name

    async def create_promo(self, code: str, reward: int, max_uses: int, created_by: int) -> bool:
        async with aiosqlite.connect(self.db_name) as conn:
            try:
                await conn.execute('''
                    INSERT INTO promo_codes (code, reward, max_uses, created_by, created_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (code, reward, max_uses, created_by, datetime.datetime.now()))
                await conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error creating promo code: {e}")
                return False

    async def use_promo(self, user_id: int, code: str) -> tuple[bool, str, int]:
        async with aiosqlite.connect(self.db_name) as conn:
            # Проверяем существование промокода
            async with conn.execute(
                'SELECT reward, max_uses, current_uses FROM promo_codes WHERE code = ?',
                (code,)
            ) as cursor:
                promo_data = await cursor.fetchone()

            if not promo_data:
                return False, "❌ Промокод не существует!", 0

            reward, max_uses, current_uses = promo_data

            if current_uses >= max_uses:
                return False, "❌ Промокод больше не действителен!", 0

            # Проверяем, использовал ли пользователь этот промокод ранее
            async with conn.execute(
                'SELECT 1 FROM used_promo_codes WHERE user_id = ? AND code = ?',
                (user_id, code)
            ) as cursor:
                if await cursor.fetchone():
                    return False, "❌ Вы уже использовали этот промокод!", 0

            # Используем промокод
            await conn.execute('''
                INSERT INTO used_promo_codes (user_id, code, used_at)
                VALUES (?, ?, ?)
            ''', (user_id, code, datetime.datetime.now()))

            await conn.execute('''
                UPDATE promo_codes 
                SET current_uses = current_uses + 1 
                WHERE code = ?
            ''', (code,))

            # Начисляем награду пользователю
            await conn.execute('''
                UPDATE users 
                SET balance = balance + ? 
                WHERE user_id = ?
            ''', (reward, user_id))

            await conn.commit()
            return True, f"✅ Промокод активирован! Начислено {reward} ⭐", reward

# Обработчик кнопки "Промокод"
@dp.message(F.text == "🎁 Промокод")
async def promo_code_handler(message: types.Message, state: FSMContext):
    await state.set_state(UserStates.waiting_for_promo)
    await message.answer(
        "📝 Введите промокод для активации:",
        reply_markup=types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="🔙 Отмена")]],
            resize_keyboard=True
        )
    )

# Обработчик ввода промокода
@dp.message(UserStates.waiting_for_promo)
async def process_promo_code(message: types.Message, state: FSMContext):
    if message.text == "🔙 Отмена":
        await state.clear()
        await message.answer(
            "❌ Ввод промокода отменен",
            reply_markup=get_main_keyboard('user')
        )
        return

    promo_system = PromoCode(db.db_name)
    success, message_text, reward = await promo_system.use_promo(
        message.from_user.id,
        message.text.strip().upper()
    )

    await state.clear()
    await message.answer(
        message_text,
        reply_markup=get_main_keyboard('user')
    )

    # Логируем использование промокода
    if success:
        logger.info(
            f"User {message.from_user.id} used promo code {message.text} "
            f"and received {reward} stars"
        )
        
# Система заданий
class Task:
    def __init__(self, db_name: str):
        self.db_name = db_name

    async def create_task(self, channel_link: str, reward: int, created_by: int, max_participants: int) -> bool:
        async with aiosqlite.connect(self.db_name) as conn:
            try:
                await conn.execute('''
                    INSERT INTO tasks (channel_link, reward, created_by, created_at, max_participants)
                    VALUES (?, ?, ?, ?, ?)
                ''', (channel_link, reward, created_by, datetime.datetime.now(), max_participants))
                await conn.commit()
                return True
            except Exception as e:
                logger.error(f"Error creating task: {e}")
                return False

    async def get_active_tasks(self) -> list:
        async with aiosqlite.connect(self.db_name) as conn:
            async with conn.execute('''
                SELECT t.*, 
                       (SELECT COUNT(*) FROM completed_tasks WHERE task_id = t.task_id) as participants
                FROM tasks t 
                WHERE t.status = 'active' 
                AND (SELECT COUNT(*) FROM completed_tasks WHERE task_id = t.task_id) < t.max_participants
            ''') as cursor:
                return await cursor.fetchall()

    async def submit_task(self, user_id: int, task_id: int, proof_message_id: int) -> tuple[bool, str]:
        async with aiosqlite.connect(self.db_name) as conn:
            # Проверяем, не выполнял ли пользователь это задание ранее
            async with conn.execute(
                'SELECT 1 FROM completed_tasks WHERE user_id = ? AND task_id = ?',
                (user_id, task_id)
            ) as cursor:
                if await cursor.fetchone():
                    return False, "❌ Вы уже выполняли это задание!"

            # Проверяем, не достигнут ли лимит участников
            async with conn.execute('''
                SELECT t.max_participants, 
                       (SELECT COUNT(*) FROM completed_tasks WHERE task_id = t.task_id) as current_participants
                FROM tasks t 
                WHERE t.task_id = ?
            ''', (task_id,)) as cursor:
                task_data = await cursor.fetchone()
                
                if not task_data:
                    return False, "❌ Задание не найдено!"
                
                if task_data[1] >= task_data[0]:
                    return False, "❌ Достигнут лимит участников задания!"

            # Записываем выполнение задания
            await conn.execute('''
                INSERT INTO completed_tasks (user_id, task_id, completed_at, proof_message_id)
                VALUES (?, ?, ?, ?)
            ''', (user_id, task_id, datetime.datetime.now(), proof_message_id))
            
            await conn.commit()
            return True, "✅ Задание отправлено на проверку модератору!"

# Обработчик кнопки "Задания"
@dp.message(F.text == "📋 Задания")
async def show_tasks(message: types.Message):
    task_system = Task(db.db_name)
    tasks = await task_system.get_active_tasks()

    if not tasks:
        await message.answer("😕 Активных заданий пока нет. Загляните позже!")
        return

    for task in tasks:
        task_id, channel_link, reward, _, created_at, status, max_participants, current_participants = task
        
        builder = InlineKeyboardBuilder()
        builder.row(types.InlineKeyboardButton(
            text="📢 Перейти в канал",
            url=channel_link
        ))
        builder.row(types.InlineKeyboardButton(
            text="✅ Отправить подтверждение",
            callback_data=f"submit_task_{task_id}"
        ))

        task_text = (
            f"📋 Задание #{task_id}\n\n"
            f"📢 Канал: {channel_link}\n"
            f"⭐ Награда: {reward} звёзд\n"
            f"👥 Участников: {current_participants}/{max_participants}\n"
            f"📅 Создано: {created_at}\n\n"
            "📝 Для выполнения:\n"
            "1. Подпишитесь на канал\n"
            "2. Сделайте скриншот подписки\n"
            "3. Нажмите кнопку «Отправить подтверждение»"
        )

        await message.answer(task_text, reply_markup=builder.as_markup())

# Обработчик отправки подтверждения задания
@dp.callback_query(F.data.startswith("submit_task_"))
async def submit_task_handler(callback: types.CallbackQuery, state: FSMContext):
    task_id = int(callback.data.split('_')[2])
    await state.update_data(task_id=task_id)
    await state.set_state(UserStates.waiting_for_task_proof)
    
    await callback.message.answer(
        "📸 Отправьте скриншот подтверждающий выполнение задания.\n"
        "❗ Принимаются только фото или видео.",
        reply_markup=types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="🔙 Отмена")]],
            resize_keyboard=True
        )
    )
    await callback.answer()

# Обработчик получения доказательства выполнения задания
@dp.message(UserStates.waiting_for_task_proof, F.photo | F.video)
async def process_task_proof(message: types.Message, state: FSMContext):
    state_data = await state.get_data()
    task_id = state_data['task_id']
    
    # Сохраняем proof_message_id для модераторов
    task_system = Task(db.db_name)
    success, response_text = await task_system.submit_task(
        message.from_user.id,
        task_id,
        message.message_id
    )

    await state.clear()
    await message.answer(
        response_text,
        reply_markup=get_main_keyboard('user')
    )

    if success:
        # Отправляем задание случайному модератору
        async with aiosqlite.connect(db.db_name) as conn:
            async with conn.execute(
                "SELECT user_id FROM users WHERE rank IN ('moderator', 'admin', 'owner', 'developer')"
            ) as cursor:
                moderators = await cursor.fetchall()

        if moderators:
            chosen_moderator = random.choice(moderators)[0]
            
            # Пересылаем доказательство модератору
            forwarded_msg = await message.forward(chosen_moderator)
            
            builder = InlineKeyboardBuilder()
            builder.row(
                types.InlineKeyboardButton(
                    text="✅ Одобрить",
                    callback_data=f"approve_task_{task_id}_{message.from_user.id}"
                ),
                types.InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"reject_task_{task_id}_{message.from_user.id}"
                )
            )

            await bot.send_message(
                chosen_moderator,
                f"📋 Новое задание на проверку!\n"
                f"👤 Пользователь: {message.from_user.id}\n"
                f"📝 Задание: #{task_id}",
                reply_markup=builder.as_markup()
            )

# Обработчик отмены отправки доказательства
@dp.message(UserStates.waiting_for_task_proof, F.text == "🔙 Отмена")
async def cancel_task_proof(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "❌ Отправка доказательства отменена",
        reply_markup=get_main_keyboard('user')
    )
    
# Панель модератора
@dp.message(F.text == "🛡 Панель модератора")
async def moderator_panel(message: types.Message):
    if not await is_moderator(message.from_user.id):
        await message.answer("❌ У вас нет доступа к панели модератора!")
        return

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="📋 Активные заявки",
        callback_data="mod_active_tasks"
    ))
    builder.row(types.InlineKeyboardButton(
        text="📊 Статистика",
        callback_data="mod_stats"
    ))
    
    await message.answer(
        "🛡 Панель модератора\n\n"
        "Выберите действие:",
        reply_markup=builder.as_markup()
    )

# Обработчик активных заявок модератора
@dp.callback_query(F.data == "mod_active_tasks")
async def show_active_moderator_tasks(callback: types.CallbackQuery):
    if not await is_moderator(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return

    async with aiosqlite.connect(db.db_name) as conn:
        async with conn.execute('''
            SELECT ct.*, t.reward, u.first_name 
            FROM completed_tasks ct
            JOIN tasks t ON ct.task_id = t.task_id
            JOIN users u ON ct.user_id = u.user_id
            WHERE ct.moderator_id = ? AND ct.status = 'pending'
        ''', (callback.from_user.id,)) as cursor:
            tasks = await cursor.fetchall()

    if not tasks:
        await callback.answer("У вас нет активных заявок на проверку!", show_alert=True)
        return

    for task in tasks:
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(
                text="✅ Одобрить",
                callback_data=f"approve_task_{task[1]}_{task[0]}"
            ),
            types.InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=f"reject_task_{task[1]}_{task[0]}"
            )
        )

        await callback.message.answer(
            f"📋 Заявка на проверку #{task[1]}\n"
            f"👤 Пользователь: {task[7]}\n"
            f"⭐ Награда: {task[6]} звёзд\n"
            f"📅 Отправлено: {task[2]}",
            reply_markup=builder.as_markup()
        )

# Обработчики одобрения/отклонения заданий
@dp.callback_query(F.data.startswith("approve_task_"))
async def approve_task(callback: types.CallbackQuery):
    if not await is_moderator(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return

    _, task_id, user_id = callback.data.split('_')
    task_id, user_id = int(task_id), int(user_id)

    async with aiosqlite.connect(db.db_name) as conn:
        # Получаем награду за задание
        async with conn.execute(
            'SELECT reward FROM tasks WHERE task_id = ?',
            (task_id,)
        ) as cursor:
            task_data = await cursor.fetchone()
            
        if not task_data:
            await callback.answer("❌ Задание не найдено!", show_alert=True)
            return

        reward = task_data[0]

        # Обновляем статус задания и начисляем награду
        await conn.execute('''
            UPDATE completed_tasks 
            SET status = 'approved', moderator_id = ? 
            WHERE task_id = ? AND user_id = ?
        ''', (callback.from_user.id, task_id, user_id))

        await conn.execute('''
            UPDATE users 
            SET balance = balance + ? 
            WHERE user_id = ?
        ''', (reward, user_id))

        # Логируем действие модератора
        await conn.execute('''
            INSERT INTO moderator_actions (moderator_id, action_type, target_user_id, description, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            callback.from_user.id,
            'approve_task',
            user_id,
            f'Approved task #{task_id} with reward {reward}',
            datetime.datetime.now()
        ))

        await conn.commit()

    # Уведомляем пользователя
    try:
        await bot.send_message(
            user_id,
            f"✅ Ваше задание #{task_id} одобрено!\n"
            f"⭐ На ваш баланс начислено {reward} звёзд."
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")

    await callback.message.edit_text(
        f"✅ Задание #{task_id} одобрено!\n"
        f"👤 Пользователь: {user_id}\n"
        f"⭐ Начислено: {reward} звёзд",
        reply_markup=None
    )

@dp.callback_query(F.data.startswith("reject_task_"))
async def reject_task(callback: types.CallbackQuery):
    if not await is_moderator(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return

    _, task_id, user_id = callback.data.split('_')
    task_id, user_id = int(task_id), int(user_id)

    async with aiosqlite.connect(db.db_name) as conn:
        await conn.execute('''
            UPDATE completed_tasks 
            SET status = 'rejected', moderator_id = ? 
            WHERE task_id = ? AND user_id = ?
        ''', (callback.from_user.id, task_id, user_id))

        # Логируем действие модератора
        await conn.execute('''
            INSERT INTO moderator_actions (moderator_id, action_type, target_user_id, description, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            callback.from_user.id,
            'reject_task',
            user_id,
            f'Rejected task #{task_id}',
            datetime.datetime.now()
        ))

        await conn.commit()

    # Уведомляем пользователя
    try:
        await bot.send_message(
            user_id,
            f"❌ Ваше задание #{task_id} отклонено!\n"
            "Пожалуйста, проверьте правильность выполнения и попробуйте снова."
        )
    except Exception as e:
        logger.error(f"Failed to notify user {user_id}: {e}")

    await callback.message.edit_text(
        f"❌ Задание #{task_id} отклонено!\n"
        f"👤 Пользователь: {user_id}",
        reply_markup=None
    )

# Статистика модератора
@dp.callback_query(F.data == "mod_stats")
async def show_moderator_stats(callback: types.CallbackQuery):
    if not await is_moderator(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return

    async with aiosqlite.connect(db.db_name) as conn:
        async with conn.execute('''
            SELECT 
                COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected
            FROM completed_tasks 
            WHERE moderator_id = ?
        ''', (callback.from_user.id,)) as cursor:
            stats = await cursor.fetchone()

    stats_text = (
        "📊 Ваша статистика:\n\n"
        f"✅ Одобрено заданий: {stats[0]}\n"
        f"❌ Отклонено заданий: {stats[1]}\n"
        f"📝 Всего проверено: {stats[0] + stats[1]}"
    )

    await callback.message.edit_text(stats_text)
    
    
# Панель администратора
@dp.message(F.text == "⚜️ Панель администратора")
async def admin_panel(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к панели администратора!")
        return

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="👥 Управление модераторами",
        callback_data="admin_mod_manage"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔍 Поиск пользователя",
        callback_data="admin_search_user"
    ))
    builder.row(types.InlineKeyboardButton(
        text="⚠️ Управление наказаниями",
        callback_data="admin_punishments"
    ))
    builder.row(types.InlineKeyboardButton(
        text="📊 Статистика бота",
        callback_data="admin_bot_stats"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔄 Проверка подписок",
        callback_data="admin_check_subs"
    ))

    await message.answer(
        "⚜️ Панель администратора\n\n"
        "Выберите действие:",
        reply_markup=builder.as_markup()
    )

# Управление модераторами
@dp.callback_query(F.data == "admin_mod_manage")
async def manage_moderators(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="➕ Добавить модератора",
        callback_data="add_moderator"
    ))
    builder.row(types.InlineKeyboardButton(
        text="➖ Удалить модератора",
        callback_data="remove_moderator"
    ))
    builder.row(types.InlineKeyboardButton(
        text="📋 Список модераторов",
        callback_data="list_moderators"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_admin"
    ))

    await callback.message.edit_text(
        "👥 Управление модераторами\n\n"
        "Выберите действие:",
        reply_markup=builder.as_markup()
    )

# Добавление модератора
@dp.callback_query(F.data == "add_moderator")
async def add_moderator_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_user_id)
    await callback.message.edit_text(
        "👤 Введите ID пользователя для назначения модератором:",
        reply_markup=InlineKeyboardBuilder().row(
            types.InlineKeyboardButton(
                text="🔙 Отмена",
                callback_data="cancel_admin_action"
            )
        ).as_markup()
    )

@dp.message(AdminStates.waiting_for_user_id)
async def process_add_moderator(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите корректный ID пользователя!")
        return

    user_id = int(message.text)
    async with aiosqlite.connect(db.db_name) as conn:
        # Проверяем существование пользователя
        async with conn.execute(
            'SELECT rank FROM users WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            user_data = await cursor.fetchone()

        if not user_data:
            await message.answer("❌ Пользователь не найден в базе данных!")
            await state.clear()
            return

        if user_data[0] in ['admin', 'owner', 'developer']:
            await message.answer("❌ Невозможно изменить ранг этого пользователя!")
            await state.clear()
            return

        # Назначаем модератором
        await conn.execute(
            'UPDATE users SET rank = ? WHERE user_id = ?',
            ('moderator', user_id)
        )

        # Логируем действие
        await conn.execute('''
            INSERT INTO admin_actions (admin_id, action_type, target_user_id, description, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            message.from_user.id,
            'add_moderator',
            user_id,
            'Added as moderator',
            datetime.datetime.now()
        ))

        await conn.commit()

    await message.answer(f"✅ Пользователь {user_id} назначен модератором!")
    await state.clear()

    # Уведомляем пользователя
    try:
        await bot.send_message(
            user_id,
            "🎉 Поздравляем! Вы назначены модератором бота!\n"
            "Используйте команду /start для обновления меню."
        )
    except Exception as e:
        logger.error(f"Failed to notify new moderator {user_id}: {e}")

# Удаление модератора
@dp.callback_query(F.data == "remove_moderator")
async def list_moderators_for_removal(callback: types.CallbackQuery):
    async with aiosqlite.connect(db.db_name) as conn:
        async with conn.execute(
            'SELECT user_id, first_name FROM users WHERE rank = ?',
            ('moderator',)
        ) as cursor:
            moderators = await cursor.fetchall()

    if not moderators:
        await callback.answer("❌ Нет активных модераторов!", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for mod_id, mod_name in moderators:
        builder.row(types.InlineKeyboardButton(
            text=f"{mod_name} ({mod_id})",
            callback_data=f"remove_mod_{mod_id}"
        ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="admin_mod_manage"
    ))

    await callback.message.edit_text(
        "🔄 Выберите модератора для удаления:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.startswith("remove_mod_"))
async def remove_moderator(callback: types.CallbackQuery):
    mod_id = int(callback.data.split('_')[2])

    async with aiosqlite.connect(db.db_name) as conn:
        await conn.execute(
            'UPDATE users SET rank = ? WHERE user_id = ?',
            ('user', mod_id)
        )

        # Логируем действие
        await conn.execute('''
            INSERT INTO admin_actions (admin_id, action_type, target_user_id, description, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            callback.from_user.id,
            'remove_moderator',
            mod_id,
            'Removed from moderators',
            datetime.datetime.now()
        ))

        await conn.commit()

    await callback.message.edit_text(
        f"✅ Модератор {mod_id} успешно снят с должности!"
    )

    # Уведомляем пользователя
    try:
        await bot.send_message(
            mod_id,
            "ℹ️ Вы были сняты с должности модератора.\n"
            "Используйте команду /start для обновления меню."
        )
    except Exception as e:
        logger.error(f"Failed to notify removed moderator {mod_id}: {e}")
        
        
# Поиск пользователя (админ-панель)
@dp.callback_query(F.data == "admin_search_user")
async def search_user_start(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🔍 Поиск по ID",
        callback_data="search_by_id"
    ))
    builder.row(types.InlineKeyboardButton(
        text="👤 Поиск по имени",
        callback_data="search_by_name"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_admin"
    ))

    await callback.message.edit_text(
        "🔍 Выберите способ поиска:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "search_by_id")
async def search_by_id_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_user_id)
    await callback.message.edit_text(
        "Введите ID пользователя:",
        reply_markup=InlineKeyboardBuilder().row(
            types.InlineKeyboardButton(
                text="🔙 Отмена",
                callback_data="cancel_admin_action"
            )
        ).as_markup()
    )

async def get_user_info(user_id: int) -> str:
    async with aiosqlite.connect(db.db_name) as conn:
        async with conn.execute('''
            SELECT u.*, 
                   (SELECT COUNT(*) FROM completed_tasks 
                    WHERE user_id = u.user_id AND status = 'approved') as completed_tasks,
                   (SELECT COUNT(*) FROM users WHERE referrer_id = u.user_id) as referrals
            FROM users u 
            WHERE u.user_id = ?
        ''', (user_id,)) as cursor:
            user_data = await cursor.fetchone()

        if not user_data:
            return "❌ Пользователь не найден!"

        return (
            f"👤 Профиль пользователя\n\n"
            f"🆔 ID: {user_data[0]}\n"
            f"👤 Имя: {user_data[2]}\n"
            f"🏅 Ранг: {user_data[3]}\n"
            f"⭐ Баланс: {user_data[4]} звёзд\n"
            f"👥 Рефералов: {user_data[11]}\n"
            f"✅ Выполнено заданий: {user_data[10]}\n"
            f"⚠️ Предупреждений: {user_data[8]}/3\n"
            f"🚫 Бан: {'Да' if user_data[7] else 'Нет'}\n"
            f"📅 Дата регистрации: {user_data[6]}"
        )

@dp.message(AdminStates.waiting_for_user_id)
async def process_user_search(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите корректный ID пользователя!")
        return

    user_id = int(message.text)
    user_info = await get_user_info(user_id)

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="⚠️ Выдать предупреждение",
        callback_data=f"warn_user_{user_id}"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🚫 Забанить",
        callback_data=f"ban_user_{user_id}"
    ))
    builder.row(types.InlineKeyboardButton(
        text="✅ Разбанить",
        callback_data=f"unban_user_{user_id}"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="admin_search_user"
    ))

    await message.answer(user_info, reply_markup=builder.as_markup())
    await state.clear()

# Управление наказаниями
@dp.callback_query(F.data.startswith("warn_user_"))
async def warn_user(callback: types.CallbackQuery):
    user_id = int(callback.data.split('_')[2])
    
    async with aiosqlite.connect(db.db_name) as conn:
        # Проверяем текущие предупреждения
        async with conn.execute(
            'SELECT warnings, rank FROM users WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            user_data = await cursor.fetchone()

        if not user_data:
            await callback.answer("❌ Пользователь не найден!", show_alert=True)
            return

        if user_data[1] in ['admin', 'owner', 'developer']:
            await callback.answer("❌ Нельзя выдать предупреждение этому пользователю!", show_alert=True)
            return

        new_warnings = user_data[0] + 1
        
        # Обновляем количество предупреждений
        await conn.execute(
            'UPDATE users SET warnings = ? WHERE user_id = ?',
            (new_warnings, user_id)
        )

        # Если достигнут лимит предупреждений - баним
        if new_warnings >= 3:
            await conn.execute(
                'UPDATE users SET ban_status = TRUE WHERE user_id = ?',
                (user_id,)
            )
            ban_message = "\n⛔ Достигнут лимит предупреждений - пользователь забанен!"
        else:
            ban_message = ""

        # Логируем действие
        await conn.execute('''
            INSERT INTO admin_actions (admin_id, action_type, target_user_id, description, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            callback.from_user.id,
            'warn_user',
            user_id,
            f'Warning {new_warnings}/3',
            datetime.datetime.now()
        ))

        await conn.commit()

    # Уведомляем пользователя
    try:
        await bot.send_message(
            user_id,
            f"⚠️ Вам выдано предупреждение!\n"
            f"Всего предупреждений: {new_warnings}/3\n"
            f"{ban_message}"
        )
    except Exception as e:
        logger.error(f"Failed to notify warned user {user_id}: {e}")

    await callback.answer(f"✅ Предупреждение выдано! ({new_warnings}/3){ban_message}", show_alert=True)
    
    # Обновляем информацию о пользователе
    user_info = await get_user_info(user_id)
    await callback.message.edit_text(user_info, reply_markup=callback.message.reply_markup)

# Панель владельца
@dp.message(F.text == "👑 Панель владельца")
async def owner_panel(message: types.Message):
    if not await is_owner(message.from_user.id):
        await message.answer("❌ У вас нет доступа к панели владельца!")
        return

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="⭐ Управление балансом",
        callback_data="owner_balance"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🎁 Управление промокодами",
        callback_data="owner_promo"
    ))
    builder.row(types.InlineKeyboardButton(
        text="📢 Создать рассылку",
        callback_data="owner_broadcast"
    ))
    builder.row(types.InlineKeyboardButton(
        text="👥 Управление админами",
        callback_data="owner_admins"
    ))
    builder.row(types.InlineKeyboardButton(
        text="📊 Полная статистика",
        callback_data="owner_stats"
    ))
    builder.row(types.InlineKeyboardButton(
        text="📋 Отслеживание действий",
        callback_data="owner_actions"
    ))

    await message.answer(
        "👑 Панель владельца\n\n"
        "Выберите действие:",
        reply_markup=builder.as_markup()
    )
    
# Управление балансом пользователей (панель владельца)
@dp.callback_query(F.data == "owner_balance")
async def manage_balance(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="➕ Выдать звёзды",
        callback_data="add_stars"
    ))
    builder.row(types.InlineKeyboardButton(
        text="➖ Забрать звёзды",
        callback_data="remove_stars"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_owner"
    ))

    await callback.message.edit_text(
        "⭐ Управление балансом пользователей\n"
        "Выберите действие:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.in_(["add_stars", "remove_stars"]))
async def balance_operation_start(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data
    await state.update_data(action=action)
    await state.set_state(AdminStates.waiting_for_user_id)
    
    await callback.message.edit_text(
        "👤 Введите ID пользователя:",
        reply_markup=InlineKeyboardBuilder().row(
            types.InlineKeyboardButton(
                text="🔙 Отмена",
                callback_data="cancel_owner_action"
            )
        ).as_markup()
    )

@dp.message(AdminStates.waiting_for_user_id)
async def process_balance_user_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите корректный ID пользователя!")
        return

    await state.update_data(target_user_id=int(message.text))
    await state.set_state(AdminStates.waiting_for_stars)
    
    await message.answer(
        "💫 Введите количество звёзд:",
        reply_markup=InlineKeyboardBuilder().row(
            types.InlineKeyboardButton(
                text="🔙 Отмена",
                callback_data="cancel_owner_action"
            )
        ).as_markup()
    )

@dp.message(AdminStates.waiting_for_stars)
async def process_balance_operation(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите корректное число звёзд!")
        return

    state_data = await state.get_data()
    action = state_data['action']
    target_user_id = state_data['target_user_id']
    stars = int(message.text)

    async with aiosqlite.connect(db.db_name) as conn:
        # Проверяем существование пользователя
        async with conn.execute(
            'SELECT balance FROM users WHERE user_id = ?',
            (target_user_id,)
        ) as cursor:
            user_data = await cursor.fetchone()

        if not user_data:
            await message.answer("❌ Пользователь не найден!")
            await state.clear()
            return

        current_balance = user_data[0]
        new_balance = current_balance + stars if action == "add_stars" else current_balance - stars

        if new_balance < 0:
            await message.answer("❌ У пользователя недостаточно звёзд!")
            await state.clear()
            return

        # Обновляем баланс
        await conn.execute(
            'UPDATE users SET balance = ? WHERE user_id = ?',
            (new_balance, target_user_id)
        )

        # Логируем действие
        await conn.execute('''
            INSERT INTO owner_actions (owner_id, action_type, target_user_id, description, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            message.from_user.id,
            'balance_operation',
            target_user_id,
            f'{"Added" if action == "add_stars" else "Removed"} {stars} stars',
            datetime.datetime.now()
        ))

        await conn.commit()

    operation_text = "начислено" if action == "add_stars" else "снято"
    await message.answer(
        f"✅ Операция выполнена успешно!\n"
        f"👤 Пользователю {target_user_id} {operation_text} {stars} ⭐\n"
        f"💫 Новый баланс: {new_balance} ⭐"
    )

    # Уведомляем пользователя
    try:
        await bot.send_message(
            target_user_id,
            f"{'➕' if action == 'add_stars' else '➖'} На вашем счету {operation_text} {stars} ⭐\n"
            f"💫 Текущий баланс: {new_balance} ⭐"
        )
    except Exception as e:
        logger.error(f"Failed to notify user {target_user_id}: {e}")

    await state.clear()

# Управление промокодами (панель владельца)
@dp.callback_query(F.data == "owner_promo")
async def manage_promo(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="➕ Создать промокод",
        callback_data="create_promo"
    ))
    builder.row(types.InlineKeyboardButton(
        text="❌ Удалить промокод",
        callback_data="delete_promo"
    ))
    builder.row(types.InlineKeyboardButton(
        text="📋 Список промокодов",
        callback_data="list_promos"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_owner"
    ))

    await callback.message.edit_text(
        "🎁 Управление промокодами\n"
        "Выберите действие:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "create_promo")
async def create_promo_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_promo_code)
    await callback.message.edit_text(
        "📝 Введите промокод (только латинские буквы и цифры):",
        reply_markup=InlineKeyboardBuilder().row(
            types.InlineKeyboardButton(
                text="🔙 Отмена",
                callback_data="cancel_owner_action"
            )
        ).as_markup()
    )
    
# Вывод звёзд
@dp.message(F.text == "💫 Вывод звёзд")
async def withdraw_stars(message: types.Message):
    builder = InlineKeyboardBuilder()
    amounts = [15, 25, 50, 100, 150, 250, 500]
    
    for amount in amounts:
        builder.row(types.InlineKeyboardButton(
            text=f"⭐ {amount} звёзд",
            callback_data=f"withdraw_{amount}"
        ))

    await message.answer(
        "💫 Выберите количество звёзд для вывода:\n\n"
        "⚠️ Минимальная сумма: 15 звёзд\n"
        "⏱ Время обработки: до 24 часов",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.startswith("withdraw_"))
async def process_withdrawal(callback: types.CallbackQuery):
    amount = int(callback.data.split('_')[1])
    user_id = callback.from_user.id

    async with aiosqlite.connect(db.db_name) as conn:
        # Проверяем баланс
        async with conn.execute(
            'SELECT balance FROM users WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            user_data = await cursor.fetchone()

        if not user_data or user_data[0] < amount:
            await callback.answer("❌ Недостаточно звёзд на балансе!", show_alert=True)
            return

        # Создаём заявку на вывод
        await conn.execute('''
            INSERT INTO withdrawal_requests (user_id, amount, status, created_at)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, 'pending', datetime.datetime.now()))

        # Замораживаем звёзды
        await conn.execute(
            'UPDATE users SET balance = balance - ? WHERE user_id = ?',
            (amount, user_id)
        )

        await conn.commit()

    # Отправляем уведомление админам
    for admin_id in OWNERS_IDS + DEVELOPERS_IDS:
        try:
            builder = InlineKeyboardBuilder()
            builder.row(
                types.InlineKeyboardButton(
                    text="✅ Одобрить",
                    callback_data=f"approve_withdraw_{user_id}_{amount}"
                ),
                types.InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"reject_withdraw_{user_id}_{amount}"
                )
            )

            await bot.send_message(
                admin_id,
                f"💫 Новая заявка на вывод!\n\n"
                f"👤 Пользователь: {user_id}\n"
                f"⭐ Сумма: {amount} звёзд\n"
                f"📅 Дата: {datetime.datetime.now()}",
                reply_markup=builder.as_markup()
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

    await callback.answer("✅ Заявка на вывод создана!", show_alert=True)

# Топ 10 пользователей
@dp.message(F.text == "🏆 Топ 10")
async def show_top_users(message: types.Message):
    async with aiosqlite.connect(db.db_name) as conn:
        async with conn.execute('''
            SELECT user_id, first_name, balance 
            FROM users 
            ORDER BY balance DESC 
            LIMIT 10
        ''') as cursor:
            top_users = await cursor.fetchall()

    if not top_users:
        await message.answer("😕 Пока нет пользователей с балансом.")
        return

    response = "🏆 Топ 10 пользователей по балансу:\n\n"
    for i, user in enumerate(top_users, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "👤")
        response += f"{medal} {i}. {user[1]}: {user[2]} ⭐\n"

    await message.answer(response)

# Команда /shop
@dp.message(Command("shop"))
async def shop_command(message: types.Message):
    async with aiosqlite.connect(db.db_name) as conn:
        async with conn.execute(
            'SELECT warnings FROM users WHERE user_id = ?',
            (message.from_user.id,)
        ) as cursor:
            user_data = await cursor.fetchone()

    if not user_data or user_data[0] == 0:
        await message.answer("❌ У вас нет предупреждений для снятия!")
        return

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🔄 Снять предупреждение (50 ⭐)",
        callback_data="remove_warning"
    ))

    await message.answer(
        f"⚠️ У вас {user_data[0]} предупреждений\n\n"
        "💫 Стоимость снятия одного предупреждения: 50 звёзд",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "remove_warning")
async def process_remove_warning(callback: types.CallbackQuery):
    async with aiosqlite.connect(db.db_name) as conn:
        async with conn.execute(
            'SELECT balance, warnings FROM users WHERE user_id = ?',
            (callback.from_user.id,)
        ) as cursor:
            user_data = await cursor.fetchone()

        if not user_data or user_data[0] < 50:
            await callback.answer("❌ Недостаточно звёзд!", show_alert=True)
            return

        if user_data[1] == 0:
            await callback.answer("❌ У вас нет предупреждений!", show_alert=True)
            return

        # Снимаем предупреждение и звёзды
        await conn.execute('''
            UPDATE users 
            SET warnings = warnings - 1,
                balance = balance - 50 
            WHERE user_id = ?
        ''', (callback.from_user.id,))

        await conn.commit()

    await callback.answer("✅ Предупреждение успешно снято!", show_alert=True)
    await callback.message.edit_text(
        "✅ Операция успешно выполнена!\n"
        f"💫 С баланса снято 50 звёзд\n"
        f"⚠️ Количество предупреждений уменьшено"
    )

# Команда /help
@dp.message(Command("help"))
async def help_command(message: types.Message):
    help_text = (
        "📚 Список доступных команд:\n\n"
        "/start - Запустить бота\n"
        "/help - Показать это сообщение\n"
        "/shop - Магазин (снятие предупреждений)\n\n"
        "💫 Как заработать звёзды:\n"
        "1. Приглашайте друзей\n"
        "2. Выполняйте задания\n"
        "3. Используйте промокоды\n\n"
        "⚠️ Правила:\n"
        "- Запрещено использовать ботов\n"
        "- Запрещено создавать мульти-аккаунты\n"
        "- За нарушения выдаются предупреждения\n"
        "- После 3-х предупреждений - бан\n\n"
        "🔰 Ранги:\n"
        "👤 Пользователь\n"
        "🛡 Модератор\n"
        "⚜️ Администратор\n"
        "👑 Владелец\n"
        "⚡ Разработчик"
    )
    
    await message.answer(help_text)
    
# Создание рассылки
@dp.callback_query(F.data == "owner_broadcast")
async def broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="📝 Текстовое сообщение",
        callback_data="broadcast_text"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🖼 Сообщение с фото",
        callback_data="broadcast_photo"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_owner"
    ))

    await callback.message.edit_text(
        "📢 Выберите тип рассылки:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.startswith("broadcast_"))
async def broadcast_type_select(callback: types.CallbackQuery, state: FSMContext):
    broadcast_type = callback.data.split('_')[1]
    await state.update_data(broadcast_type=broadcast_type)
    
    if broadcast_type == "text":
        await state.set_state(AdminStates.waiting_for_broadcast)
        await callback.message.edit_text(
            "📝 Введите текст рассылки:",
            reply_markup=InlineKeyboardBuilder().row(
                types.InlineKeyboardButton(
                    text="🔙 Отмена",
                    callback_data="cancel_owner_action"
                )
            ).as_markup()
        )
    else:
        await state.set_state(AdminStates.waiting_for_broadcast_photo)
        await callback.message.edit_text(
            "🖼 Отправьте фото для рассылки:",
            reply_markup=InlineKeyboardBuilder().row(
                types.InlineKeyboardButton(
                    text="🔙 Отмена",
                    callback_data="cancel_owner_action"
                )
            ).as_markup()
        )

@dp.message(AdminStates.waiting_for_broadcast)
async def process_broadcast_text(message: types.Message, state: FSMContext):
    async with aiosqlite.connect(db.db_name) as conn:
        async with conn.execute('SELECT user_id FROM users WHERE ban_status = FALSE') as cursor:
            users = await cursor.fetchall()

    success_count = 0
    fail_count = 0

    for user in users:
        try:
            await bot.send_message(user[0], message.text)
            success_count += 1
            await asyncio.sleep(0.05)  # Задержка между отправками
        except Exception as e:
            fail_count += 1
            logger.error(f"Failed to send broadcast to {user[0]}: {e}")

    await state.clear()
    await message.answer(
        f"📢 Рассылка завершена!\n\n"
        f"✅ Успешно: {success_count}\n"
        f"❌ Ошибок: {fail_count}"
    )

# Управление админами
@dp.callback_query(F.data == "owner_admins")
async def manage_admins(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="➕ Добавить админа",
        callback_data="add_admin"
    ))
    builder.row(types.InlineKeyboardButton(
        text="➖ Удалить админа",
        callback_data="remove_admin"
    ))
    builder.row(types.InlineKeyboardButton(
        text="📋 Список админов",
        callback_data="list_admins"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_owner"
    ))

    await callback.message.edit_text(
        "👥 Управление администраторами\n"
        "Выберите действие:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "list_admins")
async def list_admins(callback: types.CallbackQuery):
    async with aiosqlite.connect(db.db_name) as conn:
        async with conn.execute(
            "SELECT user_id, first_name FROM users WHERE rank = 'admin'"
        ) as cursor:
            admins = await cursor.fetchall()

    if not admins:
        await callback.answer("❌ Нет администраторов!", show_alert=True)
        return

    text = "📋 Список администраторов:\n\n"
    for admin in admins:
        text += f"👤 {admin[1]} (ID: {admin[0]})\n"

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="owner_admins"
    ))

    await callback.message.edit_text(text, reply_markup=builder.as_markup())

# Команда /destroy (только для разработчиков)
@dp.message(Command("destroy"))
async def destroy_command(message: types.Message):
    if not await is_developer(message.from_user.id):
        await message.answer("❌ Команда доступна только разработчикам!")
        return

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="💣 Подтвердить удаление",
        callback_data="confirm_destroy"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 Отмена",
        callback_data="cancel_destroy"
    ))

    await message.answer(
        "⚠️ ВНИМАНИЕ!\n\n"
        "Вы собираетесь удалить ВСЕ данные бота!\n"
        "Это действие необратимо!\n\n"
        "Вы уверены?",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data == "confirm_destroy")
async def confirm_destroy(callback: types.CallbackQuery):
    if not await is_developer(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return

    try:
        async with aiosqlite.connect(db.db_name) as conn:
            # Получаем список всех таблиц
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) as cursor:
                tables = await cursor.fetchall()

            # Удаляем все таблицы
            for table in tables:
                await conn.execute(f"DROP TABLE IF EXISTS {table[0]}")
            
            await conn.commit()

        await callback.message.edit_text(
            "💣 Все данные успешно удалены!\n"
            "Перезапустите бота командой /start"
        )

        logger.warning(f"Database destroyed by developer {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Error during database destruction: {e}")
        await callback.answer("❌ Ошибка при удалении данных!", show_alert=True)

@dp.callback_query(F.data == "cancel_destroy")
async def cancel_destroy(callback: types.CallbackQuery):
    await callback.message.edit_text("✅ Операция отменена")
    
    
# Полная статистика бота (панель владельца)
@dp.callback_query(F.data == "owner_stats")
async def show_full_stats(callback: types.CallbackQuery):
    async with aiosqlite.connect(db.db_name) as conn:
        stats = {}
        
        # Общая статистика пользователей
        async with conn.execute('''
            SELECT 
                COUNT(*) as total_users,
                SUM(CASE WHEN ban_status = TRUE THEN 1 ELSE 0 END) as banned_users,
                SUM(balance) as total_stars,
                SUM(total_referrals) as total_refs
            FROM users
        ''') as cursor:
            stats['users'] = await cursor.fetchone()

        # Статистика по рангам
        async with conn.execute('''
            SELECT rank, COUNT(*) 
            FROM users 
            GROUP BY rank
        ''') as cursor:
            stats['ranks'] = await cursor.fetchall()

        # Статистика заданий
        async with conn.execute('''
            SELECT 
                COUNT(*) as total_tasks,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_tasks,
                SUM(reward) as total_rewards
            FROM tasks
        ''') as cursor:
            stats['tasks'] = await cursor.fetchone()

        # Статистика выполненных заданий
        async with conn.execute('''
            SELECT 
                COUNT(*) as total_completed,
                SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
                SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected
            FROM completed_tasks
        ''') as cursor:
            stats['completed'] = await cursor.fetchone()

        # Статистика промокодов
        async with conn.execute('''
            SELECT 
                COUNT(*) as total_promos,
                SUM(current_uses) as total_uses,
                SUM(reward * current_uses) as total_given
            FROM promo_codes
        ''') as cursor:
            stats['promos'] = await cursor.fetchone()

    current_time = datetime.datetime.utcnow()
    stats_text = (
        f"📊 Полная статистика бота\n"
        f"📅 {current_time.strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
        f"👥 Пользователи:\n"
        f"- Всего: {stats['users'][0]}\n"
        f"- Забанено: {stats['users'][1]}\n"
        f"- Звёзд в обороте: {stats['users'][2]} ⭐\n"
        f"- Всего рефералов: {stats['users'][3]}\n\n"
        f"🏅 Ранги:\n"
    )

    for rank in stats['ranks']:
        rank_emoji = {
            'user': '👤',
            'moderator': '🛡',
            'admin': '⚜️',
            'owner': '👑',
            'developer': '⚡'
        }.get(rank[0], '❓')
        stats_text += f"- {rank_emoji} {rank[0].title()}: {rank[1]}\n"

    stats_text += (
        f"\n📋 Задания:\n"
        f"- Всего создано: {stats['tasks'][0]}\n"
        f"- Активных: {stats['tasks'][1]}\n"
        f"- Сумма наград: {stats['tasks'][2]} ⭐\n\n"
        f"✅ Выполнения:\n"
        f"- Всего попыток: {stats['completed'][0]}\n"
        f"- Одобрено: {stats['completed'][1]}\n"
        f"- Отклонено: {stats['completed'][2]}\n\n"
        f"🎁 Промокоды:\n"
        f"- Всего создано: {stats['promos'][0]}\n"
        f"- Использований: {stats['promos'][1]}\n"
        f"- Выдано звёзд: {stats['promos'][2]} ⭐"
    )

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="📊 Экспорт в CSV",
        callback_data="export_stats"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_owner"
    ))

    await callback.message.edit_text(
        stats_text,
        reply_markup=builder.as_markup()
    )

# Отслеживание действий администраторов
@dp.callback_query(F.data == "owner_actions")
async def track_actions(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(
        text="👥 Действия модераторов",
        callback_data="view_mod_actions"
    ))
    builder.row(types.InlineKeyboardButton(
        text="⚜️ Действия админов",
        callback_data="view_admin_actions"
    ))
    builder.row(types.InlineKeyboardButton(
        text="📅 За последние 24 часа",
        callback_data="view_recent_actions"
    ))
    builder.row(types.InlineKeyboardButton(
        text="🔙 Назад",
        callback_data="back_to_owner"
    ))

    await callback.message.edit_text(
        "📋 Отслеживание действий\n"
        "Выберите категорию:",
        reply_markup=builder.as_markup()
    )

@dp.callback_query(F.data.startswith("view_"))
async def show_actions(callback: types.CallbackQuery):
    action_type = callback.data.split('_')[1]
    
    async with aiosqlite.connect(db.db_name) as conn:
        if action_type == "mod_actions":
            query = '''
                SELECT m.moderator_id, u.first_name, m.action_type, 
                       m.target_user_id, m.description, m.timestamp
                FROM moderator_actions m
                JOIN users u ON m.moderator_id = u.user_id
                ORDER BY m.timestamp DESC
                LIMIT 10
            '''
        elif action_type == "admin_actions":
            query = '''
                SELECT a.admin_id, u.first_name, a.action_type, 
                       a.target_user_id, a.description, a.timestamp
                FROM admin_actions a
                JOIN users u ON a.admin_id = u.user_id
                ORDER BY a.timestamp DESC
                LIMIT 10
            '''
        else:  # recent_actions
            query = '''
                SELECT 'Модератор' as role, moderator_id as user_id, 
                       action_type, target_user_id, description, timestamp
                FROM moderator_actions
                WHERE timestamp >= datetime('now', '-1 day')
                UNION ALL
                SELECT 'Админ' as role, admin_id as user_id, 
                       action_type, target_user_id, description, timestamp
                FROM admin_actions
                WHERE timestamp >= datetime('now', '-1 day')
                ORDER BY timestamp DESC
            '''

        async with conn.execute(query) as cursor:
            actions = await cursor.fetchall()

    if not actions:
        await callback.answer("Нет действий для отображения!", show_alert=True)
        return

    text = "📋 Последние действия:\n\n"
    for action in actions:
        text += (
            f"👤 {action[1]}\n"
            f"🔧 Действие: {action[2]}\n"
            f"🎯 Цель: {action[3]}\n"
            f"📝 Описание: {action[4]}\n"
            f"📅 Время: {action[5]}\n"
            f"{'─' * 20}\n"
        )

    # Разбиваем на части, если текст слишком длинный
    if len(text) > 4096:
        for x in range(0, len(text), 4096):
            chunk = text[x:x+4096]
            await callback.message.answer(chunk)
    else:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardBuilder().row(
                types.InlineKeyboardButton(
                    text="🔙 Назад",
                    callback_data="owner_actions"
                )
            ).as_markup()
        )
        
# Обработчик отмены любого действия
@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_any_action(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    
    if "owner" in callback.data:
        await callback.message.edit_text(
            "❌ Действие отменено",
            reply_markup=InlineKeyboardBuilder().row(
                types.InlineKeyboardButton(
                    text="🔙 В панель владельца",
                    callback_data="back_to_owner"
                )
            ).as_markup()
        )
    elif "admin" in callback.data:
        await callback.message.edit_text(
            "❌ Действие отменено",
            reply_markup=InlineKeyboardBuilder().row(
                types.InlineKeyboardButton(
                    text="🔙 В панель администратора",
                    callback_data="back_to_admin"
                )
            ).as_markup()
        )
    else:
        await callback.message.edit_text(
            "❌ Действие отменено",
            reply_markup=get_main_keyboard(await get_user_rank(callback.from_user.id))
        )

# Обработчики возврата в панели
@dp.callback_query(F.data == "back_to_owner")
async def back_to_owner_panel(callback: types.CallbackQuery):
    if not await is_owner(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    await owner_panel(callback.message)

@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin_panel(callback: types.CallbackQuery):
    if not await is_admin(callback.from_user.id):
        await callback.answer("❌ Доступ запрещён!", show_alert=True)
        return
    await admin_panel(callback.message)

# Обработчик неизвестных команд
@dp.message()
async def unknown_command(message: types.Message):
    await message.answer(
        "❌ Неизвестная команда!\n"
        "Используйте /help для просмотра доступных команд."
    )

async def init_db():
    await db.create_tables()
# Запуск бота
async def main():
    # Инициализация базы данных при запуске
    await init_db()
    
    # Логгирование запуска
    logger.info(f"Bot started at {datetime.datetime.now()} UTC")
    
    # Запуск бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
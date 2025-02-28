import asyncio
import logging
import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Union, Optional, Any, Awaitable, Callable
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.chat_action import ChatActionMiddleware
from aiogram.utils.markdown import hbold
from aiogram.exceptions import TelegramBadRequest
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiocryptopay import AioCryptoPay, Networks
import aiosqlite
import os

# Middleware for request throttling
class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float):
        self.rate_limit = rate_limit
        self.last_request = {}

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        current_time = time.time()

        if user_id in self.last_request:
            time_passed = current_time - self.last_request[user_id]
            if time_passed < self.rate_limit:
                return None

        self.last_request[user_id] = current_time
        return await handler(event, data)

# Constants
API_TOKEN = "7895118132:AAHgQMEduXkmSYReXlqhGsMAjtOcypZFaus"
CRYPTO_TOKEN = "310470:AAkZsC9GaIYp6sfhxOaWpr2Ic3lg11Af8Xo"
OWNER_ID = 6673580092
REQUIRED_CHANNEL_ID = -1002452807906
CHANNEL_LINK = "https://t.me/+l75xnD9ceRo0Nzky"
AGREEMENT_LINK = "https://telegra.ph/POLZOVATELSKOE-SOGLASHENIE-02-27-15"
ADMIN_AGREEMENT_LINK = "https://telegra.ph/ADMIN-SOGLASHENIE-02-27" # Добавлено

# Price constants
BALL_PRICES = {
    "1": 0.2,
    "10": 1.9,
    "100": 17
}

VIP_PRICES = {
    "7": 5,    # Week
    "30": 18,  # Month
    "365": 33, # Year
    "0": 49    # Permanent
}

SEARCH_COST = 0.05  # Cost per found item
REFERRAL_REWARD = 0.2  # Reward per referral
MAX_REFERRALS = 15  # Maximum referrals for regular users
VIP_MAX_REFERRALS = 50  # Maximum referrals for VIP users

# Initialize bot, dispatcher and crypto
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
crypto = AioCryptoPay(token=CRYPTO_TOKEN, network=Networks.MAIN_NET)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# States
class UserStates(StatesGroup):
    waiting_for_subscription_check = State()
    waiting_for_agreement = State()
    waiting_for_referral_code = State()
    waiting_for_referral_approval = State()
    waiting_for_search_type = State()
    waiting_for_search_input = State()
    waiting_for_report_id = State()
    waiting_for_report_data = State()
    waiting_for_report_data_input = State()
    waiting_for_admin_review = State()
    waiting_for_admin_verification = State()
    waiting_for_info_search = State()
    waiting_for_user_selection = State()
    waiting_for_admin_id = State()
    waiting_for_admin_reason = State()
    waiting_for_rejection_reason = State()
    waiting_for_delete_user = State()
    waiting_for_delete_confirm = State()
    waiting_for_info_user = State()
    waiting_for_info_type = State()
    waiting_for_info_value = State()
    waiting_for_delete_info_user = State()
    waiting_for_delete_info_type = State()
    waiting_for_referral_user = State()
    waiting_for_referral_count = State()
    waiting_for_referral_reason = State()
    waiting_for_vip_user = State()
    waiting_for_vip_duration = State()
    waiting_for_vip_reason = State()
    waiting_for_remove_vip_user = State()
    waiting_for_remove_vip_reason = State()
    waiting_for_fine_user = State()
    waiting_for_fine_amount = State()
    waiting_for_fine_reason = State()
    waiting_for_warn_admin = State()
    waiting_for_warn_reason = State()
    waiting_for_new_admin = State()
    waiting_for_admin_reason = State()
    waiting_for_remove_admin = State()
    waiting_for_remove_admin_reason = State()
    waiting_for_info_search = State()
    waiting_for_delete_info_type = State()
    waiting_for_delete_field = State()
    waiting_for_unban_user = State()
    waiting_for_ban_user = State()
    waiting_for_unban_reason = State()
    waiting_for_ban_duration = State()
    waiting_for_ban_reason = State()
    
async def init_db():
    """Initialize database tables"""
    async with aiosqlite.connect('bot_database.db') as db:
        # Create users table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                referral_code TEXT UNIQUE,
                balance REAL DEFAULT 0.0,
                is_vip BOOLEAN DEFAULT FALSE,
                vip_expiration DATETIME,
                is_banned BOOLEAN DEFAULT FALSE,
                ban_expiration DATETIME,
                agreement_accepted BOOLEAN DEFAULT FALSE,
                registration_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                referrals_count INTEGER DEFAULT 0,
                referral_balance REAL DEFAULT 0.0,
                warnings INTEGER DEFAULT 0
            )
        ''')

        # Create info_base table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS info_base (
                telegram_id INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                middle_name TEXT,
                birth_date TEXT,
                phone_number TEXT,
                address TEXT,
                workplace TEXT,
                social_networks TEXT,
                info_provider_id INTEGER,
                admin_approver_id INTEGER,
                info_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (info_provider_id) REFERENCES users (user_id),
                FOREIGN KEY (admin_approver_id) REFERENCES admins (admin_id)
            )
        ''')

        # Create admins table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                admin_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                warnings INTEGER DEFAULT 0,
                approved_count INTEGER DEFAULT 0,
                rejected_count INTEGER DEFAULT 0,
                registration_date DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create banned_users table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY,
                ban_reason TEXT,
                ban_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                ban_expiration DATETIME,
                user_data TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        # Create referrals table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                referral_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                referral_user_id INTEGER,
                referral_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (referral_user_id) REFERENCES users (user_id)
            )
        ''')

        # Create reports table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                target_user_id INTEGER,
                report_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                admin_id INTEGER,
                report_data TEXT,
                check_start_time DATETIME,
                decision_time DATETIME,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (admin_id) REFERENCES admins (admin_id)
            )
        ''')

        # Create action_logs table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS action_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action_type TEXT,
                action_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                action_details TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        # Create payments table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                currency TEXT,
                payment_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                payment_type TEXT,
                payment_status TEXT,
                invoice_id TEXT UNIQUE,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        # Create statistics table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_users INTEGER DEFAULT 0,
                total_admins INTEGER DEFAULT 0,
                total_payments REAL DEFAULT 0,
                total_referrals INTEGER DEFAULT 0,
                stat_date DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create admin_warnings table
        await db.execute('''
            CREATE TABLE IF NOT EXISTS admin_warnings (
                warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                warning_reason TEXT,
                warning_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (admin_id) REFERENCES admins (admin_id)
            )
        ''')

        await db.commit()
        logger.info("Database initialized successfully")

# Helper functions
async def is_admin(user_id: int) -> bool:
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT 1 FROM admins WHERE admin_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone() is not None

async def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

async def is_banned(user_id: int) -> bool:
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT ban_expiration FROM banned_users WHERE user_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
            if not result:
                return False
            if result[0] is None:  # Permanent ban
                return True
            ban_expiration = datetime.fromisoformat(result[0])
            return ban_expiration > datetime.now(timezone.utc)

async def get_user_balance(user_id: int) -> float:
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,)) as cursor:
            result = await cursor.fetchone()
            return float(result[0]) if result else 0.0
# Keyboard functions
def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="👤 Кабинет")],
            [KeyboardButton(text="📝 Донос")]
        ],
        resize_keyboard=True
    )

def get_admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика бота"), KeyboardButton(text="👥 Статистика админов")],
            [KeyboardButton(text="➕ Добавить админа"), KeyboardButton(text="➖ Снять админа")],
            [KeyboardButton(text="⚠️ Выдать варн"), KeyboardButton(text="📈 Недельная статистика")],
            [KeyboardButton(text="🎖 Выдать VIP"), KeyboardButton(text="🚫 Снять VIP")],
            [KeyboardButton(text="💰 Выдать баллы"), KeyboardButton(text="💸 Оштрафовать")],
            [KeyboardButton(text="🗑 Удалить пользователя"), KeyboardButton(text="🔒 Бан")],
            [KeyboardButton(text="🔓 Разбан"), KeyboardButton(text="👀 Кто донёс")],
            [KeyboardButton(text="❌ Удалить информацию"), KeyboardButton(text="➕ Добавить информацию")],
            [KeyboardButton(text="🔎 Просмотр информации"), KeyboardButton(text="📊 Начисление рефералов")],
            [KeyboardButton(text="↩️ Обычное меню")]
        ],
        resize_keyboard=True
    )

async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

async def generate_unique_referral_code() -> str:
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        async with aiosqlite.connect('bot_database.db') as db:
            async with db.execute('SELECT 1 FROM users WHERE referral_code = ?', (code,)) as cursor:
                if not await cursor.fetchone():
                    return code

async def log_action(user_id: int, action_type: str, details: dict):
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute(
            'INSERT INTO action_logs (user_id, action_type, action_details) VALUES (?, ?, ?)',
            (user_id, action_type, json.dumps(details))
        )
        await db.commit()

# Start command handler
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Check if user is banned
    if await is_banned(user_id):
        return
    
    async with aiosqlite.connect('bot_database.db') as db:
        # Check if user exists
        async with db.execute('SELECT agreement_accepted FROM users WHERE user_id = ?', (user_id,)) as cursor:
            user = await cursor.fetchone()
            
        if not user:
            # Check channel subscription
            if not await check_subscription(user_id):
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_LINK)],
                        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subscription")]
                    ]
                )
                await message.answer(
                    "👋 Для использования бота необходимо подписаться на канал:",
                    reply_markup=keyboard
                )
                await state.set_state(UserStates.waiting_for_subscription_check)
                return
            
            # If owner, skip registration
            if await is_owner(user_id):
                await register_user(message.from_user, is_owner=True)
                await message.answer(
                    "👑 Добро пожаловать, владелец!",
                    reply_markup=get_main_menu_keyboard()
                )
                return
            
            # Show agreement
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📜 Прочитать соглашение", url=AGREEMENT_LINK)],
                    [
                        InlineKeyboardButton(text="✅ Принять", callback_data="accept_agreement"),
                        InlineKeyboardButton(text="❌ Отказаться", callback_data="decline_agreement")
                    ]
                ]
            )
            await message.answer(
                "📝 Пожалуйста, ознакомьтесь с пользовательским соглашением:",
                reply_markup=keyboard
            )
            await state.set_state(UserStates.waiting_for_agreement)
        else:
            # Existing user
            await message.answer(
                "👋 С возвращением!",
                reply_markup=get_main_menu_keyboard()
            )

async def register_user(user: types.User, is_owner: bool = False):
    async with aiosqlite.connect('bot_database.db') as db:
        referral_code = await generate_unique_referral_code()
        await db.execute('''
            INSERT INTO users (
                user_id, username, first_name, last_name,
                referral_code, is_vip, registration_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user.id, user.username, user.first_name, user.last_name,
            referral_code, is_owner, datetime.now(timezone.utc)
        ))
        await db.commit()

@dp.callback_query(F.data == "check_subscription")
async def callback_check_subscription(callback: CallbackQuery, state: FSMContext):
    if await check_subscription(callback.from_user.id):
        await callback.message.delete()
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📜 Прочитать соглашение", url=AGREEMENT_LINK)],
                [
                    InlineKeyboardButton(text="✅ Принять", callback_data="accept_agreement"),
                    InlineKeyboardButton(text="❌ Отказаться", callback_data="decline_agreement")
                ]
            ]
        )
        await callback.message.answer(
            "📝 Пожалуйста, ознакомьтесь с пользовательским соглашением:",
            reply_markup=keyboard
        )
        await state.set_state(UserStates.waiting_for_agreement)
    else:
        await callback.answer("❌ Вы не подписаны на канал!", show_alert=True)

@dp.callback_query(F.data == "accept_agreement")
async def callback_accept_agreement(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    async with aiosqlite.connect('bot_database.db') as db:
        # Check if user is owner
        if await is_owner(user_id):
            await register_user(callback.from_user, is_owner=True)
            await callback.message.edit_text(
                "👑 Добро пожаловать, владелец!",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        await callback.message.edit_text(
            "🔑 Пожалуйста, введите код приглашения:",
            reply_markup=None
        )
        await state.set_state(UserStates.waiting_for_referral_code)

@dp.callback_query(F.data == "decline_agreement")
async def callback_decline_agreement(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('''
            INSERT INTO banned_users (user_id, ban_reason, ban_expiration)
            VALUES (?, ?, NULL)
        ''', (user_id, "Отказ от пользовательского соглашения"))
        await db.commit()
    
    await callback.message.edit_text(
        "🚫 Вы отказались от пользовательского соглашения. Доступ к боту заблокирован."
    )
    await state.clear()
# Referral system handlers
@dp.message(UserStates.waiting_for_referral_code)
async def process_referral_code(message: Message, state: FSMContext):
    user_id = message.from_user.id
    referral_code = message.text.strip()
    
    async with aiosqlite.connect('bot_database.db') as db:
        # Check if code exists
        async with db.execute(
            'SELECT user_id, referrals_count FROM users WHERE referral_code = ?',
            (referral_code,)
        ) as cursor:
            referrer = await cursor.fetchone()
            
        if not referrer:
            await message.answer("❌ Неверный код приглашения. Попробуйте еще раз:")
            # Check attempts count
            attempts = (await state.get_data()).get('attempts', 0) + 1
            if attempts >= 3:
                await db.execute('''
                    INSERT INTO banned_users (user_id, ban_reason, ban_expiration)
                    VALUES (?, ?, NULL)
                ''', (user_id, "Превышено количество попыток ввода кода приглашения"))
                await db.commit()
                
                await message.answer("🚫 Превышено количество попыток. Вы заблокированы.")
                await state.clear()
                return
            
            await state.update_data(attempts=attempts)
            return
        
        referrer_id, referrals_count = referrer
        
        # Check referrals limit
        async with db.execute(
            'SELECT is_vip FROM users WHERE user_id = ?',
            (referrer_id,)
        ) as cursor:
            is_vip = (await cursor.fetchone())[0]
        
        max_refs = (VIP_MAX_REFERRALS if is_vip else MAX_REFERRALS)
        if referrer_id != OWNER_ID and referrals_count >= max_refs:
            await message.answer("❌ Этот код уже использован максимальное количество раз. Попробуйте другой код:")
            return
        
        # Send approval request to referrer
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_ref_{user_id}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_ref_{user_id}")
                ]
            ]
        )
        
        await bot.send_message(
            referrer_id,
            f"👤 Пользователь {message.from_user.full_name} хочет зарегистрироваться по вашему коду.",
            reply_markup=keyboard
        )
        
        await message.answer("⏳ Ожидайте подтверждения от владельца кода...")
        await state.update_data(referrer_id=referrer_id)
        await state.set_state(UserStates.waiting_for_referral_approval)

@dp.callback_query(F.data.startswith("approve_ref_"))
async def approve_referral(callback: CallbackQuery, state: FSMContext):
    referral_id = int(callback.data.split("_")[2])
    referrer_id = callback.from_user.id
    
    async with aiosqlite.connect('bot_database.db') as db:
        # Register new user
        await register_user(await bot.get_user(referral_id))
        
        # Update referrer stats
        await db.execute('''
            UPDATE users 
            SET referrals_count = referrals_count + 1,
                balance = balance + ?
            WHERE user_id = ?
        ''', (REFERRAL_REWARD, referrer_id))
        
        # Add referral record
        await db.execute('''
            INSERT INTO referrals (user_id, referral_user_id)
            VALUES (?, ?)
        ''', (referrer_id, referral_id))
        
        await db.commit()
    
    await callback.message.edit_text("✅ Вы одобрили регистрацию пользователя.")
    await bot.send_message(
        referral_id,
        "🎉 Ваша регистрация одобрена! Добро пожаловать!",
        reply_markup=get_main_menu_keyboard()
    )

@dp.callback_query(F.data.startswith("decline_ref_"))
async def decline_referral(callback: CallbackQuery, state: FSMContext):
    referral_id = int(callback.data.split("_")[2])
    
    await callback.message.edit_text("❌ Вы отклонили регистрацию пользователя.")
    await bot.send_message(
        referral_id,
        "❌ Ваша регистрация отклонена. Попробуйте другой код приглашения:",
    )

# Search system
@dp.message(F.text == "🔍 Поиск")
async def search_menu(message: Message, state: FSMContext):
    if await is_banned(message.from_user.id):
        return
        
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📱 По номеру", callback_data="search_by_phone"),
                InlineKeyboardButton(text="🆔 По ID", callback_data="search_by_id")
            ],
            [InlineKeyboardButton(text="↩️ В меню", callback_data="back_to_menu")]
        ]
    )
    
    await message.answer(
        "🔍 Выберите тип поиска:",
        reply_markup=keyboard
    )
    await state.set_state(UserStates.waiting_for_search_type)

@dp.callback_query(F.data.startswith("search_by_"))
async def process_search_type(callback: CallbackQuery, state: FSMContext):
    search_type = callback.data.split("_")[2]
    
    await state.update_data(search_type=search_type)
    await state.set_state(UserStates.waiting_for_search_input)
    
    prompt = "📱 Введите номер телефона:" if search_type == "phone" else "🆔 Введите ID пользователя:"
    
    await callback.message.edit_text(prompt)

@dp.message(UserStates.waiting_for_search_input)
async def process_search(message: Message, state: FSMContext):
    user_data = await state.get_data()
    search_type = user_data['search_type']
    search_value = message.text.strip()
    
    # Validate input
    if search_type == "phone":
        if not re.match(r'^\+?\d{10,15}$', search_value):
            await message.answer("❌ Неверный формат номера. Попробуйте еще раз:")
            return
    else:  # id
        if not search_value.isdigit() or len(search_value) < 9:
            await message.answer("❌ Неверный формат ID. ID должен содержать минимум 9 цифр:")
            return
    
    async with aiosqlite.connect('bot_database.db') as db:
        if search_type == "phone":
            query = 'SELECT * FROM info_base WHERE phone_number = ?'
        else:
            query = 'SELECT * FROM info_base WHERE telegram_id = ?'
        
        async with db.execute(query, (search_value,)) as cursor:
            result = await cursor.fetchone()
        
        # Check if user is VIP
        async with db.execute(
            'SELECT is_vip FROM users WHERE user_id = ?',
            (message.from_user.id,)
        ) as cursor:
            is_vip = (await cursor.fetchone())[0]
    
    # Prepare search results
    fields = {
        "Имя": result[1] if result else None,
        "Фамилия": result[2] if result else None,
        "Отчество": result[3] if result else None,
        "Год или дата рождения": result[4] if result else None,
        "Номер": result[5] if result else None,
        "Место жительства": result[6] if result else None,
        "Место работы": result[7] if result else None,
        "Сети": result[8] if result else None
    }
    
    found_count = sum(1 for value in fields.values() if value is not None)
    if found_count == 0:
        await message.answer(
            "❌ Информация не найдена.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="↩️ В меню", callback_data="back_to_menu")]]
            )
        )
        return
    
    # Prepare results message
    results = "\n".join(
        f"{key}: {'найдено' if value else 'не найдено'}"
        for key, value in fields.items()
    )
    
    cost = found_count * SEARCH_COST
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👑 VIP", callback_data="show_vip_results")] if is_vip else
            [InlineKeyboardButton(text="💰 Оплатить баллами", callback_data="pay_search_results")],
            [InlineKeyboardButton(text="↩️ В меню", callback_data="back_to_menu")]
        ]
    )
    
    await state.update_data(
        search_results=fields,
        search_cost=cost
    )
    
    await message.answer(
        f"{results}\n\n💰 Стоимость: {cost} баллов",
        reply_markup=keyboard
    )
# Payment and VIP system handlers
@dp.callback_query(F.data == "show_vip_results")
async def show_vip_results(callback: CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    search_results = user_data.get('search_results', {})
    
    results = "\n".join(
        f"{key}: {value if value else 'не найдено'}"
        for key, value in search_results.items()
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ В меню", callback_data="back_to_menu")]]
    )
    
    await callback.message.edit_text(
        f"🔍 Результаты поиска:\n\n{results}",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "pay_search_results")
async def pay_for_results(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    cost = user_data.get('search_cost', 0)
    
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute(
            'SELECT balance FROM users WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            if not result or result[0] < cost:
                await callback.answer("❌ Недостаточно баллов на балансе!", show_alert=True)
                return
            
            # Deduct balance
            await db.execute(
                'UPDATE users SET balance = balance - ? WHERE user_id = ?',
                (cost, user_id)
            )
            await db.commit()
    
    search_results = user_data.get('search_results', {})
    results = "\n".join(
        f"{key}: {value if value else 'не найдено'}"
        for key, value in search_results.items()
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ В меню", callback_data="back_to_menu")]]
    )
    
    await callback.message.edit_text(
        f"🔍 Результаты поиска:\n\n{results}\n\n💰 Списано: {cost} баллов",
        reply_markup=keyboard
    )

@dp.message(F.text == "👤 Кабинет")
async def profile_menu(message: Message):
    if await is_banned(message.from_user.id):
        return
    
    user_id = message.from_user.id
    
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('''
            SELECT balance, is_vip, vip_expiration, referral_code, referrals_count
            FROM users WHERE user_id = ?
        ''', (user_id,)) as cursor:
            result = await cursor.fetchone()
            
        if not result:
            await message.answer("❌ Ошибка получения данных профиля")
            return
        
        balance, is_vip, vip_expiration, referral_code, referrals_count = result
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💰 Купить баллы", callback_data="buy_balance")],
                [InlineKeyboardButton(text="👑 Купить VIP", callback_data="buy_vip")],
                [InlineKeyboardButton(text="↩️ В меню", callback_data="back_to_menu")]
            ]
        )
        
        vip_status = "Активен" if is_vip else "Неактивен"
        if is_vip and vip_expiration:
            vip_expiry = datetime.fromisoformat(vip_expiration)
            if vip_expiry > datetime.now(timezone.utc):
                vip_status += f" (до {vip_expiry.strftime('%d.%m.%Y')})"
        
        await message.answer(
            f"👤 Профиль\n\n"
            f"💰 Баланс: {balance} баллов\n"
            f"👑 VIP статус: {vip_status}\n"
            f"🔑 Реферальный код: {referral_code}\n"
            f"👥 Рефералов: {referrals_count}\n",
            reply_markup=keyboard
        )

@dp.callback_query(F.data == "buy_balance")
async def buy_balance_menu(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1 балл = 0.2$", callback_data="buy_balance_1")],
            [InlineKeyboardButton(text="10 баллов = 1.9$", callback_data="buy_balance_10")],
            [InlineKeyboardButton(text="100 баллов = 17$", callback_data="buy_balance_100")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_profile")]
        ]
    )
    
    await callback.message.edit_text(
        "💰 Выберите количество баллов для покупки:",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("buy_balance_"))
async def process_balance_purchase(callback: CallbackQuery):
    amount = int(callback.data.split("_")[2])
    price = BALL_PRICES[str(amount)]
    
    try:
        invoice = await crypto.create_invoice(
            amount=price,
            currency_type='fiat',
            fiat='USD'
        )
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=invoice.bot_invoice_url)],
                [InlineKeyboardButton(text="↩️ Отмена", callback_data="back_to_profile")]
            ]
        )
        
        await callback.message.edit_text(
            f"💰 Покупка {amount} баллов\n"
            f"💵 Сумма к оплате: {price}$\n\n"
            f"⏳ Счет действителен 30 минут",
            reply_markup=keyboard
        )
        
        # Save invoice data
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('''
                INSERT INTO payments (
                    user_id, amount, currency, payment_type, payment_status, invoice_id
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                callback.from_user.id, amount, 'USD', 'balance',
                'pending', invoice.invoice_id
            ))
            await db.commit()
            
    except Exception as e:
        logger.error(f"Error creating invoice: {e}")
        await callback.answer("❌ Ошибка создания счета. Попробуйте позже.", show_alert=True)

@dp.callback_query(F.data == "buy_vip")
async def buy_vip_menu(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Неделя = 5$", callback_data="buy_vip_7")],
            [InlineKeyboardButton(text="Месяц = 18$", callback_data="buy_vip_30")],
            [InlineKeyboardButton(text="Год = 33$", callback_data="buy_vip_365")],
            [InlineKeyboardButton(text="Навсегда = 49$", callback_data="buy_vip_0")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_profile")]
        ]
    )
    
    await callback.message.edit_text(
        "👑 Выберите длительность VIP статуса:",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("buy_vip_"))
async def process_vip_purchase(callback: CallbackQuery):
    days = int(callback.data.split("_")[2])
    price = VIP_PRICES[str(days)]
    
    try:
        invoice = await crypto.create_invoice(
            amount=price,
            currency_type='fiat',
            fiat='USD'
        )
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=invoice.bot_invoice_url)],
                [InlineKeyboardButton(text="↩️ Отмена", callback_data="back_to_profile")]
            ]
        )
        
        vip_duration = "навсегда" if days == 0 else f"на {days} дней"
        
        await callback.message.edit_text(
            f"👑 Покупка VIP статуса {vip_duration}\n"
            f"💵 Сумма к оплате: {price}$\n\n"
            f"⏳ Счет действителен 30 минут",
            reply_markup=keyboard
        )
        
        # Save invoice data
        async with aiosqlite.connect('bot_database.db') as db:
            await db.execute('''
                INSERT INTO payments (
                    user_id, amount, currency, payment_type, payment_status,
                    invoice_id, vip_duration
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                callback.from_user.id, price, 'USD', 'vip',
                'pending', invoice.invoice_id, days
            ))
            await db.commit()
            
    except Exception as e:
        logger.error(f"Error creating invoice: {e}")
        await callback.answer("❌ Ошибка создания счета. Попробуйте позже.", show_alert=True)

# Payment processing
async def check_payments():
    while True:
        try:
            async with aiosqlite.connect('bot_database.db') as db:
                async with db.execute('''
                    SELECT user_id, invoice_id, payment_type, amount, vip_duration
                    FROM payments 
                    WHERE payment_status = 'pending'
                ''') as cursor:
                    pending_payments = await cursor.fetchall()
                
                for payment in pending_payments:
                    user_id, invoice_id, payment_type, amount, vip_duration = payment
                    
                    try:
                        invoice = await crypto.get_invoices(invoice_ids=invoice_id)
                        
                        if invoice and invoice.status == 'paid':
                            if payment_type == 'balance':
                                await db.execute('''
                                    UPDATE users 
                                    SET balance = balance + ?
                                    WHERE user_id = ?
                                ''', (amount, user_id))
                                
                                await bot.send_message(
                                    user_id,
                                    f"✅ Ваш баланс пополнен на {amount} баллов!"
                                )
                                
                            elif payment_type == 'vip':
                                if vip_duration == 0:
                                    expiration = None
                                else:
                                    expiration = datetime.now(timezone.utc) + timedelta(days=vip_duration)
                                
                                await db.execute('''
                                    UPDATE users 
                                    SET is_vip = TRUE,
                                        vip_expiration = ?
                                    WHERE user_id = ?
                                ''', (expiration, user_id))
                                
                                duration_text = "навсегда" if vip_duration == 0 else f"на {vip_duration} дней"
                                await bot.send_message(
                                    user_id,
                                    f"✅ VIP статус активирован {duration_text}!"
                                )
                            
                            await db.execute('''
                                UPDATE payments 
                                SET payment_status = 'completed'
                                WHERE invoice_id = ?
                            ''', (invoice_id,))
                            
                            await log_action(
                                user_id,
                                f"payment_{payment_type}",
                                {"amount": amount, "invoice_id": invoice_id}
                            )
                            
                    except Exception as e:
                        logger.error(f"Error checking payment {invoice_id}: {e}")
                
                await db.commit()
                
        except Exception as e:
            logger.error(f"Error in payment checker: {e}")
            
        await asyncio.sleep(60)  # Check every minute
# Admin panel and report system
@dp.message(Command("owenu"))
async def admin_menu(message: Message):
    if not await is_owner(message.from_user.id):
        return
    
    await message.answer(
        "👑 Панель управления",
        reply_markup=get_admin_keyboard()
    )

@dp.message(F.text == "📝 Донос")
async def report_menu(message: Message, state: FSMContext):
    if await is_banned(message.from_user.id):
        return
    
    await message.answer("👤 Введите ID пользователя для доноса:")
    await state.set_state(UserStates.waiting_for_report_id)

@dp.message(UserStates.waiting_for_report_id)
async def process_report_id(message: Message, state: FSMContext):
    target_id = message.text.strip()
    
    # Validate Telegram ID format
    if not target_id.isdigit() or len(target_id) < 9:
        await message.answer("❌ Неверный формат ID. ID должен содержать минимум 9 цифр.")
        return
    
    target_id = int(target_id)
    
    async with aiosqlite.connect('bot_database.db') as db:
        # Check if info already exists
        async with db.execute(
            'SELECT * FROM info_base WHERE telegram_id = ?',
            (target_id,)
        ) as cursor:
            existing_info = await cursor.fetchone()
        
        # Create keyboard with available fields
        buttons = []
        if not existing_info or existing_info[1] is None:  # first_name
            buttons.append([KeyboardButton(text="👤 Имя")])
        if not existing_info or existing_info[2] is None:  # last_name
            buttons.append([KeyboardButton(text="👥 Фамилия")])
        if not existing_info or existing_info[3] is None:  # middle_name
            buttons.append([KeyboardButton(text="👤 Отчество")])
        if not existing_info or existing_info[4] is None:  # birth_date
            buttons.append([KeyboardButton(text="📅 Возраст")])
        if not existing_info or existing_info[5] is None:  # phone_number
            buttons.append([KeyboardButton(text="📱 Номер")])
        if not existing_info or existing_info[6] is None:  # address
            buttons.append([KeyboardButton(text="🏠 Место жительства")])
        if not existing_info or existing_info[7] is None:  # workplace
            buttons.append([KeyboardButton(text="💼 Место работы")])
        if not existing_info or existing_info[8] is None:  # social_networks
            buttons.append([KeyboardButton(text="🌐 Сети")])
        
        buttons.append([KeyboardButton(text="↩️ В меню")])
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=buttons,
            resize_keyboard=True
        )
        
        if not buttons[:-1]:  # If no fields available (except "Back to menu")
            await message.answer(
                "ℹ️ Для данного пользователя уже собрана вся информация.",
                reply_markup=get_main_menu_keyboard()
            )
            await state.clear()
            return
        
        await state.update_data(target_id=target_id)
        await message.answer(
            "✍️ Выберите тип информации для доноса:",
            reply_markup=keyboard
        )
        await state.set_state(UserStates.waiting_for_report_data)

@dp.message(UserStates.waiting_for_report_data)
async def process_report_data(message: Message, state: FSMContext):
    if message.text == "↩️ В меню":
        await message.answer(
            "↩️ Возвращаемся в меню",
            reply_markup=get_main_menu_keyboard()
        )
        await state.clear()
        return
    
    user_data = await state.get_data()
    target_id = user_data['target_id']
    
    field_mapping = {
        "👤 Имя": "first_name",
        "👥 Фамилия": "last_name",
        "👤 Отчество": "middle_name",
        "📅 Возраст": "birth_date",
        "📱 Номер": "phone_number",
        "🏠 Место жительства": "address",
        "💼 Место работы": "workplace",
        "🌐 Сети": "social_networks"
    }
    
    if message.text not in field_mapping:
        await message.answer("❌ Неверный выбор. Пожалуйста, используйте клавиатуру.")
        return
    
    field = field_mapping[message.text]
    await state.update_data(report_field=field)
    
    await message.answer(
        "✍️ Введите информацию:",
        reply_markup=get_main_menu_keyboard()
    )
    await state.set_state(UserStates.waiting_for_report_data_input)

@dp.message(UserStates.waiting_for_report_data_input)
async def process_report_data_input(message: Message, state: FSMContext):
    user_data = await state.get_data()
    target_id = user_data['target_id']
    field = user_data['report_field']
    
    # Validate input based on field type
    if field == "phone_number" and not re.match(r'^\+?\d{10,15}$', message.text):
        await message.answer("❌ Неверный формат номера телефона. Попробуйте еще раз:")
        return
    
    if field == "birth_date":
        try:
            # Try to parse date in different formats
            for fmt in ('%d.%m.%Y', '%Y', '%d-%m-%Y'):
                try:
                    datetime.strptime(message.text, fmt)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError("Invalid date format")
        except ValueError:
            await message.answer(
                "❌ Неверный формат даты. Используйте форматы:\n"
                "- ДД.ММ.ГГГГ\n"
                "- ГГГГ\n"
                "- ДД-ММ-ГГГГ"
            )
            return
    
    async with aiosqlite.connect('bot_database.db') as db:
        # Check for duplicate reports
        async with db.execute('''
            SELECT report_data FROM reports 
            WHERE user_id = ? AND target_user_id = ? 
            AND status = 'pending'
        ''', (message.from_user.id, target_id)) as cursor:
            if await cursor.fetchone():
                await message.answer("❌ У вас уже есть активная заявка на проверку.")
                await state.clear()
                return
        
        # Get random admin
        async with db.execute(
            'SELECT admin_id FROM admins WHERE warnings < 3 ORDER BY RANDOM() LIMIT 1'
        ) as cursor:
            admin = await cursor.fetchone()
            
        if not admin:
            await message.answer(
                "⏳ В данный момент нет свободных администраторов. Попробуйте позже."
            )
            await state.clear()
            return
        
        admin_id = admin[0]
        
        # Create report
        report_data = {
            "field": field,
            "value": message.text
        }
        
        await db.execute('''
            INSERT INTO reports (
                user_id, target_user_id, admin_id, 
                report_data, status
            ) VALUES (?, ?, ?, ?, ?)
        ''', (
            message.from_user.id, target_id, admin_id,
            json.dumps(report_data), 'pending'
        ))
        
        await db.commit()
    
    # Notify admin
    admin_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Начать проверку", callback_data=f"start_check_{target_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_report_{target_id}")
            ]
        ]
    )
    
    await bot.send_message(
        admin_id,
        f"📝 Новый донос\n\n"
        f"От: {message.from_user.full_name} ({message.from_user.id})\n"
        f"На: {target_id}\n"
        f"Поле: {message.text}\n"
        f"Значение: {message.text}\n\n"
        f"⚠️ У вас есть 5 часов на принятие решения.",
        reply_markup=admin_keyboard
    )
    
    await message.answer(
        "✅ Ваш донос отправлен на проверку администратору.\n"
        "Вы получите уведомление о результате проверки."
    )
    await state.clear()

@dp.callback_query(F.data.startswith("start_check_"))
async def start_report_check(callback: CallbackQuery):
    target_id = int(callback.data.split("_")[2])
    admin_id = callback.from_user.id
    
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('''
            UPDATE reports 
            SET status = 'checking',
                check_start_time = CURRENT_TIMESTAMP
            WHERE target_user_id = ? AND admin_id = ? AND status = 'pending'
        ''', (target_id, admin_id))
        
        # Get reporter id
        async with db.execute(
            'SELECT user_id FROM reports WHERE target_user_id = ? AND admin_id = ?',
            (target_id, admin_id)
        ) as cursor:
            reporter_id = (await cursor.fetchone())[0]
        
        await db.commit()
    
    await bot.send_message(
        reporter_id,
        "ℹ️ Администратор начал проверку вашего доноса.\n"
        "Результат будет известен в течение 24 часов."
    )
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"approve_report_{target_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_report_{target_id}")
            ]
        ]
    )
    
    await callback.message.edit_text(
        f"🔍 Проверка доноса началась\n"
        f"⏳ У вас есть 24 часа на проверку информации.",
        reply_markup=keyboard
    )
# Admin report decisions and additional functions
@dp.callback_query(F.data.startswith(("approve_report_", "reject_report_")))
async def process_report_decision(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[0]
    target_id = int(callback.data.split("_")[2])
    admin_id = callback.from_user.id
    
    async with aiosqlite.connect('bot_database.db') as db:
        # Get report details
        async with db.execute('''
            SELECT user_id, report_data, check_start_time
            FROM reports 
            WHERE target_user_id = ? AND admin_id = ? AND status = 'checking'
        ''', (target_id, admin_id)) as cursor:
            report = await cursor.fetchone()
            
        if not report:
            await callback.answer("❌ Донос не найден или уже обработан", show_alert=True)
            return
            
        reporter_id, report_data, check_start_time = report
        report_data = json.loads(report_data)
        
        # Check 24-hour limit
        check_start = datetime.fromisoformat(check_start_time)
        if datetime.now(timezone.utc) - check_start > timedelta(hours=24):
            # Add warning to admin
            await db.execute('''
                UPDATE admins 
                SET warnings = warnings + 3
                WHERE admin_id = ?
            ''', (admin_id,))
            
            # Check if admin should be removed
            async with db.execute(
                'SELECT warnings FROM admins WHERE admin_id = ?',
                (admin_id,)
            ) as cursor:
                warnings = (await cursor.fetchone())[0]
                
            if warnings >= 3:
                await remove_admin(admin_id, "Превышение времени проверки доноса")
                await callback.message.edit_text("❌ Вы были сняты с должности администратора.")
                return
            
            await callback.answer("❌ Превышен лимит времени на проверку", show_alert=True)
            return
        
        if action == "approve":
            # Update info_base
            field = report_data['field']
            value = report_data['value']
            
            # Check for duplicate information
            async with db.execute(f'''
                SELECT {field} FROM info_base WHERE telegram_id = ?
            ''', (target_id,)) as cursor:
                existing = await cursor.fetchone()
                
            if not existing:
                # Create new record
                fields = ['telegram_id', field, 'info_provider_id', 'admin_approver_id']
                values = [target_id, value, reporter_id, admin_id]
                await db.execute(f'''
                    INSERT INTO info_base ({', '.join(fields)})
                    VALUES ({', '.join(['?' for _ in fields])})
                ''', values)
            else:
                # Update existing record
                await db.execute(f'''
                    UPDATE info_base 
                    SET {field} = ?,
                        info_provider_id = ?,
                        admin_approver_id = ?
                    WHERE telegram_id = ?
                ''', (value, reporter_id, admin_id, target_id))
            
            # Add balance to reporter
            await db.execute('''
                UPDATE users 
                SET balance = balance + 0.1
                WHERE user_id = ?
            ''', (reporter_id,))
            
            await bot.send_message(
                reporter_id,
                "✅ Ваш донос был подтвержден администратором!\n"
                "💰 На ваш баланс начислено 0.1 балла."
            )
            
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text="📸 Отправить отчет",
                        callback_data=f"send_report_{target_id}"
                    )
                ]]
            )
            
            await callback.message.edit_text(
                "✅ Донос подтвержден. Пожалуйста, отправьте отчет владельцу.",
                reply_markup=keyboard
            )
            
        else:  # reject
            await state.set_state("waiting_for_rejection_reason")
            await state.update_data(
                target_id=target_id,
                reporter_id=reporter_id
            )
            
            await callback.message.edit_text(
                "📝 Укажите причину отклонения доноса:"
            )
        
        await db.execute('''
            UPDATE reports 
            SET status = ?,
                decision_time = CURRENT_TIMESTAMP
            WHERE target_user_id = ? AND admin_id = ?
        ''', ('approved' if action == 'approve' else 'rejected', target_id, admin_id))
        
        # Update admin statistics
        await db.execute('''
            UPDATE admins 
            SET {} = {} + 1
            WHERE admin_id = ?
        '''.format(
            'approved_count' if action == 'approve' else 'rejected_count',
            'approved_count' if action == 'approve' else 'rejected_count'
        ), (admin_id,))
        
        await db.commit()

@dp.message(F.text == "📊 Статистика бота")
async def show_bot_statistics(message: Message):
    if not await is_owner(message.from_user.id):
        return
        
    async with aiosqlite.connect('bot_database.db') as db:
        # Общая статистика пользователей
        async with db.execute('''
            SELECT 
                COUNT(*) as total_users,
                SUM(CASE WHEN is_vip = 1 THEN 1 ELSE 0 END) as vip_users,
                SUM(balance) as total_balance,
                SUM(referrals_count) as total_referrals
            FROM users
        ''') as cursor:
            users_stats = await cursor.fetchone()
        
        # Статистика админов
        async with db.execute('''
            SELECT 
                COUNT(*) as total_admins,
                SUM(approved_count) as total_approved,
                SUM(rejected_count) as total_rejected
            FROM admins
        ''') as cursor:
            admin_stats = await cursor.fetchone()
            
        # Статистика платежей
        async with db.execute('''
            SELECT 
                COUNT(*) as total_transactions,
                SUM(CASE WHEN payment_type = 'balance' THEN amount ELSE 0 END) as balance_payments,
                SUM(CASE WHEN payment_type = 'vip' THEN amount ELSE 0 END) as vip_payments
            FROM payments
            WHERE payment_status = 'completed'
        ''') as cursor:
            payment_stats = await cursor.fetchone()
            
        # Статистика информационной базы
        async with db.execute('''
            SELECT 
                COUNT(DISTINCT telegram_id) as total_entries,
                COUNT(first_name) + COUNT(last_name) + COUNT(middle_name) +
                COUNT(birth_date) + COUNT(phone_number) + COUNT(address) +
                COUNT(workplace) + COUNT(social_networks) as total_fields
            FROM info_base
        ''') as cursor:
            info_stats = await cursor.fetchone()
            
        # Статистика банов
        async with db.execute('''
            SELECT 
                COUNT(*) as total_bans,
                SUM(CASE WHEN ban_expiration IS NULL THEN 1 ELSE 0 END) as permanent_bans
            FROM banned_users
        ''') as cursor:
            ban_stats = await cursor.fetchone()
            
        # Размер базы данных
        db_size = os.path.getsize('bot_database.db') / (1024 * 1024)  # В МБ
        
        stats_text = (
            "📊 СТАТИСТИКА БОТА\n\n"
            f"👥 Пользователи:\n"
            f"├ Всего: {users_stats[0]}\n"
            f"├ VIP: {users_stats[1]}\n"
            f"├ Общий баланс: {users_stats[2]:.2f} баллов\n"
            f"└ Рефералов: {users_stats[3]}\n\n"
            
            f"👮 Администраторы:\n"
            f"├ Всего: {admin_stats[0]}\n"
            f"├ Одобрено: {admin_stats[1]}\n"
            f"└ Отклонено: {admin_stats[2]}\n\n"
            
            f"💰 Платежи:\n"
            f"├ Всего транзакций: {payment_stats[0]}\n"
            f"├ За баллы: ${payment_stats[1]:.2f}\n"
            f"└ За VIP: ${payment_stats[2]:.2f}\n\n"
            
            f"📁 Информационная база:\n"
            f"├ Всего записей: {info_stats[0]}\n"
            f"└ Всего полей: {info_stats[1]}\n\n"
            
            f"🚫 Баны:\n"
            f"├ Всего: {ban_stats[0]}\n"
            f"└ Вечных: {ban_stats[1]}\n\n"
            
            f"💾 Размер базы: {db_size:.2f} МБ\n"
            f"📅 Дата запуска: {BOT_START_DATE}\n"
            f"⏰ Аптайм: {(datetime.now() - datetime.fromisoformat(BOT_START_DATE)).days} дней"
        )
        
        await message.answer(stats_text, reply_markup=get_admin_keyboard())
        
        
@dp.message(F.text == "👥 Статистика админов")
async def show_admin_statistics(message: Message):
    if not await is_owner(message.from_user.id):
        return
    
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('''
            SELECT 
                username,
                first_name,
                last_name,
                approved_count,
                rejected_count,
                warnings,
                registration_date,
                (approved_count + rejected_count) as total_reports
            FROM admins
            ORDER BY total_reports DESC
        ''') as cursor:
            admins = await cursor.fetchall()
            
        if not admins:
            await message.answer(
                "ℹ️ Нет активных администраторов.",
                reply_markup=get_admin_keyboard()
            )
            return
            
        stats_text = "👥 Статистика администраторов:\n\n"
        
        for i, admin in enumerate(admins, 1):
            username, first_name, last_name, approved, rejected, warnings, reg_date, total = admin
            reg_date = datetime.fromisoformat(reg_date).strftime("%d.%m.%Y")
            
            stats_text += (
                f"{i}. {first_name} {last_name} (@{username})\n"
                f"✅ Одобрено: {approved}\n"
                f"❌ Отклонено: {rejected}\n"
                f"⚠️ Предупреждения: {warnings}/3\n"
                f"📅 На посту с: {reg_date}\n"
                f"📊 Рейтинг эффективности: {(approved/(total or 1))*100:.1f}%\n\n"
            )
        
        async def remove_admin(admin_id: int, reason: str):
          try:
          	await bot.delete_chat_history(admin_id)
          	await bot.leave_chat(admin_id)
          except Exception as e:
              logger.error(f"Error cleaning admin chat: {e}")
    
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('DELETE FROM admins WHERE admin_id = ?', (admin_id,))
        await db.commit()
        
    await log_action(
        OWNER_ID,
        "admin_removed",
        {"admin_id": admin_id, "reason": reason}
    )

@dp.message(F.text == "➕ Добавить админа")
async def add_admin_start(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer(
        "👤 Введите ID нового администратора:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_new_admin)

@dp.message(UserStates.waiting_for_new_admin)
async def process_new_admin(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    if not message.text.isdigit() or len(message.text) < 9:
        await message.answer("❌ Неверный формат ID. ID должен содержать минимум 9 цифр.")
        return
        
    user_id = int(message.text)
    
    # Проверяем, не является ли пользователь уже админом
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute(
            'SELECT 1 FROM admins WHERE admin_id = ?',
            (user_id,)
        ) as cursor:
            if await cursor.fetchone():
                await message.answer("❌ Этот пользователь уже является администратором.")
                await state.clear()
                return
                
        # Проверяем существование пользователя в базе
        async with db.execute(
            'SELECT username, first_name, last_name FROM users WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            user = await cursor.fetchone()
            
        if not user:
            await message.answer("❌ Пользователь не найден в базе данных.")
            await state.clear()
            return
            
    await state.update_data(
        new_admin_id=user_id,
        new_admin_info=f"@{user[0] or ''} ({user[1] or ''} {user[2] or ''})"
    )
    await message.answer("📝 Введите причину назначения:")
    await state.set_state(UserStates.waiting_for_admin_reason)

@dp.message(UserStates.waiting_for_admin_reason)
async def process_admin_reason(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    user_data = await state.get_data()
    new_admin_id = user_data['new_admin_id']
    admin_info = user_data['new_admin_info']
    reason = message.text
    
    # Отправляем пользователю предложение стать админом
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Принять", callback_data=f"accept_admin_{new_admin_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_admin_{new_admin_id}")
            ]
        ]
    )
    
    admin_agreement = (
        "📜 СОГЛАШЕНИЕ АДМИНИСТРАТОРА\n\n"
        "Принимая эту должность, вы соглашаетесь:\n"
        "1. Проверять все доносы в течение 24 часов\n"
        "2. Предоставлять отчеты о проверках\n"
        "3. Соблюдать конфиденциальность информации\n"
        "4. Быть онлайн минимум 4 часа в день\n\n"
        "За нарушение правил - снятие с должности.\n"
        "3 предупреждения = автоматическое снятие.\n\n"
        f"📝 Причина назначения: {reason}\n\n"
        "Вы согласны стать администратором?"
    )
    
    try:
        await bot.send_message(new_admin_id, admin_agreement, reply_markup=keyboard)
        await message.answer(
            f"✅ Предложение отправлено пользователю {admin_info}",
            reply_markup=get_admin_keyboard()
        )
    except Exception as e:
        await message.answer(
            "❌ Не удалось отправить предложение пользователю.\n"
            "Возможно, бот заблокирован."
        )
        logger.error(f"Error sending admin offer: {e}")
        
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith(("accept_admin_", "reject_admin_")))
async def process_admin_response(callback: CallbackQuery):
    action, user_id = callback.data.split("_")[0:2]
    user_id = int(user_id)
    
    if action == "reject":
        await callback.message.edit_text(
            "❌ Вы отклонили предложение стать администратором."
        )
        try:
            await bot.send_message(
                OWNER_ID,
                f"❌ Пользователь {callback.from_user.id} отклонил предложение стать администратором."
            )
        except Exception as e:
            logger.error(f"Error notifying owner about admin rejection: {e}")
        return
        
    # Принятие предложения
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('''
            INSERT INTO admins (
                admin_id,
                username,
                first_name,
                last_name,
                approved_count,
                rejected_count,
                warnings,
                registration_date
            ) VALUES (?, ?, ?, ?, 0, 0, 0, CURRENT_TIMESTAMP)
        ''', (
            callback.from_user.id,
            callback.from_user.username,
            callback.from_user.first_name,
            callback.from_user.last_name
        ))
        await db.commit()
        
    await callback.message.edit_text(
        "✅ Поздравляем! Вы стали администратором бота.\n"
        "Используйте /admin для доступа к панели администратора."
    )
    
    try:
        await bot.send_message(
            OWNER_ID,
            f"✅ Пользователь {callback.from_user.username or callback.from_user.id} принял предложение стать администратором."
        )
    except Exception as e:
        logger.error(f"Error notifying owner about admin acceptance: {e}")

@dp.message(F.text == "📊 Начисление рефералов")
async def add_referrals_start(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer(
        "👤 Введите ID пользователя для начисления рефералов:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_referral_user)

@dp.message(UserStates.waiting_for_referral_user)
async def process_referral_user(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    if not message.text.isdigit() or len(message.text) < 9:
        await message.answer("❌ Неверный формат ID. ID должен содержать минимум 9 цифр.")
        return
        
    user_id = int(message.text)
    await state.update_data(target_user_id=user_id)
    await message.answer("📊 Введите количество рефералов:")
    await state.set_state(UserStates.waiting_for_referral_count)
@dp.message(UserStates.waiting_for_referral_count)
async def process_referral_count(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    try:
        count = int(message.text)
        if count <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное целое число.")
        return
        
    await state.update_data(referral_count=count)
    await message.answer("📝 Введите причину начисления:")
    await state.set_state(UserStates.waiting_for_referral_reason)

@dp.message(UserStates.waiting_for_referral_reason)
async def process_referral_reason(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    user_data = await state.get_data()
    target_id = user_data['target_user_id']
    count = user_data['referral_count']
    reason = message.text
    
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('''
            UPDATE users 
            SET referrals_count = referrals_count + ?,
                balance = balance + ?
            WHERE user_id = ?
        ''', (count, count * REFERRAL_REWARD, target_id))
        await db.commit()
        
        try:
            await bot.send_message(
                target_id,
                f"📊 Вам начислено {count} рефералов\n"
                f"💰 Баланс пополнен на {count * REFERRAL_REWARD} баллов\n"
                f"📝 Причина: {reason}"
            )
        except Exception as e:
            logger.error(f"Error sending referral notification: {e}")
    
    await message.answer(
        f"✅ Успешно начислено {count} рефералов\n"
        f"👤 Пользователю: {target_id}\n"
        f"📝 Причина: {reason}",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()
    
@dp.message(F.text == "🎖 Выдать VIP")
async def give_vip_start(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer(
        "👤 Введите ID пользователя:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_vip_user)

@dp.message(UserStates.waiting_for_vip_user)
async def process_vip_user(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    if not message.text.isdigit() or len(message.text) < 9:
        await message.answer("❌ Неверный формат ID. ID должен содержать минимум 9 цифр.")
        return
        
    user_id = int(message.text)
    await state.update_data(target_user_id=user_id)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="7 дней"), KeyboardButton(text="30 дней")],
            [KeyboardButton(text="365 дней"), KeyboardButton(text="Навсегда")],
            [KeyboardButton(text="↩️ Отмена")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "⏰ Выберите длительность VIP статуса:",
        reply_markup=keyboard
    )
    await state.set_state(UserStates.waiting_for_vip_duration)

@dp.message(UserStates.waiting_for_vip_duration)
async def process_vip_duration(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    duration_map = {
        "7 дней": 7,
        "30 дней": 30,
        "365 дней": 365,
        "Навсегда": 0
    }
    
    if message.text not in duration_map:
        await message.answer("❌ Неверная длительность. Используйте клавиатуру.")
        return
        
    duration = duration_map[message.text]
    await state.update_data(vip_duration=duration)
    await message.answer("📝 Введите причину выдачи VIP статуса:")
    await state.set_state(UserStates.waiting_for_vip_reason)

@dp.message(UserStates.waiting_for_vip_reason)
async def process_vip_reason(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    user_data = await state.get_data()
    target_id = user_data['target_user_id']
    duration = user_data['vip_duration']
    reason = message.text
    
    async with aiosqlite.connect('bot_database.db') as db:
        if duration == 0:
            expiration = None
        else:
            expiration = datetime.now(timezone.utc) + timedelta(days=duration)
            
        await db.execute('''
            UPDATE users 
            SET is_vip = TRUE,
                vip_expiration = ?
            WHERE user_id = ?
        ''', (expiration, target_id))
        await db.commit()
        
        duration_text = "навсегда" if duration == 0 else f"на {duration} дней"
        
        try:
            await bot.send_message(
                target_id,
                f"👑 Вам выдан VIP статус {duration_text}!\n"
                f"📝 Причина: {reason}"
            )
        except Exception as e:
            logger.error(f"Error sending VIP notification: {e}")
    
    await message.answer(
        f"✅ VIP статус выдан {duration_text}\n"
        f"👤 Пользователю: {target_id}\n"
        f"📝 Причина: {reason}",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()

@dp.message(F.text == "🚫 Снять VIP")
async def remove_vip_start(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer(
        "👤 Введите ID пользователя:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_remove_vip_user)

@dp.message(UserStates.waiting_for_remove_vip_user)
async def process_remove_vip_user(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    if not message.text.isdigit() or len(message.text) < 9:
        await message.answer("❌ Неверный формат ID. ID должен содержать минимум 9 цифр.")
        return
        
    user_id = int(message.text)
    
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute(
            'SELECT is_vip FROM users WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            
        if not result or not result[0]:
            await message.answer(
                "❌ У пользователя нет VIP статуса.",
                reply_markup=get_admin_keyboard()
            )
            await state.clear()
            return
            
    await state.update_data(target_user_id=user_id)
    await message.answer("📝 Введите причину снятия VIP статуса:")
    await state.set_state(UserStates.waiting_for_remove_vip_reason)

@dp.message(UserStates.waiting_for_remove_vip_reason)
async def process_remove_vip_reason(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    user_data = await state.get_data()
    target_id = user_data['target_user_id']
    reason = message.text
    
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('''
            UPDATE users 
            SET is_vip = FALSE,
                vip_expiration = NULL
            WHERE user_id = ?
        ''', (target_id,))
        await db.commit()
        
        try:
            await bot.send_message(
                target_id,
                f"❌ Ваш VIP статус снят!\n"
                f"📝 Причина: {reason}"
            )
        except Exception as e:
            logger.error(f"Error sending VIP removal notification: {e}")
    
    await message.answer(
        f"✅ VIP статус снят\n"
        f"👤 У пользователя: {target_id}\n"
        f"📝 Причина: {reason}",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()
    
    
@dp.message(F.text == "💸 Оштрафовать")
async def fine_user_start(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer(
        "👤 Введите ID пользователя для штрафа:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_fine_user)

@dp.message(UserStates.waiting_for_fine_user)
async def process_fine_user(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    if not message.text.isdigit() or len(message.text) < 9:
        await message.answer("❌ Неверный формат ID. ID должен содержать минимум 9 цифр.")
        return
        
    user_id = int(message.text)
    
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute(
            'SELECT balance FROM users WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            result = await cursor.fetchone()
            
        if not result:
            await message.answer("❌ Пользователь не найден.")
            return
            
    await state.update_data(target_user_id=user_id, current_balance=result[0])
    await message.answer("💰 Введите сумму штрафа:")
    await state.set_state(UserStates.waiting_for_fine_amount)

@dp.message(UserStates.waiting_for_fine_amount)
async def process_fine_amount(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите положительное число.")
        return
        
    user_data = await state.get_data()
    current_balance = user_data['current_balance']
    
    await state.update_data(fine_amount=min(amount, current_balance))
    await message.answer("📝 Введите причину штрафа:")
    await state.set_state(UserStates.waiting_for_fine_reason)

@dp.message(UserStates.waiting_for_fine_reason)
async def process_fine_reason(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    user_data = await state.get_data()
    target_id = user_data['target_user_id']
    amount = user_data['fine_amount']
    current_balance = user_data['current_balance']
    reason = message.text
    
    # Если штраф больше баланса, обнуляем баланс
    new_balance = max(0, current_balance - amount)
    
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('''
            UPDATE users 
            SET balance = ?
            WHERE user_id = ?
        ''', (new_balance, target_id))
        await db.commit()
        
        try:
            await bot.send_message(
                target_id,
                f"⚠️ На вас наложен штраф!\n"
                f"💰 Сумма: {amount} баллов\n"
                f"📝 Причина: {reason}\n"
                f"💳 Текущий баланс: {new_balance} баллов"
            )
        except Exception as e:
            logger.error(f"Error sending fine notification: {e}")
    
    await message.answer(
        f"✅ Штраф успешно наложен\n"
        f"👤 Пользователь: {target_id}\n"
        f"💰 Сумма: {amount} баллов\n"
        f"📝 Причина: {reason}\n"
        f"💳 Новый баланс: {new_balance} баллов",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()
    
    
@dp.message(F.text == "🗑 Удалить пользователя")
async def delete_user_start(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer(
        "⚠️ ВНИМАНИЕ! Это действие нельзя отменить!\n"
        "👤 Введите ID пользователя для удаления:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_delete_user)

@dp.message(UserStates.waiting_for_delete_user)
async def process_delete_user(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    if not message.text.isdigit() or len(message.text) < 9:
        await message.answer("❌ Неверный формат ID. ID должен содержать минимум 9 цифр.")
        return
        
    user_id = int(message.text)
    
    if user_id == OWNER_ID:
        await message.answer("❌ Невозможно удалить владельца бота!")
        return
        
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute(
            'SELECT username, first_name, last_name FROM users WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            user = await cursor.fetchone()
            
        if not user:
            await message.answer("❌ Пользователь не найден.")
            return
            
    await state.update_data(
        target_user_id=user_id,
        target_user_info=f"{user[0] or ''} ({user[1] or ''} {user[2] or ''})"
    )
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ Подтвердить")],
            [KeyboardButton(text="↩️ Отмена")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        f"⚠️ Вы действительно хотите удалить пользователя?\n"
        f"👤 ID: {user_id}\n"
        f"📝 Данные: {user[0] or ''} ({user[1] or ''} {user[2] or ''})",
        reply_markup=keyboard
    )
    await state.set_state(UserStates.waiting_for_delete_confirm)

@dp.message(UserStates.waiting_for_delete_confirm)
async def confirm_delete_user(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    if message.text != "✅ Подтвердить":
        await message.answer("❌ Неверная команда. Используйте клавиатуру.")
        return
        
    user_data = await state.get_data()
    target_id = user_data['target_user_id']
    
    async with aiosqlite.connect('bot_database.db') as db:
        # Сохраняем данные в лог
        await db.execute('''
            INSERT INTO action_logs (
                user_id, action_type, action_details
            ) VALUES (?, 'user_deleted', ?)
        ''', (
            message.from_user.id,
            json.dumps({
                "target_id": target_id,
                "target_info": user_data['target_user_info'],
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        ))
        
        # Удаляем пользователя
        await db.execute('DELETE FROM users WHERE user_id = ?', (target_id,))
        await db.commit()
        
    try:
        # Удаляем историю чата
        await bot.delete_chat_history(target_id)
        # Покидаем чат
        await bot.leave_chat(target_id)
    except Exception as e:
        logger.error(f"Error cleaning user chat: {e}")
    
    await message.answer(
        f"✅ Пользователь {target_id} успешно удален из бота.",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()
    
@dp.message(F.text == "➕ Добавить информацию")
async def add_info_start(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer(
        "👤 Введите ID пользователя для добавления информации:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_info_user)

@dp.message(UserStates.waiting_for_info_user)
async def process_info_user(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    if not message.text.isdigit() or len(message.text) < 9:
        await message.answer("❌ Неверный формат ID. ID должен содержать минимум 9 цифр.")
        return
        
    user_id = int(message.text)
    await state.update_data(target_user_id=user_id)
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Имя"), KeyboardButton(text="👥 Фамилия")],
            [KeyboardButton(text="👤 Отчество"), KeyboardButton(text="📅 Возраст")],
            [KeyboardButton(text="📱 Номер"), KeyboardButton(text="🏠 Место жительства")],
            [KeyboardButton(text="💼 Место работы"), KeyboardButton(text="🌐 Сети")],
            [KeyboardButton(text="↩️ Отмена")]
        ],
        resize_keyboard=True
    )
    
    await message.answer("✍️ Выберите тип информации:", reply_markup=keyboard)
    await state.set_state(UserStates.waiting_for_info_type)

@dp.message(UserStates.waiting_for_info_type)
async def process_info_type(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    info_types = {
        "👤 Имя": "first_name",
        "👥 Фамилия": "last_name",
        "👤 Отчество": "middle_name",
        "📅 Возраст": "birth_date",
        "📱 Номер": "phone_number",
        "🏠 Место жительства": "address",
        "💼 Место работы": "workplace",
        "🌐 Сети": "social_networks"
    }
    
    if message.text not in info_types:
        await message.answer("❌ Неверный тип информации. Используйте клавиатуру.")
        return
        
    await state.update_data(info_type=info_types[message.text])
    await message.answer(
        "✍️ Введите информацию:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_info_value)

@dp.message(UserStates.waiting_for_info_value)
async def process_info_value(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    user_data = await state.get_data()
    target_id = user_data['target_user_id']
    info_type = user_data['info_type']
    
    async with aiosqlite.connect('bot_database.db') as db:
        # Проверяем существование записи
        async with db.execute(
            'SELECT 1 FROM info_base WHERE telegram_id = ?',
            (target_id,)
        ) as cursor:
            exists = await cursor.fetchone()
            
        if exists:
            await db.execute(f'''
                UPDATE info_base 
                SET {info_type} = ?,
                    admin_approver_id = ?,
                    info_date = CURRENT_TIMESTAMP
                WHERE telegram_id = ?
            ''', (message.text, message.from_user.id, target_id))
        else:
            fields = ['telegram_id', info_type, 'admin_approver_id']
            values = [target_id, message.text, message.from_user.id]
            await db.execute(f'''
                INSERT INTO info_base ({', '.join(fields)})
                VALUES ({', '.join(['?' for _ in fields])})
            ''', values)
            
        await db.commit()
        
    await message.answer(
        "✅ Информация успешно добавлена!",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()

@dp.message(F.text == "❌ Удалить информацию")
async def delete_info_start(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer(
        "👤 Введите ID пользователя для удаления информации:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_delete_info_user)
    
@dp.message(F.text == "➖ Снять админа")
async def remove_admin_start(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer(
        "👤 Введите ID администратора для снятия:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_remove_admin)

@dp.message(UserStates.waiting_for_remove_admin)
async def process_remove_admin(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    if not message.text.isdigit() or len(message.text) < 9:
        await message.answer("❌ Неверный формат ID. ID должен содержать минимум 9 цифр.")
        return
        
    admin_id = int(message.text)
    
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute(
            'SELECT username, first_name, last_name FROM admins WHERE admin_id = ?',
            (admin_id,)
        ) as cursor:
            admin = await cursor.fetchone()
            
        if not admin:
            await message.answer("❌ Администратор не найден.")
            await state.clear()
            return
            
    await state.update_data(
        remove_admin_id=admin_id,
        admin_info=f"@{admin[0] or ''} ({admin[1] or ''} {admin[2] or ''})"
    )
    await message.answer("📝 Введите причину снятия с должности:")
    await state.set_state(UserStates.waiting_for_remove_admin_reason)

@dp.message(UserStates.waiting_for_remove_admin_reason)
async def process_remove_admin_reason(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    user_data = await state.get_data()
    admin_id = user_data['remove_admin_id']
    admin_info = user_data['admin_info']
    reason = message.text
    
    async with aiosqlite.connect('bot_database.db') as db:
        # Сохраняем лог о снятии админа
        await db.execute('''
            INSERT INTO admin_logs (
                admin_id,
                action_type,
                action_details,
                action_date
            ) VALUES (?, 'removal', ?, CURRENT_TIMESTAMP)
        ''', (admin_id, reason))
        
        # Удаляем админа
        await db.execute('DELETE FROM admins WHERE admin_id = ?', (admin_id,))
        await db.commit()
        
    try:
        # Уведомляем админа о снятии
        await bot.send_message(
            admin_id,
            f"❌ Вы были сняты с должности администратора.\n"
            f"📝 Причина: {reason}"
        )
        # Очищаем историю чата
        await bot.delete_chat_history(admin_id)
    except Exception as e:
        logger.error(f"Error notifying removed admin: {e}")
        
    await message.answer(
        f"✅ Администратор {admin_info} снят с должности\n"
        f"📝 Причина: {reason}",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()
    
@dp.message(F.text == "👀 Кто донёс")
async def who_reported_start(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer(
        "👤 Введите ID пользователя для просмотра информации:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_info_search)

@dp.message(UserStates.waiting_for_info_search)
async def process_info_search(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    if not message.text.isdigit() or len(message.text) < 9:
        await message.answer("❌ Неверный формат ID. ID должен содержать минимум 9 цифр.")
        return
        
    target_id = int(message.text)
    
    async with aiosqlite.connect('bot_database.db') as db:
        # Получаем всю информацию о пользователе с данными о тех, кто её предоставил
        async with db.execute('''
            SELECT 
                i.first_name,
                i.last_name,
                i.middle_name,
                i.birth_date,
                i.phone_number,
                i.address,
                i.workplace,
                i.social_networks,
                i.info_provider_id,
                i.admin_approver_id,
                i.info_date,
                u.username as provider_username,
                u.first_name as provider_first_name,
                a.username as admin_username,
                a.first_name as admin_first_name
            FROM info_base i
            LEFT JOIN users u ON i.info_provider_id = u.user_id
            LEFT JOIN admins a ON i.admin_approver_id = a.admin_id
            WHERE i.telegram_id = ?
        ''') as cursor:
            info = await cursor.fetchone()
            
        if not info:
            await message.answer("❌ Информация не найдена.")
            return
            
        # Формируем сообщение
        fields = {
            "👤 Имя": info[0],
            "👥 Фамилия": info[1],
            "👤 Отчество": info[2],
            "📅 Дата рождения": info[3],
            "📱 Номер": info[4],
            "🏠 Место жительства": info[5],
            "💼 Место работы": info[6],
            "🌐 Сети": info[7]
        }
        
        result_text = f"📋 Информация о пользователе {target_id}:\n\n"
        
        for field_name, value in fields.items():
            if value:
                provider = f"@{info[11]}" if info[11] else f"{info[12]}"
                admin = f"@{info[13]}" if info[13] else f"{info[14]}"
                date = datetime.fromisoformat(info[10]).strftime("%d.%m.%Y %H:%M")
                result_text += (
                    f"{field_name}: {value}\n"
                    f"├ Донёс: {provider} ({info[8]})\n"
                    f"├ Одобрил: {admin} ({info[9]})\n"
                    f"└ Дата: {date}\n\n"
                )
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="❌ Удалить информацию")],
                [KeyboardButton(text="↩️ В меню")]
            ],
            resize_keyboard=True
        )
        
        await message.answer(result_text, reply_markup=keyboard)
        await state.update_data(target_id=target_id, available_fields=fields)
        await state.set_state(UserStates.waiting_for_delete_info_type)

@dp.message(UserStates.waiting_for_delete_info_type)
async def process_delete_info_type(message: Message, state: FSMContext):
    if message.text == "↩️ В меню":
        await message.answer("↩️ Возвращаемся в меню", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    if message.text != "❌ Удалить информацию":
        await message.answer("❌ Неверная команда. Используйте клавиатуру.")
        return
        
    user_data = await state.get_data()
    fields = user_data['available_fields']
    
    # Создаем клавиатуру из доступных полей
    keyboard = []
    for field_name, value in fields.items():
        if value:
            keyboard.append([KeyboardButton(text=field_name)])
    keyboard.append([KeyboardButton(text="↩️ Отмена")])
    
    await message.answer(
        "✏️ Выберите поле для удаления:",
        reply_markup=ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    )
    await state.set_state(UserStates.waiting_for_delete_field)

@dp.message(UserStates.waiting_for_delete_field)
async def process_delete_field(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    user_data = await state.get_data()
    target_id = user_data['target_id']
    fields = user_data['available_fields']
    
    if message.text not in fields:
        await message.answer("❌ Неверное поле. Используйте клавиатуру.")
        return
        
    # Мапинг названий полей в базе данных
    field_mapping = {
        "👤 Имя": "first_name",
        "👥 Фамилия": "last_name",
        "👤 Отчество": "middle_name",
        "📅 Дата рождения": "birth_date",
        "📱 Номер": "phone_number",
        "🏠 Место жительства": "address",
        "💼 Место работы": "workplace",
        "🌐 Сети": "social_networks"
    }
    
    field = field_mapping[message.text]
    
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute(f'''
            UPDATE info_base 
            SET {field} = NULL,
                info_provider_id = NULL,
                admin_approver_id = NULL
            WHERE telegram_id = ?
        ''', (target_id,))
        await db.commit()
        
    await message.answer(
        f"✅ Поле {message.text} успешно очищено!",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()
    
@dp.message(F.text == "🔒 Бан")
async def ban_user_start(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer(
        "👤 Введите ID пользователя для бана:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_ban_user)

@dp.message(UserStates.waiting_for_ban_user)
async def process_ban_user(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    if not message.text.isdigit() or len(message.text) < 9:
        await message.answer("❌ Неверный формат ID. ID должен содержать минимум 9 цифр.")
        return
        
    user_id = int(message.text)
    
    if user_id == OWNER_ID:
        await message.answer("❌ Невозможно забанить владельца бота!")
        return
        
    if await is_banned(user_id):
        await message.answer("❌ Пользователь уже забанен.")
        return
        
    # Проверяем существование пользователя
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute(
            'SELECT username, first_name, last_name FROM users WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            user = await cursor.fetchone()
            
        if not user:
            await message.answer("❌ Пользователь не найден в базе данных.")
            return
            
    await state.update_data(
        target_user_id=user_id,
        user_info=f"{user[0] or ''} ({user[1] or ''} {user[2] or ''})"
    )
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="1 час"),
                KeyboardButton(text="24 часа"),
                KeyboardButton(text="72 часа")
            ],
            [
                KeyboardButton(text="7 дней"),
                KeyboardButton(text="30 дней"),
                KeyboardButton(text="Навсегда")
            ],
            [KeyboardButton(text="↩️ Отмена")]
        ],
        resize_keyboard=True
    )
    
    await message.answer(
        "⏰ Выберите длительность бана или введите количество часов (1-100000):",
        reply_markup=keyboard
    )
    await state.set_state(UserStates.waiting_for_ban_duration)

@dp.message(UserStates.waiting_for_ban_duration)
async def process_ban_duration(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    duration_map = {
        "1 час": 1,
        "24 часа": 24,
        "72 часа": 72,
        "7 дней": 168,  # 7 * 24
        "30 дней": 720,  # 30 * 24
        "Навсегда": 0
    }
    
    if message.text in duration_map:
        hours = duration_map[message.text]
    else:
        try:
            hours = int(message.text)
            if not (0 <= hours <= 100000):
                raise ValueError
        except ValueError:
            await message.answer(
                "❌ Неверная длительность. Введите число от 0 до 100000 или используйте клавиатуру."
            )
            return
            
    await state.update_data(ban_duration=hours)
    await message.answer(
        "📝 Введите причину бана:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_ban_reason)

@dp.message(UserStates.waiting_for_ban_reason)
async def process_ban_reason(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    user_data = await state.get_data()
    target_id = user_data['target_user_id']
    hours = user_data['ban_duration']
    reason = message.text
    
    # Сохраняем текущие данные пользователя перед баном
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('''
            SELECT balance, is_vip, vip_expiration, referrals_count
            FROM users WHERE user_id = ?
        ''', (target_id,)) as cursor:
            user_data = await cursor.fetchone()
            
        if hours == 0:  # Вечный бан
            ban_expiration = None
        else:
            ban_expiration = datetime.now(timezone.utc) + timedelta(hours=hours)
        
        # Сохраняем данные пользователя в таблицу забаненных
        await db.execute('''
            INSERT INTO banned_users (
                user_id, ban_reason, ban_date, ban_expiration, user_data
            ) VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)
        ''', (
            target_id,
            reason,
            ban_expiration,
            json.dumps(user_data) if user_data else None
        ))
        
        # Удаляем пользователя из основной таблицы
        await db.execute('DELETE FROM users WHERE user_id = ?', (target_id,))
        await db.commit()
    
    try:
        # Очищаем историю чата
        await bot.delete_chat_history(target_id)
        
        if hours == 0:
            ban_message = (
                f"🚫 Вы забанены навсегда!\n"
                f"📝 Причина: {reason}"
            )
        else:
            expiry_time = ban_expiration.strftime("%d.%m.%Y %H:%M:%S")
            ban_message = (
                f"🚫 Вы забанены на {hours} часов!\n"
                f"⏰ Дата окончания: {expiry_time}\n"
                f"📝 Причина: {reason}"
            )
        
        # Отправляем сообщение о бане
        ban_msg = await bot.send_message(target_id, ban_message)
        
        if hours > 0:
            # Запускаем задачу обновления таймера
            asyncio.create_task(update_ban_timer(target_id, ban_msg.message_id, ban_expiration))
            
    except Exception as e:
        logger.error(f"Error sending ban notification: {e}")
    
    duration_text = "навсегда" if hours == 0 else f"на {hours} часов"
    await message.answer(
        f"✅ Пользователь {target_id} забанен {duration_text}\n"
        f"📝 Причина: {reason}",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()

async def update_ban_timer(user_id: int, message_id: int, expiration: datetime):
    """Обновляет таймер бана в сообщении"""
    while True:
        try:
            now = datetime.now(timezone.utc)
            if now >= expiration:
                # Время бана истекло
                await unban_user(user_id, "Истек срок бана")
                await bot.edit_message_text(
                    "✅ Бан снят! Вы снова можете использовать бота.",
                    user_id,
                    message_id
                )
                break
                
            # Вычисляем оставшееся время
            remaining = expiration - now
            years = remaining.days // 365
            months = (remaining.days % 365) // 30
            days = (remaining.days % 30)
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            seconds = remaining.seconds % 60
            
            # Форматируем сообщение
            time_parts = []
            if years > 0:
                time_parts.append(f"{years}г")
            if months > 0:
                time_parts.append(f"{months}м")
            if days > 0:
                time_parts.append(f"{days}д")
            if hours > 0:
                time_parts.append(f"{hours}ч")
            if minutes > 0:
                time_parts.append(f"{minutes}м")
            time_parts.append(f"{seconds}с")
            
            time_str = " ".join(time_parts)
            
            await bot.edit_message_text(
                f"🚫 До конца бана осталось: {time_str}",
                user_id,
                message_id
            )
            
            # Определяем интервал обновления
            if remaining.total_seconds() > 86400:  # > 1 день
                await asyncio.sleep(3600)  # 1 час
            elif remaining.total_seconds() > 3600:  # > 1 час
                await asyncio.sleep(60)  # 1 минута
            else:
                await asyncio.sleep(1)  # 1 секунда
                
        except Exception as e:
            logger.error(f"Error updating ban timer: {e}")
            break

async def unban_user(user_id: int, reason: str):
    """Разбанивает пользователя"""
    async with aiosqlite.connect('bot_database.db') as db:
        # Получаем данные пользователя из таблицы забаненных
        async with db.execute('''
            SELECT user_data FROM banned_users WHERE user_id = ?
        ''', (user_id,)) as cursor:
            result = await cursor.fetchone()
            
        if not result:
            return
            
        user_data = json.loads(result[0]) if result[0] else {}
        
        # Восстанавливаем пользователя в основной таблице
        await db.execute('''
            INSERT INTO users (
                user_id, balance, is_vip, vip_expiration, referrals_count
            ) VALUES (?, ?, ?, ?, ?)
        ''', (
            user_id,
            user_data.get('balance', 0),
            user_data.get('is_vip', False),
            user_data.get('vip_expiration'),
            user_data.get('referrals_count', 0)
        ))
        
        # Удаляем запись из таблицы забаненных
        await db.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
        await db.commit()
        
        try:
            await bot.send_message(
                user_id,
                f"✅ Ваш бан снят!\n"
                f"📝 Причина: {reason}\n"
                f"Добро пожаловать обратно!"
            )
        except Exception as e:
            logger.error(f"Error sending unban notification: {e}")

            
@dp.message(F.text == "🔓 Разбан")
async def unban_start(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer(
        "👤 Введите ID пользователя для разбана:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_unban_user)

@dp.message(UserStates.waiting_for_unban_user)
async def process_unban_user(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    if not message.text.isdigit() or len(message.text) < 9:
        await message.answer("❌ Неверный формат ID. ID должен содержать минимум 9 цифр.")
        return
        
    user_id = int(message.text)
    
    if not await is_banned(user_id):
        await message.answer("❌ Пользователь не находится в бане.")
        return
        
    await state.update_data(target_user_id=user_id)
    await message.answer(
        "📝 Введите причину разбана:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_unban_reason)

@dp.message(UserStates.waiting_for_unban_reason)
async def process_unban_reason(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    user_data = await state.get_data()
    target_id = user_data['target_user_id']
    reason = message.text
    
    await unban_user(target_id, reason)
    
    await message.answer(
        f"✅ Пользователь {target_id} разбанен\n"
        f"📝 Причина: {reason}",
        reply_markup=get_admin_keyboard()
    )
    await state.clear()
    
                            
@dp.message(F.text == "⚠️ Выдать варн")
async def warn_admin_start(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    await message.answer(
        "👤 Введите ID администратора для выдачи предупреждения:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="↩️ Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(UserStates.waiting_for_warn_admin)

@dp.message(UserStates.waiting_for_warn_admin)
async def process_warn_admin(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    if not message.text.isdigit() or len(message.text) < 9:
        await message.answer("❌ Неверный формат ID. ID должен содержать минимум 9 цифр.")
        return
        
    admin_id = int(message.text)
    
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('''
            SELECT username, first_name, last_name, warnings 
            FROM admins 
            WHERE admin_id = ?
        ''', (admin_id,)) as cursor:
            admin = await cursor.fetchone()
            
        if not admin:
            await message.answer("❌ Администратор не найден.")
            await state.clear()
            return
            
    await state.update_data(
        warn_admin_id=admin_id,
        admin_info=f"@{admin[0] or ''} ({admin[1] or ''} {admin[2] or ''})",
        current_warnings=admin[3]
    )
    await message.answer("📝 Введите причину предупреждения:")
    await state.set_state(UserStates.waiting_for_warn_reason)

@dp.message(UserStates.waiting_for_warn_reason)
async def process_warn_reason(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    user_data = await state.get_data()
    admin_id = user_data['warn_admin_id']
    admin_info = user_data['admin_info']
    current_warnings = user_data['current_warnings']
    reason = message.text
    
    new_warnings = current_warnings + 1
    
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('''
            UPDATE admins 
            SET warnings = ?
            WHERE admin_id = ?
        ''', (new_warnings, admin_id))
        
            
@dp.message(UserStates.waiting_for_warn_reason)
async def process_warn_reason(message: Message, state: FSMContext):
    if message.text == "↩️ Отмена":
        await message.answer("↩️ Действие отменено", reply_markup=get_admin_keyboard())
        await state.clear()
        return
        
    user_data = await state.get_data()
    admin_id = user_data['warn_admin_id']
    admin_info = user_data['admin_info']
    current_warnings = user_data['current_warnings']
    reason = message.text
    
    new_warnings = current_warnings + 1
    
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('''
            UPDATE admins 
            SET warnings = ?
            WHERE admin_id = ?
        ''', (new_warnings, admin_id))
        
        # Сохраняем лог предупреждения
        await db.execute('''
            INSERT INTO admin_logs (
                admin_id,
                action_type,
                action_details,
                action_date
            ) VALUES (?, 'warning', ?, CURRENT_TIMESTAMP)
        ''', (admin_id, reason))
        
        await db.commit()
        
        # Если это третье предупреждение - автоматическое снятие
        if new_warnings >= 3:
            # Сохраняем лог о снятии
            await db.execute('''
                INSERT INTO admin_logs (
                    admin_id,
                    action_type,
                    action_details,
                    action_date
                ) VALUES (?, 'auto_removal', 'Автоматическое снятие после 3 предупреждений', CURRENT_TIMESTAMP)
            ''', (admin_id,))
            
            # Удаляем админа
            await db.execute('DELETE FROM admins WHERE admin_id = ?', (admin_id,))
            await db.commit()
            
            try:
                # Уведомляем админа о снятии
                await bot.send_message(
                    admin_id,
                    "❌ Вы автоматически сняты с должности администратора после получения 3 предупреждений.\n"
                    f"📝 Последнее предупреждение: {reason}"
                )
                # Очищаем историю чата
                await bot.delete_chat_history(admin_id)
            except Exception as e:
                logger.error(f"Error notifying removed admin: {e}")
                
            await message.answer(
                f"⚠️ Администратор {admin_info} получил третье предупреждение и был автоматически снят с должности.\n"
                f"📝 Причина последнего предупреждения: {reason}",
                reply_markup=get_admin_keyboard()
            )
        else:
            try:
                # Уведомляем админа о предупреждении
                await bot.send_message(
                    admin_id,
                    f"⚠️ Вы получили предупреждение ({new_warnings}/3)\n"
                    f"📝 Причина: {reason}"
                )
            except Exception as e:
                logger.error(f"Error notifying warned admin: {e}")
                
            await message.answer(
                f"⚠️ Администратор {admin_info} получил предупреждение ({new_warnings}/3)\n"
                f"📝 Причина: {reason}",
                reply_markup=get_admin_keyboard()
            )
    
    await state.clear()
    
        
            
@dp.message(F.text == "📈 Недельная статистика")
async def show_weekly_stats(message: Message):
    if not await is_owner(message.from_user.id):
        return
        
    # Получаем дату начала недели (7 дней назад)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    async with aiosqlite.connect('bot_database.db') as db:
        # Статистика проверок по админам за неделю
        async with db.execute('''
            SELECT 
                a.username,
                a.first_name,
                COUNT(CASE WHEN l.action_type = 'approve' THEN 1 END) as approves,
                COUNT(CASE WHEN l.action_type = 'reject' THEN 1 END) as rejects,
                COUNT(CASE WHEN l.action_type = 'warning' THEN 1 END) as warnings
            FROM admins a
            LEFT JOIN admin_logs l ON a.admin_id = l.admin_id
            WHERE l.action_date >= ?
            GROUP BY a.admin_id
            ORDER BY (approves + rejects) DESC
        ''', (week_ago.isoformat(),)) as cursor:
            admin_stats = await cursor.fetchall()
            
        # Статистика платежей за неделю
        async with db.execute('''
            SELECT 
                SUM(CASE WHEN payment_type = 'balance' THEN amount ELSE 0 END) as balance_payments,
                SUM(CASE WHEN payment_type = 'vip' THEN amount ELSE 0 END) as vip_payments,
                COUNT(*) as total_transactions
            FROM payments
            WHERE payment_date >= ? AND payment_status = 'completed'
        ''', (week_ago.isoformat(),)) as cursor:
            payment_stats = await cursor.fetchone()
            
        # Статистика новых пользователей
        async with db.execute('''
            SELECT COUNT(*) 
            FROM users 
            WHERE registration_date >= ?
        ''', (week_ago.isoformat(),)) as cursor:
            new_users = await cursor.fetchone()
            
        # Статистика доносов
        async with db.execute('''
            SELECT 
                COUNT(*) as total_reports,
                COUNT(DISTINCT telegram_id) as unique_targets
            FROM info_base
            WHERE info_date >= ?
        ''', (week_ago.isoformat(),)) as cursor:
            report_stats = await cursor.fetchone()
        
        stats_text = (
            "📈 НЕДЕЛЬНАЯ СТАТИСТИКА\n"
            f"📅 Период: {week_ago.strftime('%d.%m.%Y')} - {datetime.now().strftime('%d.%m.%Y')}\n\n"
            
            "👮 Статистика админов:\n"
        )
        
        if admin_stats:
            for admin in admin_stats:
                username, first_name, approves, rejects, warnings = admin
                total_checks = approves + rejects
                if total_checks > 0:
                    efficiency = (approves / total_checks) * 100
                else:
                    efficiency = 0
                    
                stats_text += (
                    f"├ {first_name} (@{username or 'None'})\n"
                    f"│ ✅ Одобрено: {approves}\n"
                    f"│ ❌ Отклонено: {rejects}\n"
                    f"│ ⚠️ Получено предупреждений: {warnings}\n"
                    f"│ 📊 Эффективность: {efficiency:.1f}%\n"
                    "│\n"
                )
        else:
            stats_text += "├ Нет активности администраторов\n"
            
        stats_text += (
            "\n💰 Финансы:\n"
            f"├ Транзакций: {payment_stats[2] or 0}\n"
            f"├ Доход с баллов: ${payment_stats[0] or 0:.2f}\n"
            f"└ Доход с VIP: ${payment_stats[1] or 0:.2f}\n\n"
            
            "👥 Пользователи:\n"
            f"└ Новых за неделю: {new_users[0]}\n\n"
            
            "📋 Доносы:\n"
            f"├ Всего доносов: {report_stats[0]}\n"
            f"└ Уникальных целей: {report_stats[1]}"
        )
        
        await message.answer(stats_text, reply_markup=get_admin_keyboard())
        
            
                
                        
@dp.message(F.text == "🔎 Просмотр информации")
async def view_info_start(message: Message, state: FSMContext):
    if not await is_owner(message.from_user.id):
        return
    
    await message.answer(
        "🔍 Введите ID пользователя или имя для поиска:"
    )
    await state.set_state("waiting_for_info_search")

@dp.message(lambda message: message.from_user.id == OWNER_ID and message.state == "waiting_for_info_search")
async def process_info_search(message: Message, state: FSMContext):
    search_query = message.text.strip()
    
    async with aiosqlite.connect('bot_database.db') as db:
        if search_query.isdigit():
            # Search by ID
            async with db.execute('''
                SELECT * FROM users 
                WHERE user_id = ?
            ''', (int(search_query),)) as cursor:
                user = await cursor.fetchone()
                users = [user] if user else []
        else:
            # Search by name
            async with db.execute('''
                SELECT * FROM users 
                WHERE username LIKE ? OR first_name LIKE ? OR last_name LIKE ?
            ''', (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%")) as cursor:
                users = await cursor.fetchall()
        
        if not users:
            await message.answer("❌ Пользователь не найден.")
            await state.clear()
            return
        
        if len(users) > 1:
            # Multiple matches
            text = "📋 Найдено несколько совпадений:\n\n"
            for user in users:
                text += f"👤 {user[2]} {user[3]} - ID: {user[0]}\n"
            text += "\nВведите ID нужного пользователя:"
            
            await message.answer(text)
            await state.set_state("waiting_for_user_selection")
            await state.update_data(users=users)
            return
        
        # Single user found - show detailed info
        await show_user_details(message, users[0][0])
        await state.clear()

async def show_user_details(message: Message, user_id: int):
    async with aiosqlite.connect('bot_database.db') as db:
        # Get user info
        async with db.execute('''
            SELECT * FROM users WHERE user_id = ?
        ''', (user_id,)) as cursor:
            user = await cursor.fetchone()
        
        if not user:
            await message.answer("❌ Пользователь не найден.")
            return
        
        # Get referrals info
        async with db.execute('''
            SELECT COUNT(*) FROM referrals WHERE user_id = ?
        ''', (user_id,)) as cursor:
            referrals_count = (await cursor.fetchone())[0]
        
        # Get payments info
        async with db.execute('''
            SELECT 
                COUNT(*),
                SUM(CASE WHEN payment_status = 'completed' THEN amount ELSE 0 END)
            FROM payments 
            WHERE user_id = ?
        ''', (user_id,)) as cursor:
            payments_count, total_payments = await cursor.fetchone()
        
        # Get reports info
        async with db.execute('''
            SELECT COUNT(*) FROM reports WHERE user_id = ?
        ''', (user_id,)) as cursor:
            reports_count = (await cursor.fetchone())[0]
        
        reg_date = datetime.fromisoformat(user[11]).strftime("%d.%m.%Y %H:%M")
        vip_status = "Активен" if user[6] else "Неактивен"
        if user[6] and user[7]:
            vip_expiry = datetime.fromisoformat(user[7])
            if vip_expiry > datetime.now(timezone.utc):
                vip_status += f" (до {vip_expiry.strftime('%d.%m.%Y')})"
        
        text = (
            f"👤 Информация о пользователе\n\n"
            f"🆔 ID: {user[0]}\n"
            f"👤 Имя: {user[2]}\n"
            f"👥 Фамилия: {user[3]}\n"
            f"📝 Username: @{user[1]}\n"
            f"📅 Регистрация: {reg_date}\n\n"
            f"💰 Баланс: {user[5]} баллов\n"
            f"👑 VIP статус: {vip_status}\n"
            f"🔑 Реферальный код: {user[4]}\n"
            f"👥 Рефералов привлечено: {referrals_count}\n\n"
            f"📊 Статистика:\n"
            f"💵 Всего платежей: {payments_count}\n"
            f"💰 Сумма платежей: ${total_payments:.2f}\n"
            f"📝 Отправлено доносов: {reports_count}\n"
            f"⚠️ Предупреждений: {user[14]}\n"
        )
        
        await message.answer(text)
# Automatic systems and bot startup
async def check_admin_deadlines():
    """Check admin report deadlines and VIP expiration"""
    while True:
        try:
            async with aiosqlite.connect('bot_database.db') as db:
                # Check report deadlines
                async with db.execute('''
                    SELECT 
                        admin_id,
                        target_user_id,
                        check_start_time
                    FROM reports 
                    WHERE status = 'checking'
                ''') as cursor:
                    checking_reports = await cursor.fetchall()
                
                current_time = datetime.now(timezone.utc)
                for admin_id, target_id, start_time in checking_reports:
                    start_time = datetime.fromisoformat(start_time)
                    if current_time - start_time > timedelta(hours=23, minutes=50):
                        # Send warning to admin
                        await bot.send_message(
                            admin_id,
                            "⚠️ До окончания проверки осталось 10 минут!"
                        )
                    elif current_time - start_time > timedelta(hours=24):
                        # Add warning and possibly remove admin
                        await db.execute('''
                            UPDATE admins 
                            SET warnings = warnings + 3
                            WHERE admin_id = ?
                        ''', (admin_id,))
                        
                        async with db.execute(
                            'SELECT warnings FROM admins WHERE admin_id = ?',
                            (admin_id,)
                        ) as cursor:
                            warnings = (await cursor.fetchone())[0]
                        
                        if warnings >= 3:
                            await remove_admin(
                                admin_id,
                                "Превышение времени проверки доноса"
                            )
                
                # Check VIP expiration
                async with db.execute('''
                    SELECT user_id, vip_expiration
                    FROM users 
                    WHERE is_vip = TRUE AND vip_expiration IS NOT NULL
                ''') as cursor:
                    vip_users = await cursor.fetchall()
                
                for user_id, expiration in vip_users:
                    expiry = datetime.fromisoformat(expiration)
                    if current_time > expiry:
                        await db.execute('''
                            UPDATE users 
                            SET is_vip = FALSE,
                                vip_expiration = NULL
                            WHERE user_id = ?
                        ''', (user_id,))
                        
                        await bot.send_message(
                            user_id,
                            "ℹ️ Ваш VIP статус истек."
                        )
                
                await db.commit()
                
        except Exception as e:
            logger.error(f"Error in admin deadline checker: {e}")
        
        await asyncio.sleep(60)  # Check every minute

async def clean_old_data():
    """Clean old data and maintain database"""
    while True:
        try:
            async with aiosqlite.connect('bot_database.db') as db:
                current_time = datetime.now(timezone.utc)
                
                # Clean old pending reports
                await db.execute('''
                    DELETE FROM reports 
                    WHERE status = 'pending' 
                    AND report_date < ?
                ''', (current_time - timedelta(days=7),))
                
                # Clean old completed payments
                await db.execute('''
                    DELETE FROM payments 
                    WHERE payment_status = 'completed' 
                    AND payment_date < ?
                ''', (current_time - timedelta(days=30),))
                
                # Clean old action logs
                await db.execute('''
                    DELETE FROM action_logs 
                    WHERE action_date < ?
                ''', (current_time - timedelta(days=90),))
                
                await db.commit()
                
                # Vacuum database to reclaim space
                await db.execute('VACUUM')
                
        except Exception as e:
            logger.error(f"Error in database cleaner: {e}")
        
        await asyncio.sleep(86400)  # Run once per day

async def update_statistics():
    """Update bot statistics"""
    while True:
        try:
            async with aiosqlite.connect('bot_database.db') as db:
                async with db.execute('''
                    SELECT 
                        COUNT(*) as total_users,
                        SUM(CASE WHEN is_vip = 1 THEN 1 ELSE 0 END) as vip_users,
                        SUM(referrals_count) as total_referrals
                    FROM users
                ''') as cursor:
                    users_stats = await cursor.fetchone()
                
                async with db.execute('''
                    SELECT COUNT(*) FROM admins
                ''') as cursor:
                    admin_count = (await cursor.fetchone())[0]
                
                async with db.execute('''
                    SELECT SUM(amount) 
                    FROM payments 
                    WHERE payment_status = 'completed'
                ''') as cursor:
                    total_payments = (await cursor.fetchone())[0] or 0
                
                await db.execute('''
                    INSERT INTO statistics (
                        total_users,
                        total_admins,
                        total_payments,
                        total_referrals,
                        stat_date
                    ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (
                    users_stats[0],
                    admin_count,
                    total_payments,
                    users_stats[2]
                ))
                
                await db.commit()
                
        except Exception as e:
            logger.error(f"Error in statistics updater: {e}")
        
        await asyncio.sleep(3600)  # Update every hour

# Security measures
def setup_security():
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bot.log'),
            logging.StreamHandler()
        ]
    )
    
    # Set up API request limits
    dp.message.middleware(ThrottlingMiddleware(rate_limit=1))
    
    # Enable error handling
    dp.errors.register(error_handler)

async def error_handler(event, error):
    """Handle errors in the bot"""
    try:
        error_msg = f"Error: {error}\nEvent: {event}"
        logger.error(error_msg)

        if isinstance(error, SQLInjectionError):
            user_id = getattr(event, 'from_user', None)
            if user_id:
                async with aiosqlite.connect('bot_database.db') as db:
                    await db.execute('''
                        UPDATE users 
                        SET warnings = warnings + 1
                        WHERE user_id = ?
                    ''', (user_id.id,))

                    async with db.execute(
                        'SELECT warnings FROM users WHERE user_id = ?', 
                        (user_id.id,)
                    ) as cursor:
                        warnings = (await cursor.fetchone())[0]
                        if warnings >= 3:
                            await ban_user(user_id.id, "Попытка SQL-инъекции", 0)

                    await db.commit()

                await bot.send_message(
                    OWNER_ID,
                    f"⚠️ Попытка SQL-инъекции!\n"
                    f"Пользователь: {user_id.id if user_id else 'Unknown'}"
                )
        
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

class SQLInjectionError(Exception):
    pass

def check_sql_injection(text: str) -> bool:
    """Check for SQL injection attempts"""
    suspicious_patterns = [
        r'\bSELECT\b',
        r'\bINSERT\b',
        r'\bUPDATE\b',
        r'\bDELETE\b',
        r'\bDROP\b',
        r'\bUNION\b',
        r'--',
        r';',
        r'\/\*',
        r'\*\/',
        r'\bOR\b.*\b=\b',
        r'\bAND\b.*\b=\b'
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            raise SQLInjectionError("Подозрительный ввод")
    
    return False

# Bot startup
async def on_startup():
    """Setup bot on startup"""
    setup_security()
    
    # Initialize database
    await init_db()
    
    # Start background tasks
    asyncio.create_task(check_payments())
    asyncio.create_task(check_admin_deadlines())
    asyncio.create_task(clean_old_data())
    asyncio.create_task(update_statistics())
    
    logger.info("Bot started successfully!")

async def main():
    """Main function to start the bot"""
    # Удаляем вебхук перед запуском
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Set bot commands
    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="profile", description="Профиль")
    ])
    
    # Register startup handler
    dp.startup.register(on_startup)
    
    # Start bot
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped!")
import asyncio
import logging
import hashlib
from datetime import timedelta
import aiosqlite
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from cryptography.fernet import Fernet
import json
import os
from datetime import datetime, timezone
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Константы и конфигурация
BOT_TOKEN = "8163139120:AAG2M8UJ5NPJdKGQlepMz4jSMUX1R7uXMI4"
OWNER_ID = 6673580092  # Защищенный ID владельца
REVIEW_CHANNEL_ID = -1002166881231
DATABASE_PATH = "bot_database.db"
ENCRYPTION_KEY = Fernet.generate_key()
fernet = Fernet(ENCRYPTION_KEY)

# Списки для хранения различных типов администраторов
MAIN_ADMINS = []  # Список главных администраторов
MODERATORS = []   # Список модераторов

# Конфигурация логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Класс для работы с базой данных
class Database:
    def __init__(self):
        self.db_path = DATABASE_PATH
        self.fernet = fernet

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица пользователей
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    stars INTEGER DEFAULT 0,
                    last_bonus TIMESTAMP,
                    is_banned INTEGER DEFAULT 0,
                    warnings INTEGER DEFAULT 0
                )
            ''')
            
            # Таблица рефералов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS referrals (
                    referrer_id INTEGER,
                    referred_id INTEGER,
                    FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                    FOREIGN KEY (referred_id) REFERENCES users(user_id)
                )
            ''')
            
            # Таблица заданий
            await db.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channels TEXT,
                    stars INTEGER,
                    max_users INTEGER,
                    current_users INTEGER DEFAULT 0,
                    created_by INTEGER,
                    FOREIGN KEY (created_by) REFERENCES users(user_id)
                )
            ''')
            
            # Таблица выполненных заданий
            await db.execute('''
                CREATE TABLE IF NOT EXISTS completed_tasks (
                    user_id INTEGER,
                    task_id INTEGER,
                    channel_id TEXT,
                    completion_time TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
                )
            ''')
            
            # Таблица промокодов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS promocodes (
                    code TEXT PRIMARY KEY,
                    stars INTEGER,
                    max_uses INTEGER,
                    current_uses INTEGER DEFAULT 0,
                    created_by INTEGER,
                    FOREIGN KEY (created_by) REFERENCES users(user_id)
                )
            ''')
            
            # Таблица использованных промокодов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS used_promocodes (
                    user_id INTEGER,
                    code TEXT,
                    use_time TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (code) REFERENCES promocodes(code)
                )
            ''')
            
            # Таблица заявок на вывод
            await db.execute('''
                CREATE TABLE IF NOT EXISTS withdrawal_requests (
                    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount INTEGER,
                    status TEXT,
                    request_time TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS daily_bonus (
    stars INTEGER NOT NULL,
    max_claims INTEGER NOT NULL
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS bonus_claims (
    user_id INTEGER NOT NULL,
    claim_time DATETIME NOT NULL,
    stars INTEGER NOT NULL
                )
            ''')
            
            
            await db.commit()
            
class SecuritySystem:
    def __init__(self, db: Database):
        self.db = db
        self.suspicious_actions = {}
        
    async def log_suspicious_activity(self, user_id: int, action_type: str, details: str):
        async with aiosqlite.connect(self.db.db_path) as db:
            await db.execute('''
                INSERT INTO security_logs (user_id, action_type, details, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (user_id, action_type, details, datetime.utcnow()))
            await db.commit()
            
        if user_id not in self.suspicious_actions:
            self.suspicious_actions[user_id] = []
        self.suspicious_actions[user_id].append(datetime.utcnow())
        
        # Оповещение администраторов
        if len(self.suspicious_actions[user_id]) >= 3:
            return True
        return False
        
    async def check_spam(self, user_id: int, action_type: str) -> bool:
        async with aiosqlite.connect(self.db.db_path) as db:
            cursor = await db.execute('''
                SELECT timestamp FROM action_logs 
                WHERE user_id = ? AND action_type = ? 
                ORDER BY timestamp DESC LIMIT 1
            ''', (user_id, action_type))
            last_action = await cursor.fetchone()
            
            if last_action:
                last_time = datetime.fromisoformat(last_action[0])
                if action_type == 'review':
                    return datetime.utcnow() - last_time < timedelta(hours=1)
                elif action_type == 'withdrawal':
                    return datetime.utcnow() - last_time < timedelta(hours=20)
            
            # Логируем действие
            await db.execute('''
                INSERT INTO action_logs (user_id, action_type, timestamp)
                VALUES (?, ?, ?)
            ''', (user_id, action_type, datetime.utcnow().isoformat()))
            await db.commit()
            return False

class UserManager:
    def __init__(self, db: Database):
        self.db = db
        
    async def add_user(self, user_id: int, first_name: str) -> bool:
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                await db.execute('''
                    INSERT OR IGNORE INTO users (user_id, first_name, stars, last_bonus)
                    VALUES (?, ?, 0, ?)
                ''', (user_id, first_name, datetime.utcnow() - timedelta(days=1)))
                await db.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False
            
    async def get_user(self, user_id: int):
        async with aiosqlite.connect(self.db.db_path) as db:
            cursor = await db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            return await cursor.fetchone()
            
    async def update_stars(self, user_id: int, stars: int):
        async with aiosqlite.connect(self.db.db_path) as db:
            await db.execute('''
                UPDATE users 
                SET stars = stars + ? 
                WHERE user_id = ?
            ''', (stars, user_id))
            await db.commit()
            
    async def get_top_users(self, limit: int = 10):
        async with aiosqlite.connect(self.db.db_path) as db:
            cursor = await db.execute('''
                SELECT first_name, stars 
                FROM users 
                WHERE is_banned = 0 
                ORDER BY stars DESC 
                LIMIT ?
            ''', (limit,))
            return await cursor.fetchall()
            
    async def check_subscription(self, user_id: int, channel_id: str):
        try:
            member = await bot.get_chat_member(channel_id, user_id)
            return member.status in ['member', 'administrator', 'creator']
        except Exception:
            return False
            
    async def add_referral(self, referrer_id: int, referred_id: int):
        async with aiosqlite.connect(self.db.db_path) as db:
            await db.execute('''
                INSERT INTO referrals (referrer_id, referred_id)
                VALUES (?, ?)
            ''', (referrer_id, referred_id))
            await db.commit()
            
    async def get_referrals_count(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db.db_path) as db:
            cursor = await db.execute('''
                SELECT COUNT(*) 
                FROM referrals 
                WHERE referrer_id = ?
            ''', (user_id,))
            result = await cursor.fetchone()
            return result[0] if result else 0
            
    async def check_ban(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db.db_path) as db:
            cursor = await db.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
            result = await cursor.fetchone()
            return bool(result[0]) if result else False
            
    async def add_warning(self, user_id: int) -> int:
        async with aiosqlite.connect(self.db.db_path) as db:
            await db.execute('''
                UPDATE users 
                SET warnings = warnings + 1 
                WHERE user_id = ?
            ''', (user_id,))
            await db.commit()
            
            cursor = await db.execute('SELECT warnings FROM users WHERE user_id = ?', (user_id,))
            result = await cursor.fetchone()
            return result[0] if result else 0
            
    async def reset_warnings(self, user_id: int):
        async with aiosqlite.connect(self.db.db_path) as db:
            await db.execute('''
                UPDATE users 
                SET warnings = 0 
                WHERE user_id = ?
            ''', (user_id,))
            await db.commit()
            
class TaskManager:
    def __init__(self, db: Database):
        self.db = db
        
    async def create_task(self, channels: list, stars: int, max_users: int, created_by: int) -> int:
        channels_str = json.dumps(channels)
        async with aiosqlite.connect(self.db.db_path) as db:
            cursor = await db.execute('''
                INSERT INTO tasks (channels, stars, max_users, created_by)
                VALUES (?, ?, ?, ?)
                RETURNING task_id
            ''', (channels_str, stars, max_users, created_by))
            await db.commit()
            task_id = await cursor.fetchone()
            return task_id[0] if task_id else None

    async def get_active_tasks(self):
        async with aiosqlite.connect(self.db.db_path) as db:
            cursor = await db.execute('''
                SELECT task_id, channels, stars, max_users, current_users
                FROM tasks
                WHERE current_users < max_users
            ''')
            tasks = await cursor.fetchall()
            return [(task[0], json.loads(task[1]), task[2], task[3], task[4]) for task in tasks]

    async def complete_task(self, task_id: int, user_id: int, channels: list):
        async with aiosqlite.connect(self.db.db_path) as db:
            # Проверяем, не выполнял ли пользователь это задание ранее
            cursor = await db.execute('''
                SELECT 1 FROM completed_tasks 
                WHERE user_id = ? AND task_id = ?
            ''', (user_id, task_id))
            if await cursor.fetchone():
                return False, "Вы уже выполняли это задание"

            # Проверяем, не выполнял ли пользователь задания с этими каналами
            for channel in channels:
                cursor = await db.execute('''
                    SELECT 1 FROM completed_tasks 
                    WHERE user_id = ? AND channel_id = ?
                ''', (user_id, channel))
                if await cursor.fetchone():
                    return False, f"Вы уже выполняли задание для канала {channel}"

            # Обновляем количество выполнений задания
            await db.execute('''
                UPDATE tasks 
                SET current_users = current_users + 1 
                WHERE task_id = ?
            ''', (task_id,))

            # Записываем выполнение задания
            for channel in channels:
                await db.execute('''
                    INSERT INTO completed_tasks (user_id, task_id, channel_id, completion_time)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, task_id, channel, datetime.utcnow()))

            await db.commit()
            return True, "Задание успешно выполнено"

    async def delete_task(self, task_id: int):
        async with aiosqlite.connect(self.db.db_path) as db:
            await db.execute('DELETE FROM tasks WHERE task_id = ?', (task_id,))
            await db.commit()

class PromoManager:
    def __init__(self, db: Database):
        self.db = db

    async def create_promo(self, code: str, stars: int, max_uses: int, created_by: int):
        async with aiosqlite.connect(self.db.db_path) as db:
            await db.execute('''
                INSERT INTO promocodes (code, stars, max_uses, created_by)
                VALUES (?, ?, ?, ?)
            ''', (code, stars, max_uses, created_by))
            await db.commit()

    async def use_promo(self, code: str, user_id: int):
        async with aiosqlite.connect(self.db.db_path) as db:
            # Проверяем существование и активность промокода
            cursor = await db.execute('''
                SELECT stars, max_uses, current_uses 
                FROM promocodes 
                WHERE code = ?
            ''', (code,))
            promo = await cursor.fetchone()
            
            if not promo:
                return False, "Промокод не существует"
                
            if promo[2] >= promo[1]:
                return False, "Промокод больше не действителен"

            # Проверяем, использовал ли пользователь этот промокод
            cursor = await db.execute('''
                SELECT 1 FROM used_promocodes 
                WHERE user_id = ? AND code = ?
            ''', (user_id, code))
            
            if await cursor.fetchone():
                return False, "Вы уже использовали этот промокод"

            # Обновляем количество использований
            await db.execute('''
                UPDATE promocodes 
                SET current_uses = current_uses + 1 
                WHERE code = ?
            ''', (code,))

            # Записываем использование промокода
            await db.execute('''
                INSERT INTO used_promocodes (user_id, code, use_time)
                VALUES (?, ?, ?)
            ''', (user_id, code, datetime.utcnow()))

            await db.commit()
            return True, promo[0]  # Возвращаем количество звезд

    async def delete_promo(self, code: str):
        async with aiosqlite.connect(self.db.db_path) as db:
            await db.execute('DELETE FROM promocodes WHERE code = ?', (code,))
            await db.commit()

class WithdrawalSystem:
    def __init__(self, db: Database):
        self.db = db

    async def create_request(self, user_id: int, amount: int):
        async with aiosqlite.connect(self.db.db_path) as db:
            # Проверяем баланс пользователя
            cursor = await db.execute('SELECT stars FROM users WHERE user_id = ?', (user_id,))
            user_stars = await cursor.fetchone()
            
            if not user_stars or user_stars[0] < amount:
                return False, "Недостаточно звезд на балансе"

            # Проверяем время последней заявки
            cursor = await db.execute('''
                SELECT request_time 
                FROM withdrawal_requests 
                WHERE user_id = ? 
                ORDER BY request_time DESC 
                LIMIT 1
            ''', (user_id,))
            last_request = await cursor.fetchone()
            
            if last_request:
                last_time = datetime.fromisoformat(last_request[0])
                if datetime.utcnow() - last_time < timedelta(hours=20):
                    return False, "Вы можете создать новую заявку через 20 часов"

            # Создаем заявку
            await db.execute('''
                INSERT INTO withdrawal_requests (user_id, amount, status, request_time)
                VALUES (?, ?, 'pending', ?)
            ''', (user_id, amount, datetime.utcnow()))
            
            # Уменьшаем баланс пользователя
            await db.execute('''
                UPDATE users 
                SET stars = stars - ? 
                WHERE user_id = ?
            ''', (amount, user_id))
            
            await db.commit()
            return True, "Заявка на вывод создана"

    async def process_request(self, request_id: int, approved: bool):
        async with aiosqlite.connect(self.db.db_path) as db:
            if approved:
                await db.execute('''
                    UPDATE withdrawal_requests 
                    SET status = 'approved' 
                    WHERE request_id = ?
                ''', (request_id,))
            else:
                # Возвращаем звезды пользователю
                cursor = await db.execute('''
                    SELECT user_id, amount 
                    FROM withdrawal_requests 
                    WHERE request_id = ?
                ''', (request_id,))
                request = await cursor.fetchone()
                
                if request:
                    await db.execute('''
                        UPDATE users 
                        SET stars = stars + ? 
                        WHERE user_id = ?
                    ''', (request[1], request[0]))
                    
                    await db.execute('''
                        UPDATE withdrawal_requests 
                        SET status = 'rejected' 
                        WHERE request_id = ?
                    ''', (request_id,))
            
            await db.commit()
            
class DailyBonus:
    def __init__(self, db: Database):
        self.db = db
        self._bonus_amount = 0
        self._max_activations = 0
        self._reset_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    async def set_bonus(self, amount: int, max_activations: int):
        self._bonus_amount = amount
        self._max_activations = max_activations
        async with aiosqlite.connect(self.db.db_path) as db:
            await db.execute('''
                UPDATE bot_settings 
                SET value = ? 
                WHERE key = 'daily_bonus_amount'
            ''', (amount,))
            await db.execute('''
                UPDATE bot_settings 
                SET value = ? 
                WHERE key = 'daily_bonus_max'
            ''', (max_activations,))
            await db.commit()

    async def claim_bonus(self, user_id: int):
        current_time = datetime.utcnow()
        if current_time.date() > self._reset_time.date():
            self._reset_time = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            async with aiosqlite.connect(self.db.db_path) as db:
                await db.execute('UPDATE daily_bonus_claims SET claimed = 0')
                await db.commit()

        async with aiosqlite.connect(self.db.db_path) as db:
            cursor = await db.execute('''
                SELECT claimed, last_claim 
                FROM daily_bonus_claims 
                WHERE user_id = ?
            ''', (user_id,))
            result = await cursor.fetchone()

            if result:
                if result[0]:
                    return False, "Вы уже получили сегодняшний бонус"
            
            cursor = await db.execute('SELECT COUNT(*) FROM daily_bonus_claims WHERE claimed = 1')
            claimed_count = (await cursor.fetchone())[0]
            
            if claimed_count >= self._max_activations:
                return False, "На сегодня все бонусы уже разобраны"

            await db.execute('''
                INSERT OR REPLACE INTO daily_bonus_claims (user_id, claimed, last_claim)
                VALUES (?, 1, ?)
            ''', (user_id, current_time))
            
            await db.execute('''
                UPDATE users 
                SET stars = stars + ? 
                WHERE user_id = ?
            ''', (self._bonus_amount, user_id))
            
            await db.commit()
            return True, self._bonus_amount

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Проверяем, забанен ли пользователь
    if await user_manager.check_ban(user_id):
        return
    
    # Проверяем, существует ли пользователь в базе
    user_data = await user_manager.get_user(user_id)
    
    if not user_data:
        # Новый пользователь
        # Проверяем реферальную ссылку
        if context.args and len(context.args) > 0:
            try:
                referrer_id = int(context.args[0])
                if referrer_id != user_id and await user_manager.get_user(referrer_id):
                    await user_manager.add_referral(referrer_id, user_id)
                    await user_manager.update_stars(referrer_id, 1)
            except ValueError:
                pass

        keyboard = []
        for channel in REQUIRED_CHANNELS:
            keyboard.append([InlineKeyboardButton(
                f"Подписаться на {channel['title']}", 
                url=channel['link']
            )])
        keyboard.append([InlineKeyboardButton("Проверить подписку ✅", callback_data="check_sub")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Добро пожаловать! Для использования бота необходимо подписаться на наши каналы:",
            reply_markup=reply_markup
        )
    else:
        # Существующий пользователь
        await show_main_menu(update, context)

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    # Проверяем подписку на все каналы
    all_subscribed = True
    for channel in REQUIRED_CHANNELS:
        if not await user_manager.check_subscription(user_id, channel['id']):
            all_subscribed = False
            break
    
    if all_subscribed:
        # Добавляем пользователя в базу
        await user_manager.add_user(user_id, query.from_user.first_name)
        await query.message.edit_text("Добро пожаловать! Теперь вы можете использовать бота.")
        await show_main_menu(update, context)
    else:
        await query.answer("Вы не подписались на все каналы!", show_alert=True)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("Заработать звезды⭐")],
        [KeyboardButton("Профиль👤"), KeyboardButton("Топ пользователей📊")],
        [KeyboardButton("Задания📚"), KeyboardButton("Промокод🎁")],
        [KeyboardButton("Вывести звёзды🌟")],
        [KeyboardButton("Ежедневный бонус📦")],
        [KeyboardButton("Оставить отзыв📧")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    message = "Главное меню:"
    if isinstance(update.callback_query, CallbackQuery):
        await update.callback_query.message.reply_text(message, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message, reply_markup=reply_markup)
        
async def earn_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if await user_manager.check_ban(user_id):
        return
        
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    
    message = (
        "🌟 Заработок звёзд\n\n"
        "За каждого приглашенного друга вы получаете 1 звезду!\n\n"
        f"Ваша реферальная ссылка:\n{ref_link}\n\n"
        "Отправьте её друзьям и получайте звёзды за каждого присоединившегося!"
    )
    await update.message.reply_text(message)

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if await user_manager.check_ban(user_id):
        return
        
    user_data = await user_manager.get_user(user_id)
    referrals_count = await user_manager.get_referrals_count(user_id)
    
    message = (
        f"👤 Профиль\n\n"
        f"Имя: {user_data[1]}\n"
        f"Баланс: {user_data[2]}⭐\n"
        f"Приглашено друзей: {referrals_count}"
    )
    await update.message.reply_text(message)

async def show_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if await user_manager.check_ban(user_id):
        return
        
    top_users = await user_manager.get_top_users(10)
    
    message = "📊 Топ 10 пользователей\n\n"
    for i, (name, stars) in enumerate(top_users, 1):
        message += f"{i}. {name} - {stars}⭐\n"
        
    await update.message.reply_text(message)

async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if await user_manager.check_ban(user_id):
        return
        
    tasks = await task_manager.get_active_tasks()
    
    if not tasks:
        await update.message.reply_text("На данный момент нет доступных заданий.")
        return
        
    for task_id, channels, stars, max_users, current_users in tasks:
        keyboard = []
        for channel in channels:
            keyboard.append([InlineKeyboardButton(
                f"Подписаться на канал", 
                url=f"https://t.me/{channel}"
            )])
        keyboard.append([InlineKeyboardButton(
            "✅ Проверить выполнение", 
            callback_data=f"check_task_{task_id}"
        )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message = (
            f"📚 Задание #{task_id}\n\n"
            f"Награда: {stars}⭐\n"
            f"Выполнено: {current_users}/{max_users}\n\n"
            "1. Подпишитесь на каналы\n"
            "2. Нажмите кнопку проверки"
        )
        await update.message.reply_text(message, reply_markup=reply_markup)

async def check_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    task_id = int(query.data.split('_')[2])
    
    if await user_manager.check_ban(user_id):
        await query.answer("Вы заблокированы!", show_alert=True)
        return

    # Проверяем, не отправлял ли уже пользователь заявку на это задание
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute('''
            SELECT status FROM task_submissions 
            WHERE user_id = ? AND task_id = ?
        ''', (user_id, task_id))
        submission = await cursor.fetchone()
        
        if submission:
            if submission[0] == 'pending':
                await query.answer("Вы уже отправили заявку на проверку!", show_alert=True)
            elif submission[0] == 'approved':
                await query.answer("Вы уже выполнили это задание!", show_alert=True)
            return

    # Запрашиваем доказательство выполнения
    await context.bot.send_message(
        user_id,
        f"📸 Отправьте фото или видео выполнения задания #{task_id}\n"
        "⚠️ У вас есть 5 минут на отправку доказательства",
        reply_markup=ForceReply()
    )
    
    # Сохраняем в контексте, что ждём доказательство для этого задания
    context.user_data['awaiting_proof'] = {
        'task_id': task_id,
        'expires': datetime.utcnow() + timedelta(minutes=5)
    }

async def handle_proof_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if 'awaiting_proof' not in context.user_data:
        return
        
    proof_data = context.user_data['awaiting_proof']
    if datetime.utcnow() > proof_data['expires']:
        await update.message.reply_text("⚠️ Время на отправку доказательства истекло!")
        del context.user_data['awaiting_proof']
        return

    task_id = proof_data['task_id']
    
    # Сохраняем заявку в базе
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            INSERT INTO task_submissions (user_id, task_id, status, submission_time)
            VALUES (?, ?, 'pending', ?)
        ''', (user_id, task_id, datetime.utcnow()))
        await db.commit()

    # Отправляем заявку модераторам
    task = await task_manager.get_task(task_id)
    
    for mod_id in MODERATORS + MAIN_ADMINS:
        try:
            # Пересылаем фото/видео модератору
            forwarded = await update.message.forward(mod_id)
            
            # Отправляем информацию о задании и кнопки для модерации
            keyboard = [
                [
                    InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{task_id}_{user_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{task_id}_{user_id}")
                ]
            ]
            await context.bot.send_message(
                mod_id,
                f"📝 Новая заявка на проверку задания\n\n"
                f"👤 Пользователь: {update.effective_user.first_name}\n"
                f"📌 ID пользователя: {user_id}\n"
                f"📋 Задание #{task_id}\n"
                f"⭐️ Награда: {task[2]} звезд",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            continue

    await update.message.reply_text(
        "✅ Доказательство отправлено на проверку модераторам!\n"
        "⏳ Ожидайте решения"
    )
    del context.user_data['awaiting_proof']

async def handle_moderation_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    mod_id = query.from_user.id
    
    if mod_id not in MODERATORS and mod_id not in MAIN_ADMINS:
        await query.answer("У вас нет прав на модерацию!", show_alert=True)
        return
        
    action, task_id, user_id = query.data.split('_')
    task_id = int(task_id)
    user_id = int(user_id)
    
    if action == 'approve':
        # Одобряем заявку
        task = await task_manager.get_task(task_id)
        stars = task[2]
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                UPDATE task_submissions 
                SET status = 'approved', 
                    moderated_by = ?,
                    moderation_time = ? 
                WHERE user_id = ? AND task_id = ?
            ''', (mod_id, datetime.utcnow(), user_id, task_id))
            
            # Начисляем звезды
            await db.execute('''
                UPDATE users 
                SET stars = stars + ? 
                WHERE user_id = ?
            ''', (stars, user_id))
            await db.commit()
            
        await query.edit_message_text(
            f"✅ Заявка одобрена модератором\n"
            f"⭐️ Начислено {stars} звезд"
        )
        
        try:
            await context.bot.send_message(
                user_id,
                f"✅ Ваша заявка на задание #{task_id} одобрена!\n"
                f"⭐️ Начислено {stars} звезд"
            )
        except Exception:
            pass
            
    elif action == 'reject':
        # Отклоняем заявку
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                UPDATE task_submissions 
                SET status = 'rejected',
                    moderated_by = ?,
                    moderation_time = ? 
                WHERE user_id = ? AND task_id = ?
            ''', (mod_id, datetime.utcnow(), user_id, task_id))
            await db.commit()
            
        await query.edit_message_text("❌ Заявка отклонена модератором")
        
        try:
            await context.bot.send_message(
                user_id,
                f"❌ Ваша заявка на задание #{task_id} отклонена!\n"
                "Попробуйте выполнить задание снова"
            )
        except Exception:
            pass

# Добавляем обрабо

async def promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if await user_manager.check_ban(user_id):
        return
        
    await update.message.reply_text(
        "Введите промокод:",
        reply_markup=ForceReply()
    )

async def handle_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    code = update.message.text.strip()
    
    if await user_manager.check_ban(user_id):
        return
        
    success, result = await promo_manager.use_promo(code, user_id)
    
    if success:
        await user_manager.update_stars(user_id, result)
        await update.message.reply_text(f"Промокод активирован! Получено {result}⭐")
    else:
        await update.message.reply_text(result)

async def withdraw_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if await user_manager.check_ban(user_id):
        return
        
    keyboard = [
        [InlineKeyboardButton("15⭐", callback_data="withdraw_15"),
         InlineKeyboardButton("25⭐", callback_data="withdraw_25")],
        [InlineKeyboardButton("50⭐", callback_data="withdraw_50"),
         InlineKeyboardButton("100⭐", callback_data="withdraw_100")],
        [InlineKeyboardButton("150⭐", callback_data="withdraw_150"),
         InlineKeyboardButton("350⭐", callback_data="withdraw_350")],
        [InlineKeyboardButton("500⭐", callback_data="withdraw_500")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Выберите количество звёзд для вывода:",
        reply_markup=reply_markup
    )

async def withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    amount = int(query.data.split('_')[1])
    
    if await user_manager.check_ban(user_id):
        return
        
    success, message = await withdrawal_system.create_request(user_id, amount)
    await query.answer(message, show_alert=True)
    
    if success:
        # Отправляем уведомление администраторам
        admin_message = (
            f"Новая заявка на вывод!\n\n"
            f"От: {query.from_user.first_name} (ID: {user_id})\n"
            f"Сумма: {amount}⭐"
        )
        for admin_id in MAIN_ADMINS:
            try:
                await context.bot.send_message(admin_id, admin_message)
            except Exception:
                continue
                
                                                                                                                                                                                                
# Административные команды
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        return
        
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Использование: /addadmin <id>")
        return
        
    try:
        new_admin_id = int(context.args[0])
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                INSERT INTO admins (admin_id, added_by, added_time)
                VALUES (?, ?, ?)
            ''', (new_admin_id, user_id, datetime.utcnow()))
            await db.commit()
        MAIN_ADMINS.append(new_admin_id)
        await update.message.reply_text(f"Администратор (ID: {new_admin_id}) успешно добавлен")
    except ValueError:
        await update.message.reply_text("Неверный формат ID")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")

async def remove_moderator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in MAIN_ADMINS and user_id != OWNER_ID:
        return
        
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Использование: /delmod <id> <причина>")
        return
        
    try:
        mod_id = int(context.args[0])
        reason = ' '.join(context.args[1:])
        
        if mod_id not in MODERATORS:
            await update.message.reply_text("Этот пользователь не является модератором!")
            return
            
        MODERATORS.remove(mod_id)
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                DELETE FROM moderators 
                WHERE mod_id = ?
            ''', (mod_id,))
            await db.commit()
            
        await update.message.reply_text(
            f"Модератор (ID: {mod_id}) удален\n"
            f"Причина: {reason}"
        )
        
        try:
            await context.bot.send_message(
                mod_id,
                f"Вы были сняты с должности модератора\n"
                f"Причина: {reason}"
            )
        except Exception:
            pass
            
    except ValueError:
        await update.message.reply_text("Неверный формат ID")
        
async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        return
        
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Использование: /deladmin <id> <причина>")
        return
        
    try:
        admin_id = int(context.args[0])
        reason = ' '.join(context.args[1:])
        
        if admin_id in MAIN_ADMINS:
            MAIN_ADMINS.remove(admin_id)
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute('''
                    DELETE FROM admins WHERE admin_id = ?
                ''', (admin_id,))
                await db.commit()
            await update.message.reply_text(f"Администратор (ID: {admin_id}) удален\nПричина: {reason}")
    except ValueError:
        await update.message.reply_text("Неверный формат ID")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")

async def add_moderator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in MAIN_ADMINS and user_id != OWNER_ID:
        return
        
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Использование: /addmod <id>")
        return
        
    try:
        mod_id = int(context.args[0])
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                INSERT INTO moderators (mod_id, added_by, added_time)
                VALUES (?, ?, ?)
            ''', (mod_id, user_id, datetime.utcnow()))
            await db.commit()
        MODERATORS.append(mod_id)
        await update.message.reply_text(f"Модератор (ID: {mod_id}) успешно добавлен")
    except ValueError:
        await update.message.reply_text("Неверный формат ID")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")

async def set_daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in MAIN_ADMINS and user_id != OWNER_ID:
        return
        
    if not context.args or len(context.args) != 2:
        await update.message.reply_text("Использование: /eb <количество звезд> <количество активаций>")
        return
        
    try:
        stars = int(context.args[0])
        max_activations = int(context.args[1])
        await daily_bonus.set_bonus(stars, max_activations)
        await update.message.reply_text(
            f"Ежедневный бонус установлен:\n"
            f"Количество звезд: {stars}\n"
            f"Максимум активаций: {max_activations}"
        )
    except ValueError:
        await update.message.reply_text("Неверный формат параметров")

async def create_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in MAIN_ADMINS and user_id != OWNER_ID:
        return
        
    if not context.args or len(context.args) != 3:
        await update.message.reply_text("Использование: /present <промокод> <макс.использований> <звезд>")
        return
        
    try:
        code = context.args[0]
        max_uses = int(context.args[1])
        stars = int(context.args[2])
        
        await promo_manager.create_promo(code, stars, max_uses, user_id)
        await update.message.reply_text(
            f"Промокод создан:\n"
            f"Код: {code}\n"
            f"Использований: {max_uses}\n"
            f"Звезд: {stars}"
        )
    except ValueError:
        await update.message.reply_text("Неверный формат параметров")

async def delete_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in MAIN_ADMINS and user_id != OWNER_ID:
        return
        
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Использование: /delp <промокод>")
        return
        
    code = context.args[0]
    await promo_manager.delete_promo(code)
    await update.message.reply_text(f"Промокод {code} удален")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in MAIN_ADMINS and user_id != OWNER_ID:
        return
        
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Использование: /ban <id> <причина>")
        return
        
    try:
        target_id = int(context.args[0])
        reason = ' '.join(context.args[1:])
        
        if target_id in MAIN_ADMINS or target_id == OWNER_ID:
            await update.message.reply_text("Невозможно забанить администратора")
            return
            
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                UPDATE users 
                SET is_banned = 1 
                WHERE user_id = ?
            ''', (target_id,))
            await db.commit()
            
        await update.message.reply_text(f"Пользователь (ID: {target_id}) забанен\nПричина: {reason}")
    except ValueError:
        await update.message.reply_text("Неверный формат ID")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in MAIN_ADMINS and user_id != OWNER_ID:
        return
        
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Использование: /unban <id>")
        return
        
    try:
        target_id = int(context.args[0])
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                UPDATE users 
                SET is_banned = 0 
                WHERE user_id = ?
            ''', (target_id,))
            await db.commit()
            
        await update.message.reply_text(f"Пользователь (ID: {target_id}) разбанен")
    except ValueError:
        await update.message.reply_text("Неверный формат ID")
        
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        
async def give_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in MAIN_ADMINS and user_id != OWNER_ID:
        return
        
    if not context.args or len(context.args) != 2:
        await update.message.reply_text("Использование: /give <id> <количество>")
        return
        
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
        await user_manager.update_stars(target_id, amount)
        await update.message.reply_text(f"Пользователю (ID: {target_id}) начислено {amount}⭐")
    except ValueError:
        await update.message.reply_text("Неверный формат параметров")

async def null_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in MAIN_ADMINS and user_id != OWNER_ID:
        return
        
    if not context.args or len(context.args) != 2:
        await update.message.reply_text("Использование: /null <id> <количество/all>")
        return
        
    try:
        target_id = int(context.args[0])
        amount = context.args[1].lower()
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            if amount == 'all':
                await db.execute('UPDATE users SET stars = 0 WHERE user_id = ?', (target_id,))
                message = f"Баланс пользователя (ID: {target_id}) полностью обнулен"
            else:
                amount = int(amount)
                cursor = await db.execute('SELECT stars FROM users WHERE user_id = ?', (target_id,))
                current_stars = (await cursor.fetchone())[0]
                
                if amount >= current_stars:
                    await db.execute('UPDATE users SET stars = 0 WHERE user_id = ?', (target_id,))
                    message = f"Баланс пользователя (ID: {target_id}) обнулен"
                else:
                    await db.execute('''
                        UPDATE users 
                        SET stars = stars - ? 
                        WHERE user_id = ?
                    ''', (amount, target_id))
                    message = f"У пользователя (ID: {target_id}) снято {amount}⭐"
                    
            await db.commit()
        await update.message.reply_text(message)
    except ValueError:
        await update.message.reply_text("Неверный формат параметров")

async def show_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in MAIN_ADMINS and user_id != OWNER_ID:
        return
        
    if not context.args or len(context.args) != 1:
        await update.message.reply_text("Использование: /user <id>")
        return
        
    try:
        target_id = int(context.args[0])
        user_data = await user_manager.get_user(target_id)
        referrals_count = await user_manager.get_referrals_count(target_id)
        
        if user_data:
            message = (
                f"👤 Информация о пользователе\n\n"
                f"ID: {user_data[0]}\n"
                f"Имя: {user_data[1]}\n"
                f"Баланс: {user_data[2]}⭐\n"
                f"Забанен: {'Да' if user_data[4] else 'Нет'}\n"
                f"Предупреждений: {user_data[5]}\n"
                f"Рефералов: {referrals_count}"
            )
        else:
            message = "Пользователь не найден"
            
        await update.message.reply_text(message)
    except ValueError:
        await update.message.reply_text("Неверный формат ID")

async def send_mass_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in MAIN_ADMINS and user_id != OWNER_ID:
        return
        
    if not context.args:
        await update.message.reply_text("Использование: /kall <текст>")
        return
        
    message = ' '.join(context.args)
    failed = 0
    success = 0
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute('SELECT user_id FROM users WHERE is_banned = 0')
        users = await cursor.fetchall()
        
        for user in users:
            try:
                await context.bot.send_message(user[0], message)
                success += 1
            except Exception:
                failed += 1
                
    await update.message.reply_text(
        f"Рассылка завершена\n"
        f"Успешно: {success}\n"
        f"Не доставлено: {failed}"
    )

async def destroy_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        return
        
    if not context.args or len(context.args) != 1:
        return
        
async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info_text = """
🤖 Информация о боте

🌟 Наш бот предлагает:
• Заработок звёзд за приглашение друзей
• Выполнение заданий с вознаграждением
• Ежедневные бонусы
• Система промокодов
• Вывод заработанных звёзд
• Рейтинг топ пользователей

💫 Как начать зарабатывать:
1. Приглашайте друзей по реферальной ссылке
2. Выполняйте задания в разделе "Задания📚"
3. Активируйте промокоды
4. Получайте ежедневный бонус

⭐ За каждого приглашенного друга вы получаете 1 звезду
🎁 Ежедневные бонусы помогут увеличить ваш баланс
📊 Попадите в топ-10 самых успешных пользователей

Удачи в заработке! 🚀
"""
    await update.message.reply_text(info_text)

async def show_admin_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in MAIN_ADMINS and user_id != OWNER_ID:
        return
        
    admin_commands = """
👨‍💼 Список административных команд:

🔰 Управление администраторами:
/addadmin <id> - Добавить администратора
/deladmin <id> <причина> - Удалить администратора
/addmod <id> - Добавить модератора
/delmod <id> <причина> - Удалить модератора

👥 Управление пользователями:
/ban <id> <причина> - Забанить пользователя
/unban <id> - Разбанить пользователя
/warn <id> <причина> - Выдать предупреждение
/user <id> - Информация о пользователе

⭐ Управление звездами:
/give <id> <количество> - Выдать звезды
/null <id> <количество/all> - Обнулить баланс

⭐ Управление звездами:
/give <id> <количество> - Выдать звезды
/null <id> <количество/all> - Обнулить баланс

🎁 Управление промокодами и бонусами:
/present <промокод> <макс.использований> <звезд> - Создать промокод
/delp <промокод> - Удалить промокод
/eb <количество звезд> <количество активаций> - Установить ежедневный бонус

📝 Управление заданиями:
/ubung <ссылки через запятую> <звезд> <макс.выполнений> - Создать задание
/delt <номер задания> - Удалить задание

📨 Коммуникация:
/kall <текст> - Массовая рассылка

🔒 Безопасность:
/destroy <код> - Уничтожить бота (только для владельца)

Примеры использования:
• Создание задания:
/ubung https://t.me/channel1, https://t.me/channel2 25 30

• Создание промокода:
/present NEWYEAR 100 50

• Выдача звезд:
/give 123456789 50

• Массовая рассылка:
/kall Всем привет! Новые задания доступны!
"""
    await update.message.reply_text(admin_commands)

# Добавьте эти обработчики в функцию main():
    
    
async def show_vip_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if await user_manager.check_ban(user_id):
        return
    
    # Получаем количество предупреждений пользователя
    user_data = await user_manager.get_user(user_id)
    warnings = user_data[5] if user_data else 0
    
    if warnings == 0:
        await update.message.reply_text("У вас нет предупреждений! 😊")
        return
        
    message = (
        "🛍 Магазин\n\n"
        "📝 Снятие 1 предупреждения\n"
        "💰 Цена: 50 звезд\n\n"
        f"❗️ У вас предупреждений: {warnings}\n"
        "⚠️ При накоплении 3-х предупреждений вы будете заблокированы!"
    )
    
    keyboard = [[InlineKeyboardButton("Снять предупреждение - 50⭐", callback_data="remove_warn")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message, reply_markup=reply_markup)

async def vip_shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if await user_manager.check_ban(user_id):
        return
        
    # Проверяем баланс и наличие предупреждений
    user_data = await user_manager.get_user(user_id)
    if not user_data:
        await query.answer("Ошибка: пользователь не найден", show_alert=True)
        return
        
    stars = user_data[2]
    warnings = user_data[5]
    
    if warnings == 0:
        await query.answer("У вас нет предупреждений!", show_alert=True)
        return
        
    if stars < 50:
        await query.answer("Недостаточно звезд! Нужно 50⭐", show_alert=True)
        return
        
    # Снимаем предупреждение и списываем звезды
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            UPDATE users 
            SET warnings = warnings - 1,
                stars = stars - 50 
            WHERE user_id = ?
        ''', (user_id,))
        await db.commit()
    
    await query.answer("Предупреждение успешно снято!", show_alert=True)
    # Обновляем сообщение с актуальной информацией
    await show_vip_shop(update, context)

# В функции main() добавляем обработчики:
    
        
    code = context.args[0]
    # Проверяем код с помощью хеша
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    
    if code_hash == DESTROY_CODE_HASH:
        await update.message.reply_text("Код подтвержден. Запуск процедуры уничтожения...")
        # Удаляем файл бота
        os.remove(__file__)
        sys.exit(0)

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверяем права на выдачу предупреждения
    if user_id not in MODERATORS and user_id not in MAIN_ADMINS and user_id != OWNER_ID:
        return
        
    # Проверяем правильность команды
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Использование: /warn <id> <причина>")
        return
        
    try:
        target_id = int(context.args[0])
        reason = ' '.join(context.args[1:])
        
        # Проверяем, не забанен ли уже пользователь
        if await user_manager.check_ban(target_id):
            await update.message.reply_text("Этот пользователь уже заблокирован!")
            return
            
        # Добавляем предупреждение
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Получаем текущее количество предупреждений
            cursor = await db.execute('''
                SELECT warnings FROM users 
                WHERE user_id = ?
            ''', (target_id,))
            result = await cursor.fetchone()
            
            if not result:
                await update.message.reply_text("Пользователь не найден в базе данных!")
                return
                
            warnings = result[0] + 1  # Увеличиваем количество предупреждений
            
            # Обновляем количество предупреждений
            await db.execute('''
                UPDATE users 
                SET warnings = ? 
                WHERE user_id = ?
            ''', (warnings, target_id))
            await db.commit()
            
            # Если достигнут лимит предупреждений - баним
            if warnings >= 3:
                await db.execute('''
                    UPDATE users 
                    SET is_banned = 1 
                    WHERE user_id = ?
                ''', (target_id,))
                await db.commit()
                
                await update.message.reply_text(
                    f"Пользователь (ID: {target_id}) получил бан\n"
                    f"Причина: достигнут лимит предупреждений (3/3)"
                )
                
                try:
                    await context.bot.send_message(
                        target_id,
                        "Вы были заблокированы за накопление 3-х предупреждений.\n"
                        "Для разблокировки обратитесь к администрации."
                    )
                except Exception:
                    pass
            else:
                await update.message.reply_text(
                    f"Выдано предупреждение пользователю (ID: {target_id})\n"
                    f"Причина: {reason}\n"
                    f"Всего предупреждений: {warnings}/3"
                )
                
                try:
                    await context.bot.send_message(
                        target_id,
                        f"Вы получили предупреждение!\n"
                        f"Причина: {reason}\n"
                        f"Всего предупреждений: {warnings}/3\n\n"
                        f"Вы можете снять предупреждение за 50⭐ в /vip_shop"
                    )
                except Exception:
                    pass
                    
    except ValueError:
        await update.message.reply_text("Неверный формат ID")
        
async def temp_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверка прав на временную блокировку
    if user_id not in MODERATORS and user_id not in MAIN_ADMINS and user_id != OWNER_ID:
        return
        
    # Проверка корректности команды
    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "Использование: /tempban <id> <часы> <причина>\n"
            "Пример: /tempban 123456789 24 Спам"
        )
        return
        
    try:
        target_id = int(context.args[0])
        hours = int(context.args[1])
        reason = ' '.join(context.args[2:])
        
        # Проверка валидности времени блокировки
        if hours < 1 or hours > 168:  # максимум 7 дней
            await update.message.reply_text(
                "Время блокировки должно быть от 1 до 168 часов (7 дней)"
            )
            return
            
        # Проверяем, не забанен ли уже пользователь
        if await user_manager.check_ban(target_id):
            await update.message.reply_text("Этот пользователь уже заблокирован!")
            return
            
        # Вычисляем время разбана
        unban_time = datetime.now(timezone.utc) + timedelta(hours=hours)
        
        # Баним пользователя
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                UPDATE users 
                SET is_banned = 1,
                    unban_time = ?,
                    ban_reason = ?
                WHERE user_id = ?
            ''', (unban_time.strftime('%Y-%m-%d %H:%M:%S'), reason, target_id))
            await db.commit()
            
        # Отправляем сообщение администратору
        await update.message.reply_text(
            f"Пользователь (ID: {target_id}) получил временный бан\n"
            f"Длительность: {hours} часов\n"
            f"Причина: {reason}\n"
            f"Разбан: {unban_time.strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )
        
        # Отправляем сообщение забаненному пользователю
        try:
            await context.bot.send_message(
                target_id,
                f"Вы получили временную блокировку!\n"
                f"Длительность: {hours} часов\n"
                f"Причина: {reason}\n"
                f"Разбан: {unban_time.strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
                "После истечения срока блокировки вы сможете снова пользоваться ботом."
            )
        except Exception:
            # Если не удалось отправить сообщение пользователю
            await update.message.reply_text(
                "Внимание: не удалось отправить уведомление пользователю"
            )
            
    except ValueError:
        await update.message.reply_text("Неверный формат ID или количества часов")
        
async def claim_daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверяем, не забанен ли пользователь
    if await user_manager.check_ban(user_id):
        await update.message.reply_text("Вы заблокированы!")
        return
        
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Получаем информацию о бонусе
            cursor = await db.execute('SELECT stars, max_claims FROM daily_bonus LIMIT 1')
            bonus_info = await cursor.fetchone()
            
            if not bonus_info:
                await update.message.reply_text("Ежедневный бонус сейчас недоступен!")
                return
                
            bonus_stars, max_claims = bonus_info
            
            # Проверяем, получал ли пользователь бонус сегодня
            current_time = datetime.now(timezone.utc)
            today_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
            
            cursor = await db.execute('''
                SELECT COUNT(*) FROM bonus_claims 
                WHERE user_id = ? AND claim_time >= ?
            ''', (user_id, today_start.strftime('%Y-%m-%d %H:%M:%S')))
            claims_today = (await cursor.fetchone())[0]
            
            # Проверяем количество активаций сегодня
            cursor = await db.execute('''
                SELECT COUNT(*) FROM bonus_claims 
                WHERE claim_time >= ?
            ''', (today_start.strftime('%Y-%m-%d %H:%M:%S'),))
            total_claims_today = (await cursor.fetchone())[0]
            
            if claims_today > 0:
                next_bonus = today_start + timedelta(days=1)
                await update.message.reply_text(
                    f"Вы уже получили сегодняшний бонус!\n"
                    f"Следующий бонус будет доступен в:\n"
                    f"{next_bonus.strftime('%Y-%m-%d')} 00:00:00 UTC"
                )
                return
                
            if total_claims_today >= max_claims:
                await update.message.reply_text(
                    "На сегодня все бонусы уже разобраны!\n"
                    "Приходите завтра!"
                )
                return
                
            # Начисляем бонус
            await db.execute('''
                INSERT INTO bonus_claims (user_id, claim_time, stars) 
                VALUES (?, ?, ?)
            ''', (user_id, current_time.strftime('%Y-%m-%d %H:%M:%S'), bonus_stars))
            
            # Обновляем баланс пользователя
            await db.execute('''
                UPDATE users 
                SET stars = stars + ? 
                WHERE user_id = ?
            ''', (bonus_stars, user_id))
            
            await db.commit()
            
            # Получаем обновленный баланс
            cursor = await db.execute('SELECT stars FROM users WHERE user_id = ?', (user_id,))
            new_balance = (await cursor.fetchone())[0]
            
            await update.message.reply_text(
                f"Вы получили ежедневный бонус: +{bonus_stars}⭐!\n"
                f"Ваш текущий баланс: {new_balance}⭐\n\n"
                f"Осталось бонусов на сегодня: {max_claims - total_claims_today - 1}"
            )
            
    except Exception as e:
        print(f"Error in claim_daily_bonus: {e}")
        await update.message.reply_text(
            "Произошла ошибка при получении бонуса.\n"
            "Пожалуйста, попробуйте позже."
        )
        
async def leave_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "Неизвестный"
    
    # Проверяем, не забанен ли пользователь
    if await user_manager.check_ban(user_id):
        await update.message.reply_text("Вы заблокированы!")
        return
        
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Проверяем, оставлял ли пользователь отзыв в последние 24 часа
            cursor = await db.execute('''
                SELECT created_at FROM reviews 
                WHERE user_id = ? 
                AND created_at > datetime('now', '-24 hours')
                ORDER BY created_at DESC LIMIT 1
            ''', (user_id,))
            last_review = await cursor.fetchone()
            
            if last_review:
                # Вычисляем, через сколько можно оставить следующий отзыв
                last_review_time = datetime.strptime(last_review[0], '%Y-%m-%d %H:%M:%S')
                next_review_time = last_review_time + timedelta(days=1)
                time_left = next_review_time - datetime.now(timezone.utc)
                hours_left = int(time_left.total_seconds() / 3600)
                minutes_left = int((time_left.total_seconds() % 3600) / 60)
                
                await update.message.reply_text(
                    f"Вы уже оставляли отзыв недавно!\n"
                    f"Следующий отзыв можно оставить через: {hours_left}ч {minutes_left}м"
                )
                return
            
            # Запрашиваем отзыв у пользователя
            await update.message.reply_text(
                "📝 Пожалуйста, напишите ваш отзыв о боте.\n"
                "⚠️ Помните:\n"
                "- Отзыв должен быть конструктивным\n"
                "- Без оскорблений и спама\n"
                "- За хороший отзыв вы получите 5⭐\n\n"
                "Отправьте ваш отзыв следующим сообщением или напишите 'отмена' для отмены."
            )
            
            # Сохраняем состояние пользователя
            context.user_data['waiting_for_review'] = True
            
    except Exception as e:
        print(f"Error in leave_review: {e}")
        await update.message.reply_text(
            "Произошла ошибка при обработке запроса.\n"
            "Пожалуйста, попробуйте позже."
        )

# Добавим также обработчик для получения текста отзыва
async def handle_review_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_review'):
        return
        
    user_id = update.effective_user.id
    username = update.effective_user.username or "Неизвестный"
    review_text = update.message.text
    
    # Очищаем состояние ожидания
    context.user_data['waiting_for_review'] = False
    
    # Проверяем отмену
    if review_text.lower() == 'отмена':
        await update.message.reply_text("Отправка отзыва отменена.")
        return
        
    # Проверяем длину отзыва
    if len(review_text) < 10:
        await update.message.reply_text(
            "Отзыв слишком короткий! Напишите не менее 10 символов."
        )
        return
        
    if len(review_text) > 500:
        await update.message.reply_text(
            "Отзыв слишком длинный! Максимальная длина - 500 символов."
        )
        return
        
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Сохраняем отзыв
            await db.execute('''
                INSERT INTO reviews (user_id, username, review_text, created_at) 
                VALUES (?, ?, ?, datetime('now'))
            ''', (user_id, username, review_text))
            
            # Начисляем награду
            await db.execute('''
                UPDATE users 
                SET stars = stars + 5 
                WHERE user_id = ?
            ''', (user_id,))
            
            await db.commit()
            
            # Отправляем подтверждение
            await update.message.reply_text(
                "Спасибо за ваш отзыв! 🎉\n"
                "Вам начислено: +5⭐"
            )
            
            # Отправляем отзыв администраторам
            for admin_id in MAIN_ADMINS:
                try:
                    await context.bot.send_message(
                        admin_id,
                        f"📝 Новый отзыв!\n"
                        f"От: @{username} (ID: {user_id})\n"
                        f"Текст: {review_text}"
                    )
                except Exception:
                    continue
                    
    except Exception as e:
        print(f"Error in handle_review_text: {e}")
        await update.message.reply_text(
            "Произошла ошибка при сохранении отзыва.\n"
            "Пожалуйста, попробуйте позже."
        )
        
                                                                                                                        
from telegram.ext import Application
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Основная функция запуска бота"""
    # Создаем бота
    bot = Application.builder().token(BOT_TOKEN).build()
    db = Database()
    
    # Создание менеджеров
    global user_manager, task_manager, promo_manager, withdrawal_system, daily_bonus
    user_manager = UserManager(db)
    task_manager = TaskManager(db)
    promo_manager = PromoManager(db)
    withdrawal_system = WithdrawalSystem(db)
    daily_bonus = DailyBonus(db)
    
    # Инициализация базы данных
    await db.init_db()
    
    # Регистрация обработчиков команд
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CommandHandler("addadmin", add_admin))
    bot.add_handler(CommandHandler("deladmin", remove_admin))
    bot.add_handler(CommandHandler("addmod", add_moderator))
    bot.add_handler(CommandHandler("delmod", remove_moderator))
    bot.add_handler(CommandHandler("ban", ban_user))
    bot.add_handler(CommandHandler("unban", unban_user))
    bot.add_handler(CommandHandler("give", give_stars))
    bot.add_handler(CommandHandler("null", null_stars))
    bot.add_handler(CommandHandler("user", show_user_info))
    bot.add_handler(CommandHandler("kall", send_mass_message))
    bot.add_handler(CommandHandler("destroy", destroy_bot))
    bot.add_handler(CommandHandler("eb", set_daily_bonus))
    bot.add_handler(CommandHandler("present", create_promo_code))
    bot.add_handler(CommandHandler("delp", delete_promo_code))
    bot.add_handler(CommandHandler("info", show_info))
    bot.add_handler(CommandHandler("vip_shop", show_vip_shop))
    bot.add_handler(CommandHandler("adc", show_admin_commands))
    bot.add_handler(CommandHandler("warn", warn_user))
    bot.add_handler(CommandHandler("tempban", temp_ban))
    
    # Регистрация обработчиков кнопок
    bot.add_handler(MessageHandler(filters.Regex("^Заработать звезды⭐$"), earn_stars))
    bot.add_handler(MessageHandler(filters.Regex("^Профиль👤$"), show_profile))
    bot.add_handler(MessageHandler(filters.Regex("^Топ пользователей📊$"), show_top))
    bot.add_handler(MessageHandler(filters.Regex("^Задания📚$"), show_tasks))
    bot.add_handler(MessageHandler(filters.Regex("^Промокод🎁$"), promo_code))
    bot.add_handler(MessageHandler(filters.Regex("^Вывести звёзды🌟$"), withdraw_stars))
    bot.add_handler(MessageHandler(filters.Regex("^Ежедневный бонус📦$"), claim_daily_bonus))
    bot.add_handler(MessageHandler(filters.Regex("^Оставить отзыв📧$"), leave_review))
    
    # Обработчик для текста отзыва
    bot.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        handle_review_text
    ))
    
    # Обработчик медиафайлов для отзывов
    bot.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.Document.ALL,
        handle_review_text
    ))
    
    # Регистрация callback обработчиков
    bot.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_sub$"))
    bot.add_handler(CallbackQueryHandler(check_task_callback, pattern="^check_task_"))
    bot.add_handler(CallbackQueryHandler(withdraw_callback, pattern="^withdraw_"))
    bot.add_handler(CallbackQueryHandler(vip_shop_callback, pattern="^remove_warn$"))
    
    # Обработчик для подтверждений выполнения заданий
    bot.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.Document.ALL,
        handle_proof_submission
    ))
    
    # Обработчик решений модераторов
    bot.add_handler(CallbackQueryHandler(
        handle_moderation_decision,
        pattern="^(approve|reject)_"
    ))
    
    logger.info("Starting bot...")
    
    # Запускаем бота
    await bot.initialize()
    await bot.start()
    await bot.run_polling(drop_pending_updates=True)

def run_bot():
    """Функция для запуска бота"""
    try:
        logger.info("Initializing bot...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user!")
    except Exception as e:
        logger.error(f"Error occurred: {e}", exc_info=True)

if __name__ == '__main__':
    run_bot()                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                
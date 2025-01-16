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
            
            script_path = os.path.abspath(file)
            
            
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

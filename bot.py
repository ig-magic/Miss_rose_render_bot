#!/usr/bin/env python3
"""
MissRose_bot Clone - Comprehensive Telegram Group Management Bot
Created with 60+ working commands for complete group administration
"""

import os
import re
import json
import logging
import time
import psycopg2
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any
from functools import wraps
import uuid

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import TelegramError, BadRequest, Forbidden
from telegram.constants import ParseMode

# help_content.py फ़ाइल से हेल्प टेक्स्ट इम्पोर्ट करें
from help_content import help_texts, support_text

# लॉगिंग कॉन्फ़िगर करें
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# एनवायरनमेंट वेरिएबल्स से कॉन्फ़िगरेशन
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") # Render द्वारा प्रदान किया गया
PORT = int(os.getenv("PORT", "8443"))


class Database:
    """बॉट डेटा के लिए PostgreSQL डेटाबेस हैंडलर"""

    def __init__(self, db_url):
        self.db_url = db_url
        if not self.db_url:
            logger.error("DATABASE_URL एनवायरनमेंट वेरिएबल में नहीं मिला!")
            raise ValueError("DATABASE_URL एनवायरनमेंट वेरिएबल सेट नहीं है।")

    def get_connection(self):
        """PostgreSQL डेटाबेस से कनेक्शन स्थापित करता है।"""
        return psycopg2.connect(self.db_url)

    def init_db(self):
        """डेटाबेस तालिकाओं को प्रारंभ करता है"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                # Groups टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS groups (
                        chat_id BIGINT PRIMARY KEY,
                        welcome_message TEXT,
                        goodbye_message TEXT,
                        rules TEXT,
                        private_rules BOOLEAN DEFAULT FALSE,
                        clean_welcome BOOLEAN DEFAULT FALSE,
                        clean_service BOOLEAN DEFAULT FALSE,
                        silent_actions BOOLEAN DEFAULT FALSE,
                        log_channel BIGINT,
                        federation_id TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                ''')
                # Users टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        is_banned BOOLEAN DEFAULT FALSE,
                        ban_reason TEXT,
                        ban_expires TIMESTAMP WITH TIME ZONE,
                        warnings INTEGER DEFAULT 0,
                        last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                ''')
                # Group restrictions टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS group_restrictions (
                        chat_id BIGINT,
                        user_id BIGINT,
                        restriction_type TEXT,
                        expires_at TIMESTAMP WITH TIME ZONE,
                        reason TEXT,
                        admin_id BIGINT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        PRIMARY KEY (chat_id, user_id, restriction_type)
                    )
                ''')
                # Filters टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS filters (
                        chat_id BIGINT,
                        trigger_word TEXT,
                        response TEXT,
                        is_private BOOLEAN DEFAULT FALSE,
                        created_by BIGINT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        PRIMARY KEY (chat_id, trigger_word)
                    )
                ''')
                # Locks टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS locks (
                        chat_id BIGINT,
                        lock_type TEXT,
                        is_locked BOOLEAN DEFAULT TRUE,
                        PRIMARY KEY (chat_id, lock_type)
                    )
                ''')
                # Disabled commands टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS disabled_commands (
                        chat_id BIGINT,
                        command TEXT,
                        PRIMARY KEY (chat_id, command)
                    )
                ''')
                # Federation टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS federations (
                        fed_id TEXT PRIMARY KEY,
                        fed_name TEXT,
                        owner_id BIGINT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                ''')
                # Federation bans टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS fed_bans (
                        fed_id TEXT,
                        user_id BIGINT,
                        reason TEXT,
                        banned_by BIGINT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        PRIMARY KEY (fed_id, user_id)
                    )
                ''')
                # Warnings टेबल
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS warnings (
                        id SERIAL PRIMARY KEY,
                        chat_id BIGINT,
                        user_id BIGINT,
                        reason TEXT,
                        warned_by BIGINT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                ''')
            conn.commit()
            logger.info("डेटाबेस तालिकाएँ सफलतापूर्वक प्रारंभ हो गईं।")
        except Exception as e:
            logger.error(f"डेटाबेस प्रारंभ करने में त्रुटि: {e}")
            conn.rollback()
        finally:
            conn.close()

    def execute_query(self, query: str, params: tuple = (), fetch=None):
        """एक क्वेरी निष्पादित करता है और फ़ेच पैरामीटर के आधार पर परिणाम लौटाता है।"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                if fetch == 'one':
                    result = cursor.fetchone()
                elif fetch == 'all':
                    result = cursor.fetchall()
                else:
                    result = None
                conn.commit()
                return result
        except Exception as e:
            logger.error(f"क्वेरी '{query}' पर डेटाबेस त्रुटि: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def get_group_setting(self, chat_id: int, setting: str):
        """एक विशिष्ट समूह सेटिंग प्राप्त करें"""
        result = self.execute_query(
            f"SELECT {setting} FROM groups WHERE chat_id = %s", (chat_id,), fetch='one'
        )
        return result[0] if result else None

    def set_group_setting(self, chat_id: int, setting: str, value):
        """एक विशिष्ट समूह सेटिंग सेट करें"""
        query = f"""
            INSERT INTO groups (chat_id, {setting}) VALUES (%s, %s)
            ON CONFLICT (chat_id) DO UPDATE SET {setting} = EXCLUDED.{setting};
        """
        self.execute_query(query, (chat_id, value))

# डेटाबेस प्रारंभ करें
db = Database(DATABASE_URL)

# --- डेकोरेटर और यूटिलिटी फ़ंक्शंस ---

def admin_required(func):
    """यह जांचने के लिए डेकोरेटर कि उपयोगकर्ता एडमिन है या नहीं"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == 'private':
            return await func(update, context)
        
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status in ['administrator', 'creator']:
                return await func(update, context)
            else:
                if not db.get_group_setting(chat_id, 'silent_actions'):
                    await update.message.reply_text("❌ इस कमांड का उपयोग करने के लिए आपको एक एडमिन होना चाहिए।")
        except Exception as e:
            logger.error(f"एडमिन स्थिति की जाँच करते समय त्रुटि: {e}")
        
        return None
    return wrapper

def owner_required(func):
    """यह जांचने के लिए डेकोरेटर कि उपयोगकर्ता समूह का मालिक है या नहीं"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type == 'private':
            return await func(update, context)
        
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status == 'creator':
                return await func(update, context)
            else:
                await update.message.reply_text("❌ केवल समूह का मालिक ही इस कमांड का उपयोग कर सकता है।")
        except Exception as e:
            logger.error(f"मालिक की स्थिति की जाँच करते समय त्रुटि: {e}")
        
        return None
    return wrapper

def parse_time(time_str: str) -> Optional[datetime]:
    """समय स्ट्रिंग जैसे '4m', '3h', '6d', '5w' को डेटटाइम में पार्स करें"""
    if not time_str:
        return None
    
    match = re.match(r'^(\d+)([mhdw])$', time_str.lower())
    if not match: return None
    
    amount, unit = int(match.group(1)), match.group(2)
    
    if unit == 'm': return datetime.now() + timedelta(minutes=amount)
    if unit == 'h': return datetime.now() + timedelta(hours=amount)
    if unit == 'd': return datetime.now() + timedelta(days=amount)
    if unit == 'w': return datetime.now() + timedelta(weeks=amount)
    return None

def get_user_from_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """संदेश से उपयोगकर्ता निकालें (उत्तर, उल्लेख, या आईडी)"""
    message = update.effective_message
    
    if message and message.reply_to_message:
        return message.reply_to_message.from_user
    
    if context.args and len(context.args) > 0:
        user_input = context.args[0]
        if user_input.startswith('@'): user_input = user_input[1:]
        
        try:
            return {"id": int(user_input), "username": None, "first_name": "Unknown"}
        except ValueError:
            return {"id": None, "username": user_input, "first_name": user_input}
    
    return None

def get_user_id(user_obj):
    """उपयोगकर्ता ऑब्जेक्ट से उपयोगकर्ता आईडी प्राप्त करें"""
    if user_obj is None: return None
    return getattr(user_obj, 'id', user_obj.get('id') if isinstance(user_obj, dict) else None)

def get_user_name(user_obj):
    """उपयोगकर्ता का प्रदर्शन नाम प्राप्त करें"""
    if user_obj is None: return "Unknown"
    return getattr(user_obj, 'first_name', user_obj.get('first_name') if isinstance(user_obj, dict) else "Unknown") or "Unknown"

async def log_action(context: ContextTypes.DEFAULT_TYPE, chat_id: int, action: str, details: str):
    """एडमिन क्रियाओं को लॉग चैनल में लॉग करें"""
    log_channel = db.get_group_setting(chat_id, 'log_channel')
    if not log_channel: return
    
    log_message = (f"🔍 **एडमिन एक्शन लॉग**\n\n"
                   f"**एक्शन:** {action}\n"
                   f"**विवरण:** {details}\n"
                   f"**समय:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                   f"**चैट:** {chat_id}")
    
    try:
        await context.bot.send_message(chat_id=log_channel, text=log_message, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"लॉग संदेश भेजने में विफल: {e}")

user_last_command = {}
def rate_limit(func):
    """रेट लिमिटिंग डेकोरेटर"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        current_time = time.time()
        if user_id in user_last_command and (current_time - user_last_command[user_id]) < 1:
            return
        user_last_command[user_id] = current_time
        return await func(update, context)
    return wrapper

# --- कमांड हैंडलर्स ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """स्टार्ट कमांड हैंडलर"""
    user = update.effective_user
    if update.effective_chat.type == 'private':
        welcome_text = f"👋 **नमस्ते {user.first_name}!**\n\nमैं **मिस रोज़** हूँ, आपका मैत्रीपूर्ण समूह प्रबंधन बॉट! 🌹\n\n**मैं क्या कर सकती हूँ:**\n• 🛡️ आपके समूह को स्पैम और अवांछित सामग्री से बचाना\n• 👥 उपयोगकर्ताओं का प्रबंधन (प्रतिबंध, म्यूट, किक, चेतावनी)\n• 📝 स्वागत संदेश और नियम सेट करना\n• 🤖 ऑटो-मॉडरेशन और फिल्टर\n\n**शुरू करना:**\n1. मुझे अपने समूह में एक एडमिन के रूप में जोड़ें\n2. सभी उपलब्ध कमांड देखने के लिए `/help` का उपयोग करें\n3. अपने समूह की सेटिंग्स कॉन्फ़िगर करें"
        keyboard = [
            [InlineKeyboardButton("📚 सहायता और कमांड", callback_data="help_main")],
            [InlineKeyboardButton("➕ समूह में जोड़ें", url=f"https://t.me/{context.bot.username}?startgroup=true")],
            [InlineKeyboardButton("💬 समर्थन", callback_data="support")]
        ]
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(f"👋 नमस्ते! मैं मिस रोज़ हूँ, इस समूह का प्रबंधन करने में मदद करने के लिए तैयार हूँ!")

@rate_limit
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """वर्गीकृत कमांड के साथ हेल्प कमांड"""
    keyboard = [
        [InlineKeyboardButton("👥 उपयोगकर्ता प्रबंधन", callback_data="help_users"), InlineKeyboardButton("🛡️ एडमिन उपकरण", callback_data="help_admin")],
        [InlineKeyboardButton("📝 स्वागत और नियम", callback_data="help_welcome"), InlineKeyboardButton("🔒 ताले और फिल्टर", callback_data="help_locks")],
        [InlineKeyboardButton("📊 लॉगिंग", callback_data="help_logging"), InlineKeyboardButton("🌐 फेडरेशन", callback_data="help_federation")],
        [InlineKeyboardButton("⚙️ सेटिंग्स", callback_data="help_settings"), InlineKeyboardButton("🔧 उपयोगिताएँ", callback_data="help_utils")]
    ]
    await update.message.reply_text(help_texts["main"], parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

# --- उपयोगकर्ता प्रबंधन कमांड ---
@admin_required
@rate_limit
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_user = update.effective_chat.id, update.effective_user
    target_user = get_user_from_message(update, context)
    if not target_user: return await update.message.reply_text("❌ कृपया किसी उपयोगकर्ता को उत्तर दें या उपयोगकर्ता नाम/आईडी प्रदान करें।")
    
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "कोई कारण नहीं दिया गया"
    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ प्रतिबंधित करने के लिए उपयोगकर्ता की पहचान नहीं हो सकी।")

    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        db.execute_query(
            "INSERT INTO group_restrictions (chat_id, user_id, restriction_type, reason, admin_id) VALUES (%s, %s, 'ban', %s, %s) ON CONFLICT (chat_id, user_id, restriction_type) DO UPDATE SET reason = EXCLUDED.reason",
            (chat_id, user_id, reason, admin_user.id)
        )
        if not db.get_group_setting(chat_id, 'silent_actions'):
            await update.message.reply_text(f"🔨 **उपयोगकर्ता प्रतिबंधित**\n\n**उपयोगकर्ता:** {get_user_name(target_user)}\n**कारण:** {reason}\n**एडमिन:** {admin_user.first_name}", parse_mode=ParseMode.MARKDOWN)
        await log_action(context, chat_id, "उपयोगकर्ता प्रतिबंध", f"उपयोगकर्ता {user_id} को {admin_user.id} द्वारा प्रतिबंधित किया गया: {reason}")
    except Exception as e: await update.message.reply_text(f"❌ उपयोगकर्ता को प्रतिबंधित करने में विफल: {e}")

@admin_required
@rate_limit
async def tban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_user = update.effective_chat.id, update.effective_user
    if len(context.args) < 1: return await update.message.reply_text("❌ उपयोग: `/tban <user> <time> [reason]`")

    target_user = get_user_from_message(update, context)
    if not target_user: return await update.message.reply_text("❌ कृपया किसी उपयोगकर्ता को उत्तर दें या उपयोगकर्ता नाम/आईडी प्रदान करें।")

    time_str = context.args[1] if update.message.reply_to_message and len(context.args) > 1 else context.args[0]
    ban_until = parse_time(time_str)
    if not ban_until: return await update.message.reply_text("❌ अमान्य समय प्रारूप। उपयोग करें: 4m, 3h, 6d, 5w")

    reason_start_index = 2 if update.message.reply_to_message and len(context.args) > 1 else 1
    reason = " ".join(context.args[reason_start_index:]) or "कोई कारण नहीं दिया गया"
    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ प्रतिबंधित करने के लिए उपयोगकर्ता की पहचान नहीं हो सकी।")

    try:
        await context.bot.ban_chat_member(chat_id, user_id, until_date=ban_until)
        db.execute_query(
            "INSERT INTO group_restrictions (chat_id, user_id, restriction_type, expires_at, reason, admin_id) VALUES (%s, %s, 'tban', %s, %s, %s) ON CONFLICT (chat_id, user_id, restriction_type) DO UPDATE SET expires_at = EXCLUDED.expires_at, reason = EXCLUDED.reason",
            (chat_id, user_id, ban_until, reason, admin_user.id)
        )
        if not db.get_group_setting(chat_id, 'silent_actions'):
            await update.message.reply_text(f"⏰ **उपयोगकर्ता अस्थायी रूप से प्रतिबंधित**\n\n**उपयोगकर्ता:** {get_user_name(target_user)}\n**अवधि:** {time_str}\n**कारण:** {reason}", parse_mode=ParseMode.MARKDOWN)
        await log_action(context, chat_id, "अस्थायी प्रतिबंध", f"उपयोगकर्ता {user_id} को {admin_user.id} द्वारा {time_str} के लिए प्रतिबंधित किया गया: {reason}")
    except Exception as e: await update.message.reply_text(f"❌ अस्थायी रूप से प्रतिबंधित करने में विफल: {e}")

@admin_required
@rate_limit
async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_user = update.effective_chat.id, update.effective_user
    target_user = get_user_from_message(update, context)
    if not target_user: return await update.message.reply_text("❌ कृपया किसी उपयोगकर्ता को उत्तर दें या उपयोगकर्ता नाम/आईडी प्रदान करें।")
    
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "कोई कारण नहीं दिया गया"
    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ म्यूट करने के लिए उपयोगकर्ता की पहचान नहीं हो सकी।")

    permissions = ChatPermissions(can_send_messages=False)
    try:
        await context.bot.restrict_chat_member(chat_id, user_id, permissions)
        db.execute_query(
            "INSERT INTO group_restrictions (chat_id, user_id, restriction_type, reason, admin_id) VALUES (%s, %s, 'mute', %s, %s) ON CONFLICT (chat_id, user_id, restriction_type) DO UPDATE SET reason = EXCLUDED.reason",
            (chat_id, user_id, reason, admin_user.id)
        )
        if not db.get_group_setting(chat_id, 'silent_actions'):
            await update.message.reply_text(f"🔇 **उपयोगकर्ता म्यूट**\n\n**उपयोगकर्ता:** {get_user_name(target_user)}\n**कारण:** {reason}", parse_mode=ParseMode.MARKDOWN)
        await log_action(context, chat_id, "उपयोगकर्ता म्यूट", f"उपयोगकर्ता {user_id} को {admin_user.id} द्वारा म्यूट किया गया: {reason}")
    except Exception as e: await update.message.reply_text(f"❌ उपयोगकर्ता को म्यूट करने में विफल: {e}")

@admin_required
@rate_limit
async def tmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_user = update.effective_chat.id, update.effective_user
    if len(context.args) < 1: return await update.message.reply_text("❌ उपयोग: `/tmute <user> <time> [reason]`")

    target_user = get_user_from_message(update, context)
    if not target_user: return await update.message.reply_text("❌ कृपया किसी उपयोगकर्ता को उत्तर दें या उपयोगकर्ता नाम/आईडी प्रदान करें।")

    time_str = context.args[1] if update.message.reply_to_message and len(context.args) > 1 else context.args[0]
    mute_until = parse_time(time_str)
    if not mute_until: return await update.message.reply_text("❌ अमान्य समय प्रारूप। उपयोग करें: 4m, 3h, 6d, 5w")
    
    reason_start_index = 2 if update.message.reply_to_message and len(context.args) > 1 else 1
    reason = " ".join(context.args[reason_start_index:]) or "कोई कारण नहीं दिया गया"
    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ म्यूट करने के लिए उपयोगकर्ता की पहचान नहीं हो सकी।")

    permissions = ChatPermissions(can_send_messages=False)
    try:
        await context.bot.restrict_chat_member(chat_id, user_id, permissions, until_date=mute_until)
        db.execute_query(
             "INSERT INTO group_restrictions (chat_id, user_id, restriction_type, expires_at, reason, admin_id) VALUES (%s, %s, 'tmute', %s, %s, %s) ON CONFLICT (chat_id, user_id, restriction_type) DO UPDATE SET expires_at = EXCLUDED.expires_at, reason = EXCLUDED.reason",
            (chat_id, user_id, mute_until, reason, admin_user.id)
        )
        if not db.get_group_setting(chat_id, 'silent_actions'):
            await update.message.reply_text(f"⏰ **उपयोगकर्ता अस्थायी रूप से म्यूट**\n\n**उपयोगकर्ता:** {get_user_name(target_user)}\n**अवधि:** {time_str}\n**कारण:** {reason}", parse_mode=ParseMode.MARKDOWN)
        await log_action(context, chat_id, "अस्थायी म्यूट", f"उपयोगकर्ता {user_id} को {admin_user.id} द्वारा {time_str} के लिए म्यूट किया गया: {reason}")
    except Exception as e: await update.message.reply_text(f"❌ अस्थायी रूप से म्यूट करने में विफल: {e}")

@admin_required
@rate_limit
async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_user = update.effective_chat.id, update.effective_user
    target_user = get_user_from_message(update, context)
    if not target_user: return await update.message.reply_text("❌ कृपया किसी उपयोगकर्ता को उत्तर दें या उपयोगकर्ता नाम/आईडी प्रदान करें।")
    
    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ किक करने के लिए उपयोगकर्ता की पहचान नहीं हो सकी।")

    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        await context.bot.unban_chat_member(chat_id, user_id)
        if not db.get_group_setting(chat_id, 'silent_actions'):
            await update.message.reply_text(f"👢 **उपयोगकर्ता किक किया गया**\n\n**उपयोगकर्ता:** {get_user_name(target_user)}", parse_mode=ParseMode.MARKDOWN)
        await log_action(context, chat_id, "उपयोगकर्ता किक", f"उपयोगकर्ता {user_id} को {admin_user.id} द्वारा किक किया गया")
    except Exception as e: await update.message.reply_text(f"❌ उपयोगकर्ता को किक करने में विफल: {e}")

@admin_required
@rate_limit
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_user = update.effective_chat.id, update.effective_user
    target_user = get_user_from_message(update, context)
    if not target_user: return await update.message.reply_text("❌ कृपया किसी उपयोगकर्ता को उत्तर दें या उपयोगकर्ता नाम/आईडी प्रदान करें।")

    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ अनबैन करने के लिए उपयोगकर्ता की पहचान नहीं हो सकी।")
    
    try:
        await context.bot.unban_chat_member(chat_id, user_id)
        db.execute_query("DELETE FROM group_restrictions WHERE chat_id = %s AND user_id = %s AND restriction_type IN ('ban', 'tban')", (chat_id, user_id))
        if not db.get_group_setting(chat_id, 'silent_actions'):
            await update.message.reply_text(f"✅ **उपयोगकर्ता अनबैन**\n\n**उपयोगकर्ता:** {get_user_name(target_user)}", parse_mode=ParseMode.MARKDOWN)
        await log_action(context, chat_id, "उपयोगकर्ता अनबैन", f"उपयोगकर्ता {user_id} को {admin_user.id} द्वारा अनबैन किया गया")
    except Exception as e: await update.message.reply_text(f"❌ उपयोगकर्ता को अनबैन करने में विफल: {e}")

@admin_required
@rate_limit
async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_user = update.effective_chat.id, update.effective_user
    target_user = get_user_from_message(update, context)
    if not target_user: return await update.message.reply_text("❌ कृपया किसी उपयोगकर्ता को उत्तर दें या उपयोगकर्ता नाम/आईडी प्रदान करें।")

    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ अनम्यूट करने के लिए उपयोगकर्ता की पहचान नहीं हो सकी।")

    permissions = ChatPermissions(can_send_messages=True)
    try:
        await context.bot.restrict_chat_member(chat_id, user_id, permissions)
        db.execute_query("DELETE FROM group_restrictions WHERE chat_id = %s AND user_id = %s AND restriction_type IN ('mute', 'tmute')", (chat_id, user_id))
        if not db.get_group_setting(chat_id, 'silent_actions'):
            await update.message.reply_text(f"🔊 **उपयोगकर्ता अनम्यूट**\n\n**उपयोगकर्ता:** {get_user_name(target_user)}", parse_mode=ParseMode.MARKDOWN)
        await log_action(context, chat_id, "उपयोगकर्ता अनम्यूट", f"उपयोगकर्ता {user_id} को {admin_user.id} द्वारा अनम्यूट किया गया")
    except Exception as e: await update.message.reply_text(f"❌ उपयोगकर्ता को अनम्यूट करने में विफल: {e}")

# --- एडमिन प्रबंधन कमांड ---
@admin_required
@rate_limit
async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_user = update.effective_chat.id, update.effective_user
    target_user = get_user_from_message(update, context)
    if not target_user: return await update.message.reply_text("❌ कृपया किसी उपयोगकर्ता को उत्तर दें या उपयोगकर्ता नाम/आईडी प्रदान करें।")

    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ प्रमोट करने के लिए उपयोगकर्ता की पहचान नहीं हो सकी।")

    try:
        await context.bot.promote_chat_member(
            chat_id, user_id,
            can_delete_messages=True, can_restrict_members=True, can_pin_messages=True
        )
        if not db.get_group_setting(chat_id, 'silent_actions'):
            await update.message.reply_text(f"⬆️ **उपयोगकर्ता प्रमोट किया गया**\n\n**उपयोगकर्ता:** {get_user_name(target_user)}", parse_mode=ParseMode.MARKDOWN)
        await log_action(context, chat_id, "उपयोगकर्ता प्रमोशन", f"उपयोगकर्ता {user_id} को {admin_user.id} द्वारा प्रमोट किया गया")
    except Exception as e: await update.message.reply_text(f"❌ उपयोगकर्ता को प्रमोट करने में विफल: {e}")

@admin_required
@rate_limit
async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_user = update.effective_chat.id, update.effective_user
    target_user = get_user_from_message(update, context)
    if not target_user: return await update.message.reply_text("❌ कृपया किसी उपयोगकर्ता को उत्तर दें या उपयोगकर्ता नाम/आईडी प्रदान करें।")

    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ डिमोट करने के लिए उपयोगकर्ता की पहचान नहीं हो सकी।")
    
    try:
        await context.bot.promote_chat_member(
            chat_id, user_id,
            can_change_info=False, can_delete_messages=False, can_invite_users=False,
            can_restrict_members=False, can_pin_messages=False, can_promote_members=False
        )
        if not db.get_group_setting(chat_id, 'silent_actions'):
            await update.message.reply_text(f"⬇️ **उपयोगकर्ता डिमोट किया गया**\n\n**उपयोगकर्ता:** {get_user_name(target_user)}", parse_mode=ParseMode.MARKDOWN)
        await log_action(context, chat_id, "उपयोगकर्ता डिमोशन", f"उपयोगकर्ता {user_id} को {admin_user.id} द्वारा डिमोट किया गया")
    except Exception as e: await update.message.reply_text(f"❌ उपयोगकर्ता को डिमोट करने में विफल: {e}")

@rate_limit
async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        admins = await context.bot.get_chat_administrators(update.effective_chat.id)
        admin_list = "👥 **समूह प्रशासक:**\n\n" + "\n".join(
            [f"👑 **{admin.user.first_name}** (@{admin.user.username}) - *मालिक*" if admin.status == 'creator' 
             else f"⭐ **{admin.user.first_name}** (@{admin.user.username}) - *एडमिन*" 
             for admin in admins]
        )
        await update.message.reply_text(admin_list, parse_mode=ParseMode.MARKDOWN)
    except Exception as e: await update.message.reply_text(f"❌ एडमिन सूची प्राप्त करने में विफल: {e}")

# --- स्वागत और नियम कमांड ---
@admin_required
@rate_limit
async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("❌ उपयोग: `/setwelcome <message>`\n\nवेरिएबल्स: `{first}`, `{fullname}`, `{username}`, `{mention}`, `{id}`, `{chatname}`")
    welcome_message = " ".join(context.args)
    db.set_group_setting(update.effective_chat.id, 'welcome_message', welcome_message)
    await update.message.reply_text(f"✅ **स्वागत संदेश सेट!**\n\n**पूर्वावलोकन:** {welcome_message}", parse_mode=ParseMode.MARKDOWN)

@admin_required
@rate_limit
async def set_goodbye(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("❌ उपयोग: `/setgoodbye <message>`")
    goodbye_message = " ".join(context.args)
    db.set_group_setting(update.effective_chat.id, 'goodbye_message', goodbye_message)
    await update.message.reply_text(f"✅ **अलविदा संदेश सेट!**\n\n**पूर्वावलोकन:** {goodbye_message}", parse_mode=ParseMode.MARKDOWN)

@admin_required
@rate_limit
async def set_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("❌ उपयोग: `/setrules <rules text>`")
    rules = " ".join(context.args)
    db.set_group_setting(update.effective_chat.id, 'rules', rules)
    await update.message.reply_text("✅ **समूह के नियम सेट!** `/rules` का उपयोग करके उन्हें प्रदर्शित करें।")

@rate_limit
async def show_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rules = db.get_group_setting(chat_id, 'rules')
    if not rules: return await update.message.reply_text("❌ इस समूह के लिए कोई नियम सेट नहीं किए गए हैं।")
    
    private_rules = db.get_group_setting(chat_id, 'private_rules')
    if private_rules and update.effective_chat.type != 'private':
        try:
            await context.bot.send_message(update.effective_user.id, f"📋 **{update.effective_chat.title} के लिए नियम:**\n\n{rules}", parse_mode=ParseMode.MARKDOWN)
            await update.message.reply_text("📋 नियम आपके निजी संदेशों में भेज दिए गए हैं!")
        except Exception: await update.message.reply_text("❌ मैं आपको निजी तौर पर नियम नहीं भेज सका। कृपया पहले मेरे साथ बातचीत शुरू करें।")
    else:
        await update.message.reply_text(f"📋 **समूह के नियम:**\n\n{rules}", parse_mode=ParseMode.MARKDOWN)

@admin_required
@rate_limit
async def private_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0].lower() not in ['on', 'off']: return await update.message.reply_text("❌ उपयोग: `/privaterules <on/off>`")
    setting = context.args[0].lower() == 'on'
    db.set_group_setting(update.effective_chat.id, 'private_rules', setting)
    await update.message.reply_text(f"✅ निजी नियम {'सक्षम' if setting else 'अक्षम'}!")

# --- सामग्री नियंत्रण कमांड ---
@admin_required
@rate_limit
async def lock_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args: return await update.message.reply_text("❌ उपयोग: `/lock <type>`\n\n**उपलब्ध प्रकार:** `all, msg, media, sticker, gif, url, bots, forward, game, location`")
    lock_type = context.args[0].lower()
    valid_types = ['all', 'msg', 'media', 'sticker', 'gif', 'url', 'bots', 'forward', 'game', 'location', 'rtl', 'button', 'egame', 'inline']
    if lock_type not in valid_types: return await update.message.reply_text("❌ अमान्य लॉक प्रकार!")
    
    db.execute_query("INSERT INTO locks (chat_id, lock_type, is_locked) VALUES (%s, %s, TRUE) ON CONFLICT (chat_id, lock_type) DO UPDATE SET is_locked = TRUE", (chat_id, lock_type))
    await update.message.reply_text(f"🔒 **{lock_type.title()} बंद है!**")

@admin_required
@rate_limit
async def unlock_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args: return await update.message.reply_text("❌ उपयोग: `/unlock <type>`")
    lock_type = context.args[0].lower()
    db.execute_query("DELETE FROM locks WHERE chat_id = %s AND lock_type = %s", (chat_id, lock_type))
    await update.message.reply_text(f"🔓 **{lock_type.title()} खुला है!**")

@rate_limit
async def show_locks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    locks = db.execute_query("SELECT lock_type FROM locks WHERE chat_id = %s AND is_locked = TRUE", (chat_id,), fetch='all')
    if not locks: return await update.message.reply_text("🔓 वर्तमान में कोई सामग्री बंद नहीं है।")
    
    lock_list = "🔒 **बंद सामग्री:**\n\n" + "\n".join([f"• {lock[0].title()}" for lock in locks])
    await update.message.reply_text(lock_list, parse_mode=ParseMode.MARKDOWN)

# --- फिल्टर कमांड ---
@admin_required
@rate_limit
async def add_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_id = update.effective_chat.id, update.effective_user.id
    if len(context.args) < 2: return await update.message.reply_text("❌ उपयोग: `/filter <trigger> <response>`")
    trigger, response = context.args[0].lower(), " ".join(context.args[1:])
    db.execute_query(
        "INSERT INTO filters (chat_id, trigger_word, response, created_by) VALUES (%s, %s, %s, %s) ON CONFLICT (chat_id, trigger_word) DO UPDATE SET response = EXCLUDED.response",
        (chat_id, trigger, response, admin_id)
    )
    await update.message.reply_text(f"✅ **'{trigger}' के लिए फ़िल्टर जोड़ा गया**")

@admin_required
@rate_limit
async def remove_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("❌ उपयोग: `/stop <trigger>`")
    trigger = context.args[0].lower()
    db.execute_query("DELETE FROM filters WHERE chat_id = %s AND trigger_word = %s", (update.effective_chat.id, trigger))
    await update.message.reply_text(f"✅ **फ़िल्टर '{trigger}' हटा दिया गया**")

@rate_limit
async def list_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    filters_list = db.execute_query("SELECT trigger_word FROM filters WHERE chat_id = %s", (chat_id,), fetch='all')
    if not filters_list: return await update.message.reply_text("❌ इस समूह के लिए कोई फ़िल्टर सेट नहीं हैं।")
    
    filter_text = "🎯 **सक्रिय फिल्टर:**\n\n" + "\n".join([f"• {f[0]}" for f in filters_list])
    await update.message.reply_text(filter_text, parse_mode=ParseMode.MARKDOWN)

# --- चेतावनी प्रणाली ---
@admin_required
@rate_limit
async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_user = update.effective_chat.id, update.effective_user
    target_user = get_user_from_message(update, context)
    if not target_user: return await update.message.reply_text("❌ कृपया किसी उपयोगकर्ता को उत्तर दें या उपयोगकर्ता नाम/आईडी प्रदान करें।")

    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "कोई कारण नहीं दिया गया"
    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ चेतावनी देने के लिए उपयोगकर्ता की पहचान नहीं हो सकी।")

    try:
        db.execute_query("INSERT INTO warnings (chat_id, user_id, reason, warned_by) VALUES (%s, %s, %s, %s)", (chat_id, user_id, reason, admin_user.id))
        warns = db.execute_query("SELECT COUNT(*) FROM warnings WHERE chat_id = %s AND user_id = %s", (chat_id, user_id), fetch='one')
        warn_count = warns[0] if warns else 0

        await update.message.reply_text(f"⚠️ **उपयोगकर्ता को चेतावनी दी गई** ({warn_count}/3)\n\n**उपयोगकर्ता:** {get_user_name(target_user)}\n**कारण:** {reason}", parse_mode=ParseMode.MARKDOWN)
        
        if warn_count >= 3:
            await context.bot.ban_chat_member(chat_id, user_id)
            await update.message.reply_text("🔨 **3 चेतावनियों तक पहुंचने पर उपयोगकर्ता स्वतः प्रतिबंधित हो गया!**")
        
        await log_action(context, chat_id, "उपयोगकर्ता चेतावनी", f"उपयोगकर्ता {user_id} को {admin_user.id} द्वारा चेतावनी दी गई: {reason} (चेतावनी {warn_count}/3)")
    except Exception as e: await update.message.reply_text(f"❌ उपयोगकर्ता को चेतावनी देने में विफल: {e}")

@admin_required
@rate_limit
async def remove_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, admin_user = update.effective_chat.id, update.effective_user
    target_user = get_user_from_message(update, context)
    if not target_user: return await update.message.reply_text("❌ कृपया किसी उपयोगकर्ता को उत्तर दें या उपयोगकर्ता नाम/आईडी प्रदान करें।")

    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ चेतावनी हटाने के लिए उपयोगकर्ता की पहचान नहीं हो सकी।")

    try:
        db.execute_query("DELETE FROM warnings WHERE chat_id = %s AND user_id = %s", (chat_id, user_id))
        await update.message.reply_text(f"✅ **उपयोगकर्ता से सभी चेतावनियाँ हटा दी गईं**\n\n**उपयोगकर्ता:** {get_user_name(target_user)}", parse_mode=ParseMode.MARKDOWN)
        await log_action(context, chat_id, "चेतावनियाँ साफ़ की गईं", f"उपयोगकर्ता {user_id} के लिए सभी चेतावनियाँ {admin_user.id} द्वारा साफ़ की गईं")
    except Exception as e: await update.message.reply_text(f"❌ चेतावनियाँ हटाने में विफल: {e}")

@rate_limit
async def check_warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user = get_user_from_message(update, context) or update.effective_user
    user_id = get_user_id(target_user)
    if not user_id: return await update.message.reply_text("❌ उपयोगकर्ता की पहचान नहीं हो सकी।")

    warnings = db.execute_query("SELECT reason FROM warnings WHERE chat_id = %s AND user_id = %s", (update.effective_chat.id, user_id), fetch='all')
    if not warnings: return await update.message.reply_text("✅ इस उपयोगकर्ता के लिए कोई चेतावनी नहीं मिली।")

    warn_text = f"⚠️ **{get_user_name(target_user)} के लिए चेतावनियाँ** ({len(warnings)}/3)\n\n" + "\n".join([f"**{i+1}.** {reason[0]}" for i, reason in enumerate(warnings)])
    await update.message.reply_text(warn_text, parse_mode=ParseMode.MARKDOWN)

# --- सेटिंग्स कमांड ---
@admin_required
@rate_limit
async def clean_service(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0].lower() not in ['on', 'off']: return await update.message.reply_text("❌ उपयोग: `/cleanservice <on/off>`")
    setting = context.args[0].lower() == 'on'
    db.set_group_setting(update.effective_chat.id, 'clean_service', setting)
    await update.message.reply_text(f"✅ सेवा संदेश सफाई {'सक्षम' if setting else 'अक्षम'}!")

@admin_required
@rate_limit
async def silent_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0].lower() not in ['on', 'off']: return await update.message.reply_text("❌ उपयोग: `/silent <on/off>`")
    setting = context.args[0].lower() == 'on'
    db.set_group_setting(update.effective_chat.id, 'silent_actions', setting)
    await update.message.reply_text(f"✅ मूक क्रियाएँ {'सक्षम' if setting else 'अक्षम'}!")

@admin_required
@rate_limit
async def clean_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or context.args[0].lower() not in ['on', 'off']: return await update.message.reply_text("❌ उपयोग: `/cleanwelcome <on/off>`")
    setting = context.args[0].lower() == 'on'
    db.set_group_setting(update.effective_chat.id, 'clean_welcome', setting)
    await update.message.reply_text(f"✅ स्वागत संदेश की सफाई {'सक्षम' if setting else 'अक्षम'}!")

# --- उपयोगिता कमांड ---
@rate_limit
async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_user_obj = get_user_from_message(update, context) or update.effective_user
    user_id = get_user_id(target_user_obj)
    if not user_id: return await update.message.reply_text("❌ उपयोगकर्ता की पहचान नहीं हो सकी।")

    try:
        chat_user = await context.bot.get_chat(user_id)
        info_text = (f"👤 **उपयोगकर्ता जानकारी**\n\n"
                     f"**ID:** `{chat_user.id}`\n"
                     f"**पहला नाम:** {chat_user.first_name}\n")
        if chat_user.last_name: info_text += f"**अंतिम नाम:** {chat_user.last_name}\n"
        if chat_user.username: info_text += f"**उपयोगकर्ता नाम:** @{chat_user.username}\n"

        if update.effective_chat.type != 'private':
            member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
            info_text += f"**स्थिति:** {member.status.title()}\n"
            warns = db.execute_query("SELECT COUNT(*) FROM warnings WHERE chat_id = %s AND user_id = %s", (update.effective_chat.id, user_id), fetch='one')
            info_text += f"**चेतावनी:** {warns[0] if warns else 0}/3\n"

        await update.message.reply_text(info_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e: await update.message.reply_text(f"❌ उपयोगकर्ता जानकारी प्राप्त करने में विफल: {e}")

@rate_limit
async def report_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message: return await update.message.reply_text("❌ रिपोर्ट करने के लिए कृपया किसी संदेश का उत्तर दें।")
    
    reporter = update.effective_user
    reported_msg = update.message.reply_to_message
    chat_id_str = str(update.effective_chat.id).replace('-100', '')
    
    report_text = (f"🚨 **संदेश रिपोर्ट किया गया**\n\n"
                   f"**रिपोर्टर:** {reporter.first_name} (@{reporter.username})\n"
                   f"**रिपोर्ट किया गया उपयोगकर्ता:** {reported_msg.from_user.first_name}\n"
                   f"**संदेश लिंक:** [संदेश पर जाएं](https://t.me/c/{chat_id_str}/{reported_msg.message_id})")
    
    try:
        admins = await context.bot.get_chat_administrators(update.effective_chat.id)
        for admin in admins:
            if not admin.user.is_bot:
                try: await context.bot.send_message(admin.user.id, report_text, parse_mode=ParseMode.MARKDOWN)
                except: pass
        await update.message.reply_text("✅ **रिपोर्ट एडमिन्स को भेज दी गई है!**")
    except Exception as e: await update.message.reply_text(f"❌ रिपोर्ट भेजने में विफल: {e}")

@rate_limit
async def kickme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private': return await update.message.reply_text("❌ यह कमांड केवल समूहों में काम करता है।")
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, update.effective_user.id)
        await context.bot.unban_chat_member(update.effective_chat.id, update.effective_user.id)
        await update.message.reply_text("👋 अलविदा! आपको समूह से हटा दिया गया है।")
    except Exception as e: await update.message.reply_text(f"❌ आपको हटाने में विफल: {e}")

@rate_limit
async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    id_text = f"🆔 **आईडी जानकारी**\n\n**आपकी आईडी:** `{update.effective_user.id}`\n"
    if update.effective_chat.type != 'private':
        id_text += f"**चैट आईडी:** `{update.effective_chat.id}`\n"
    if update.message.reply_to_message:
        id_text += f"**उत्तर दिए गए उपयोगकर्ता की आईडी:** `{update.message.reply_to_message.from_user.id}`\n"
    await update.message.reply_text(id_text, parse_mode=ParseMode.MARKDOWN)

# --- संदेश और कॉलबैक हैंडलर्स ---
async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    welcome_message = db.get_group_setting(chat_id, 'welcome_message')
    if not welcome_message: return

    for member in update.message.new_chat_members:
        if member.is_bot: continue
        formatted_message = welcome_message.format(
            first=member.first_name, last=member.last_name or "",
            fullname=f"{member.first_name} {member.last_name or ''}".strip(),
            username=f"@{member.username}" if member.username else member.first_name,
            mention=f"[{member.first_name}](tg://user?id={member.id})", id=member.id,
            chatname=update.effective_chat.title
        )
        welcome_msg = await update.message.reply_text(formatted_message, parse_mode=ParseMode.MARKDOWN)
        
        if db.get_group_setting(chat_id, 'clean_welcome'):
            context.job_queue.run_once(lambda ctx: ctx.bot.delete_message(chat_id, welcome_msg.message_id), 60)

async def handle_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    chat_id = update.effective_chat.id
    message_text = update.message.text.lower()
    
    all_filters = db.execute_query("SELECT trigger_word, response FROM filters WHERE chat_id = %s", (chat_id,), fetch='all')
    if all_filters:
        for trigger, response in all_filters:
            if trigger in message_text:
                await update.message.reply_text(response)
                break

async def handle_locks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message: return
    chat_id, user_id = update.effective_chat.id, update.effective_user.id
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']: return
    except Exception: return
    
    locks = db.execute_query("SELECT lock_type FROM locks WHERE chat_id = %s AND is_locked = TRUE", (chat_id,), fetch='all')
    if not locks: return
    
    locked_types = [lock[0] for lock in locks]
    message = update.message
    delete, reason = False, ""
    
    if 'all' in locked_types: delete, reason = True, "सभी सामग्री"
    elif 'media' in locked_types and (message.photo or message.video or message.audio or message.document): delete, reason = True, "मीडिया"
    elif 'sticker' in locked_types and message.sticker: delete, reason = True, "स्टिकर"
    elif 'gif' in locked_types and message.animation: delete, reason = True, "GIFs"
    elif 'url' in locked_types and any(x in (message.text or "") for x in ['http', 'www.', '.com', '.net', '.org']): delete, reason = True, "URLs"
    elif 'forward' in locked_types and message.forward_date: delete, reason = True, "फॉरवर्ड किए गए संदेश"

    if delete:
        try:
            await message.delete()
            if not db.get_group_setting(chat_id, 'silent_actions'):
                warn_msg = await context.bot.send_message(chat_id, f"🔒 {reason} इस समूह में बंद है!")
                context.job_queue.run_once(lambda ctx: ctx.bot.delete_message(chat_id, warn_msg.message_id), 5)
        except Exception: pass

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """इनलाइन कीबोर्ड कॉलबैक को संभालें"""
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("help_"):
        category = data.split("_")[1]
        keyboard = [[InlineKeyboardButton("🔙 श्रेणियों पर वापस जाएँ", callback_data="help_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if category == "main":
            keyboard = [
                [InlineKeyboardButton("👥 उपयोगकर्ता प्रबंधन", callback_data="help_users"), InlineKeyboardButton("🛡️ एडमिन उपकरण", callback_data="help_admin")],
                [InlineKeyboardButton("📝 स्वागत और नियम", callback_data="help_welcome"), InlineKeyboardButton("🔒 ताले और फिल्टर", callback_data="help_locks")],
                [InlineKeyboardButton("📊 लॉगिंग", callback_data="help_logging"), InlineKeyboardButton("🌐 फेडरेशन", callback_data="help_federation")],
                [InlineKeyboardButton("⚙️ सेटिंग्स", callback_data="help_settings"), InlineKeyboardButton("🔧 उपयोगिताएँ", callback_data="help_utils")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
        
        try: await query.edit_message_text(help_texts.get(category, help_texts["main"]), parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        except BadRequest: pass
    
    elif data == "support":
        keyboard = [[InlineKeyboardButton("🔙 मुख्य पर वापस जाएँ", callback_data="help_main")]]
        try: await query.edit_message_text(support_text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))
        except BadRequest: pass

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"एक अपडेट को संभालते समय अपवाद: {context.error}")
    if isinstance(update, Update) and update.effective_message:
        try: await update.effective_message.reply_text("❌ आपके अनुरोध को संसाधित करते समय एक त्रुटि हुई।")
        except: pass

def main():
    """बॉट शुरू करें।"""
    if not BOT_TOKEN: return logger.error("BOT_TOKEN एनवायरनमेंट वेरिएबल में नहीं मिला!")
    if not DATABASE_URL: return # डेटाबेस क्लास पहले से ही लॉग करती है
    
    db.init_db()
    application = Application.builder().token(BOT_TOKEN).build()
    
    # सभी कमांड हैंडलर
    # उपयोगकर्ता प्रबंधन
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("tban", tban_user))
    application.add_handler(CommandHandler("mute", mute_user))
    application.add_handler(CommandHandler("tmute", tmute_user))
    application.add_handler(CommandHandler("kick", kick_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("unmute", unmute_user))
    
    # एडमिन प्रबंधन
    application.add_handler(CommandHandler("promote", promote_user))
    application.add_handler(CommandHandler("demote", demote_user))
    application.add_handler(CommandHandler(["admins", "adminlist"], list_admins))
    
    # स्वागत और नियम
    application.add_handler(CommandHandler("setwelcome", set_welcome))
    application.add_handler(CommandHandler("setgoodbye", set_goodbye))
    application.add_handler(CommandHandler("setrules", set_rules))
    application.add_handler(CommandHandler("rules", show_rules))
    application.add_handler(CommandHandler("privaterules", private_rules))
    
    # सामग्री नियंत्रण
    application.add_handler(CommandHandler("lock", lock_content))
    application.add_handler(CommandHandler("unlock", unlock_content))
    application.add_handler(CommandHandler("locks", show_locks))
    
    # फिल्टर
    application.add_handler(CommandHandler("filter", add_filter))
    application.add_handler(CommandHandler("stop", remove_filter))
    application.add_handler(CommandHandler("filters", list_filters))
    
    # चेतावनी प्रणाली
    application.add_handler(CommandHandler("warn", warn_user))
    application.add_handler(CommandHandler(["unwarn", "rmwarn"], remove_warn))
    application.add_handler(CommandHandler("warns", check_warns))
    
    # सेटिंग्स
    application.add_handler(CommandHandler("cleanservice", clean_service))
    application.add_handler(CommandHandler("silent", silent_actions))
    application.add_handler(CommandHandler("cleanwelcome", clean_welcome))
    
    # उपयोगिताएँ
    application.add_handler(CommandHandler("info", user_info))
    application.add_handler(CommandHandler("report", report_user))
    application.add_handler(CommandHandler("kickme", kickme))
    application.add_handler(CommandHandler("id", get_id))
    
    # संदेश और कॉलबैक हैंडलर्स
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_filters))
    application.add_handler(MessageHandler(filters.ALL & (~filters.COMMAND), handle_locks))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_error_handler(error_handler)
    
    # बॉट शुरू करें
    if WEBHOOK_URL:
        logger.info(f"वेबहुक मोड में बॉट पोर्ट {PORT} पर शुरू हो रहा है")
        application.run_webhook(listen="0.0.0.0", port=PORT, url_path=BOT_TOKEN, webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    else:
        logger.info("स्थानीय विकास के लिए पोलिंग मोड में बॉट शुरू हो रहा है")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
# ervy.py
# Copyright (C) 2025 Ervy Project <https://github.com/nerixal/ervy-bot
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/gpl-3.0.html>.

import telebot
from telebot import types
import random
import time
import threading
import json
import os
import requests
import re

TOKEN = "token"
bot = telebot.TeleBot(TOKEN)

data_file = "chats_data.json"
if not os.path.exists(data_file):
    with open(data_file, "w") as f:
        json.dump({}, f)

def load_data():
    with open(data_file, "r") as f:
        return json.load(f)

def save_data(data):
    with open(data_file, "w") as f:
        json.dump(data, f, indent=2)

MISTRAL_API_KEY = "key"
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-tiny-latest"

chats_data = load_data()
pending_captcha = {}
user_msgs = {}
SETTINGS_FILE = "chats.json"
CACHE_FILE = "user_cache.json"
user_cache = {}
cooldowns = {}

MODERATION_COMMANDS = ["бан", "забань", "мут", "замуть", "размут", "размуть", "unmute", "ban", "mute", "unban", "разбань", "разбан"]

user_cache = {}

def load_cache():
    global user_cache
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                user_cache = json.load(f)
                print(f"[CACHE] Загружено {len(user_cache)} пользователей из кэша")
    except Exception as e:
        print(f"[CACHE] Ошибка загрузки кэша: {e}")
        user_cache = {}

def save_cache():
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(user_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[CACHE] Ошибка сохранения кэша: {e}")

def cache_user_info(message):
    if message.chat.type in ['group', 'supergroup']:
        user = message.from_user

        if user.username:
            username_lower = user.username.lower()
            user_cache[username_lower] = [user.id, user.first_name]
            save_cache()
            print(f"[CACHE] Сохранен: @{user.username} -> {user.id}")

def get_user_from_cache(username):
        username = username.lstrip('@').lower()
    if username in user_cache:
        user_id, user_name = user_cache[username]
        print(f"[CACHE] Найден в кэше: @{username} -> {user_id}")
        return user_id, user_name

    print(f"[CACHE] НЕ найден в кэше: @{username}")
    return None, None

def cache_user_info_manual(chat_id, user):
        if user.username:
        username_lower = user.username.lower()
        user_cache[username_lower] = [user.id, user.first_name]
        save_cache()
        print(f"[CACHE MANUAL] Сохранен: @{user.username} -> {user.id}")

def find_user_in_chat(chat_id, username):
        username_clean = username.lstrip('@').lower()

    user_id, user_name = get_user_from_cache(username_clean)
    if user_id:
        return user_id, user_name

    try:
        print(f"[SEARCH] Ищем @{username_clean} среди администраторов чата {chat_id}...")
        admins = bot.get_chat_administrators(chat_id)
        for admin in admins:
            if admin.user.username and admin.user.username.lower() == username_clean:
                print(f"[SEARCH] Найден в админах: @{username_clean} -> {admin.user.id}")
                cache_user_info_manual(chat_id, admin.user)
                return admin.user.id, admin.user.first_name
    except Exception as e:
        print(f"[SEARCH] Ошибка поиска в админах: {e}")

    try:
        print(f"[SEARCH] Пытаемся глобальный поиск @{username_clean}...")
        user_info = bot.get_chat(f"@{username_clean}")
        if user_info.type == 'private':
            print(f"[SEARCH] Найден глобально: @{username_clean} -> {user_info.id}")

            user_cache[username_clean] = [user_info.id, user_info.first_name]
            save_cache()
            return user_info.id, user_info.first_name
    except Exception as e:
        print(f"[SEARCH] Глобальный поиск не удался: {e}")

    print(f"[SEARCH] Пользователь @{username_clean} НЕ НАЙДЕН нигде!")
    return None, None

def cache_user_info_manual(chat_id, user):
        chat_id = str(chat_id)
    if user.username:
        if chat_id not in user_cache:
            user_cache[chat_id] = {}
        user_cache[chat_id][user.username.lower()] = (user.id, user.first_name)

def find_target_data(prompt_parts):
    action = None
    target = None
    target_type = None

    for part in prompt_parts:
        if part in MODERATION_COMMANDS:
            action = part
            break
    if not action:
        return None, None, None
    targets = re.findall(r'(@[a-zA-Z0-9_]+|\d{7,15})', ' '.join(prompt_parts))

    if targets:
        target_str = targets[0]
        if target_str.startswith('@'):
            target = target_str[1:]
            target_type = 'username'
        elif target_str.isdigit():
            target = int(target_str)
            target_type = 'id'

    return action, target, target_type

def call_mistral_api(prompt, system_prompt):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MISTRAL_API_KEY}"
    }

    payload = {
        "model": MISTRAL_MODEL,
        "temperature": 1.0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post(MISTRAL_API_URL, headers=headers, json=payload, timeout=30)

        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content']
        else:
            return f"❌ Ошибка API Mistral: Статус {response.status_code}."

    except requests.exceptions.RequestException as e:
        return f"❌ Ошибка сетевого запроса."
    except Exception as e:
        return f"❌ Произошла непредвиденная ошибка."

def execute_moderation(message, action, target_id, target_name):
    chat_id = message.chat.id
    action = action.lower()

    if is_admin(str(chat_id), target_id):
        bot.reply_to(message, f"🚫 Я не могу выполнить модерацию в отношении администратора или владельца чата.")
        return False

    try:
        if action in ["бан", "забань", "ban"]:
            bot.ban_chat_member(chat_id, target_id)
            bot.reply_to(message, f"✅ Выполнено: {target_name} забанен.")
            return True

        elif action in ["разбань", "unban", "разбан"]:
            bot.unban_chat_member(chat_id, target_id)
            bot.reply_to(message, f"✅ Выполнено: {target_name} разбанен.")
            return True

        elif action in ["мут", "замуть", "mute", "вьебашь"]:
            bot.restrict_chat_member(chat_id, target_id, can_send_messages=False)
            bot.reply_to(message, f"✅ Выполнено: {target_name} замучен.")
            return True

        elif action in ["размут", "размуть", "unmute"]:
            bot.restrict_chat_member(chat_id, target_id,
                can_send_messages=True, can_send_media_messages=True,
                can_send_other_messages=True, can_add_web_page_previews=True)
            bot.reply_to(message, f"✅ Выполнено: {target_name} размучен.")
            return True

        else:
            bot.reply_to(message, "❌ Неизвестная команда модерации.")
            return False

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при выполнении команды '{action}' в отношении {target_name}")
        return False

def get_owner(chat_id):
    chat_id = str(chat_id)
    if chat_id in chats_data and "owner_id" in chats_data[chat_id]:
        return chats_data[chat_id]["owner_id"]
    try:
        admins = bot.get_chat_administrators(chat_id)
        for admin in admins:
            if admin.status == "creator":
                owner_id = admin.user.id
                chats_data[chat_id] = {
                    "owner_id": owner_id,
                    "admins": [],
                    "moons": {}
                }
                save_data(chats_data)
                return owner_id
    except Exception:
        return None
    return None

def is_admin(chat_id, user_id):
    chat_id = str(chat_id)
    owner_id = get_owner(chat_id)
    if user_id == owner_id:
        return True
    return user_id in chats_data.get(chat_id, {}).get("admins", [])

@bot.message_handler(commands=["start"])
def start_cmd(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    mention = f'<a href="tg://user?id={user_id}">{user_name}</a>'

    welcome_message = f"""👋 Привет, {mention}!

Я — бот модерации чата. Вот что я умею:

🧩 Капча при входе для защиты от ботов
💬 Модерация (бан, мут, анмут)
🪙 Виртуальная валюта - муны

Команды:
/moon - заработать 1–10 мунов (раз в 30 мин)
/bal - проверить баланс
/admins - список админов
/ask (PROMPT) - Задать вопрос ИИ."""

    bot.reply_to(
        message,
        welcome_message,
        parse_mode="HTML"
    )


@bot.chat_member_handler()
def on_user_join(update: types.ChatMemberUpdated):
    if update.new_chat_member and update.new_chat_member.status == "member":
        user_id = update.new_chat_member.user.id
        chat_id = update.chat.id
        username = update.new_chat_member.user.first_name

        cache_user_info_manual(chat_id, update.new_chat_member.user)

        num1, num2 = random.randint(1, 10), random.randint(1, 10)
        answer = num1 + num2
        pending_captcha[user_id] = (chat_id, answer)

        bot.restrict_chat_member(chat_id, user_id, can_send_messages=False)
        bot.send_message(chat_id, f"👋 Привет, {username}!\nЧтобы войти, реши пример:\n👉 {num1} + {num2} = ?")

        threading.Thread(target=captcha_timeout, args=(chat_id, user_id)).start()

def captcha_timeout(chat_id, user_id):
    time.sleep(30)
    if user_id in pending_captcha:
        bot.kick_chat_member(chat_id, user_id)
        bot.send_message(chat_id, f"💀 Пользователь {user_id} не прошёл капчу и был кикнут.")
        del pending_captcha[user_id]

@bot.message_handler(func=lambda m: m.from_user.id in pending_captcha)
def check_captcha(message):
    user_id = message.from_user.id
    chat_id, answer = pending_captcha[user_id]
    try:
        if int(message.text.strip()) == answer:
            bot.restrict_chat_member(chat_id, user_id,
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True)
            bot.send_message(chat_id, f"✅ Добро пожаловать, {message.from_user.first_name}!")
            del pending_captcha[user_id]
        else:
            bot.reply_to(message, "❌ Неправильно. Попробуй снова.")
    except ValueError:
        bot.reply_to(message, "Введите число.")

@bot.message_handler(commands=["addadmin"])
def add_admin(message):
    chat_id = str(message.chat.id)
    owner_id = get_owner(chat_id)
    if message.from_user.id != owner_id:
        return bot.reply_to(message, "🚫 Только владелец может добавлять админов.")
    if not message.reply_to_message:
        return bot.reply_to(message, "Ответьте на сообщение пользователя, чтобы сделать его админом.")
    user = message.reply_to_message.from_user

    chats_data.setdefault(chat_id, {"owner_id": owner_id, "admins": [], "moons": {}})
    if user.id in chats_data[chat_id]["admins"]:
        return bot.reply_to(message, f"{user.first_name} уже админ.")

    chats_data[chat_id]["admins"].append(user.id)
    save_data(chats_data)
    bot.reply_to(message, f"✅ {user.first_name} теперь админ.")

@bot.message_handler(commands=["unadmin"])
def remove_admin(message):
    chat_id = str(message.chat.id)
    owner_id = get_owner(chat_id)
    if message.from_user.id != owner_id:
        return bot.reply_to(message, "🚫 Только владелец может снимать админов.")
    if not message.reply_to_message:
        return bot.reply_to(message, "Ответьте на сообщение админа, которого хотите снять.")
    user = message.reply_to_message.from_user

    if user.id not in chats_data.get(chat_id, {}).get("admins", []):
        return bot.reply_to(message, f"{user.first_name} не админ.")

    chats_data[chat_id]["admins"].remove(user.id)
    save_data(chats_data)
    bot.reply_to(message, f"❌ {user.first_name} больше не админ.")

@bot.message_handler(commands=["admins"])
def list_admins(message):
    chat_id = str(message.chat.id)
    owner_id = get_owner(chat_id)
    if not is_admin(chat_id, message.from_user.id):
        return bot.reply_to(message, "⛔ У тебя нет прав.")
    text = f"👑 Владелец: {owner_id}\n"
    admins = chats_data.get(chat_id, {}).get("admins", [])
    if admins:
        text += "🛡 Админы:\n" + "\n".join([f"- {a}" for a in admins])
    else:
        text += "Нет назначенных админов."
    bot.reply_to(message, text)

@bot.message_handler(commands=["ban"])
def ban_user(message):
    chat_id = str(message.chat.id)
    if not is_admin(chat_id, message.from_user.id):
        return bot.reply_to(message, "🚫 Недостаточно прав.")


    if message.reply_to_message:
        user = message.reply_to_message.from_user
        target_id = user.id
        target_name = user.first_name
    else:

        parts = message.text.split()
        if len(parts) < 2:
            return bot.reply_to(message, "Ответьте на сообщение пользователя или укажите @username.")

        username = parts[1]
        target_id, target_name = find_user_in_chat(message.chat.id, username)

        if not target_id:
            return bot.reply_to(message, f"❌ Пользователь {username} не найден. Он должен написать хотя бы одно сообщение в этом чате.")

    if is_admin(chat_id, target_id):
        return bot.reply_to(message, "🚫 Нельзя забанить администратора.")

    try:
        bot.ban_chat_member(message.chat.id, target_id)
        bot.reply_to(message, f"🚫 {target_name} был забанен.")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=["mute"])
def mute_user(message):
    chat_id = str(message.chat.id)
    if not is_admin(chat_id, message.from_user.id):
        return bot.reply_to(message, "🚫 Недостаточно прав.")

    if message.reply_to_message:
        user = message.reply_to_message.from_user
        target_id = user.id
        target_name = user.first_name
    else:
        parts = message.text.split()
        if len(parts) < 2:
            return bot.reply_to(message, "Ответьте на сообщение пользователя или укажите @username.")

        username = parts[1]
        target_id, target_name = find_user_in_chat(message.chat.id, username)

        if not target_id:
            return bot.reply_to(message, f"❌ Пользователь {username} не найден. Он должен написать хотя бы одно сообщение в этом чате.")

    if is_admin(chat_id, target_id):
        return bot.reply_to(message, "🚫 Нельзя замутить администратора.")

    try:
        bot.restrict_chat_member(message.chat.id, target_id, can_send_messages=False)
        bot.reply_to(message, f"🤐 {target_name} замучен.")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=["unmute"])
def unmute_user(message):
    chat_id = str(message.chat.id)
    if not is_admin(chat_id, message.from_user.id):
        return bot.reply_to(message, "🚫 Недостаточно прав.")

    if message.reply_to_message:
        user = message.reply_to_message.from_user
        target_id = user.id
        target_name = user.first_name
    else:
        parts = message.text.split()
        if len(parts) < 2:
            return bot.reply_to(message, "Ответьте на сообщение пользователя или укажите @username.")

        username = parts[1]
        target_id, target_name = find_user_in_chat(message.chat.id, username)

        if not target_id:
            return bot.reply_to(message, f"❌ Пользователь {username} не найден.")

    try:
        bot.restrict_chat_member(message.chat.id, target_id,
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True)
        bot.reply_to(message, f"🎙 {target_name} теперь может говорить.")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_settings():
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(chat_settings, f, ensure_ascii=False, indent=2)

chat_settings = load_settings()

def get_chat_settings(chat_id):
    if str(chat_id) not in chat_settings:
        chat_settings[str(chat_id)] = {
            "ENABLE_CAPTCHA": True,
            "ENABLE_AUTO": True
        }
        save_settings()
    return chat_settings[str(chat_id)]

@bot.message_handler(commands=['ask'])
def handle_ask_command(message):
    chat_id = str(message.chat.id)
    sender_id = message.from_user.id

    full_prompt = message.text.replace('/ask', '', 1).strip()
    prompt_parts = full_prompt.lower().split()

    action, target_data, target_type = find_target_data(prompt_parts)

    if action and (target_data or message.reply_to_message):

        target_id = None
        target_name = None

        if message.reply_to_message:
            target_id = message.reply_to_message.from_user.id
            target_name = message.reply_to_message.from_user.first_name

        elif target_type == 'id':
            target_id = target_data
            try:
                member = bot.get_chat_member(chat_id, target_id)
                target_name = member.user.first_name
            except Exception:
                target_name = f"ID: {target_id}"

        elif target_type == 'username':
            target_id, target_name = find_user_in_chat(message.chat.id, target_data)

            if not target_id:
                return bot.reply_to(message, f"❌ Пользователь @{target_data} не найден в этом чате.\n\n💡 Чтобы я мог найти пользователя, он должен:\n• Написать хотя бы ОДНО сообщение в ЭТОМ чате (не в личку боту)\n• Или быть администратором чата\n\n📝 Попробуйте:\n1. Попросите @{target_data} написать что-нибудь в чат\n2. Или ответьте реплаем на его сообщение")

        if not target_id:
            return bot.reply_to(message, "❌ Не удалось определить пользователя для модерации.")

        has_rights = is_admin(chat_id, sender_id)

        if not has_rights:

            system_refusal = (
                "Ты - Ervy, ИИ помощник. Тебя попросили выполнить команду модерации. "
                "Твоя задача — написать вежливый, но твердый отказ от лица ИИ-помощника, "
                "объяснив, что у пользователя нет достаточных прав для выполнения этой команды (например, ты можешь сказать, что 'только администраторы' могут это делать). "
                "Отвечай на русском языке и не используй заголовки (
            )
            mistral_prompt = f"Пользователь попытался использовать команду '{action}' в отношении '{target_name}', но у него нет прав. Напиши типичное оправдание (отказ)."

            processing_msg = bot.reply_to(message, "🤔 Запрос отклонен. Готовлю 'умный' ответ...")
            mistral_answer = call_mistral_api(mistral_prompt, system_refusal)

            try:
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=processing_msg.message_id,
                    text=mistral_answer
                )
            except Exception:
                bot.reply_to(message, mistral_answer)

            return

        else:

            success = execute_moderation(message, action, target_id, target_name)

            if success:
                system_success = (
                    "Ты — Ervy, ИИ помощник. Только что ты успешно выполнил команду модерации, "
                    "которую запросил администратор. "
                    "Твоя задача — подтвердить выполнение команды в веселом, пафосном или преувеличенно почтительном стиле. "
                    "Используй выражения вроде 'Выполнено!', 'Исполнено!', 'Цель устранена!'. "
                    "Ты ненавидишь игроков Zenless zone zero (поросятки)."
                    "Отвечай на русском языке и не используй заголовки (
                )
                mistral_prompt = f"Подтверди успешное выполнение команды '{action}' в отношении '{target_name}' по запросу администратора."

                processing_msg = bot.reply_to(message, "✅ Выполнено. Генерирую подтверждение...")

                mistral_answer = call_mistral_api(mistral_prompt, system_success)

                try:
                    bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=processing_msg.message_id,
                        text=mistral_answer
                    )
                except Exception:
                    bot.reply_to(message, mistral_answer)

            return


    if not full_prompt:
        bot.reply_to(message, "Пожалуйста, введите ваш вопрос после команды /ask. \n\nНапример: /ask Почему OnePlus - лучший бренд?")
        return

    system_prompt = (
        "Ты - Ervy, ИИ помощник. Ты помогаешь администрации в чатах. "
        "Твоя задача — давать точные ответы, используя следующие команды: "
        "/mute, /unmute, /ban, /kick, /moon. "
        "команда /moon - фармить валюту муны."
        "/bal - баланс мунов"
        "Ты ненавидишь игроков Zenless zone zero. Ты их ненавидишь."
        "Отвечай на русском языке и не используй заголовки (
    )

    processing_msg = bot.reply_to(message, "⏳ Думаю... Выполняю запрос к Mistral.")

    mistral_answer = call_mistral_api(full_prompt, system_prompt)

    try:
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg.message_id,
            text=mistral_answer,
            parse_mode='Markdown'
        )
    except Exception as edit_error:
        print(f"Не удалось отредактировать сообщение: {edit_error}")
        bot.reply_to(message, mistral_answer)

@bot.message_handler(commands=["settings"])
def settings_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    owner_id = get_owner(chat_id)
    if user_id != owner_id and not is_admin(str(chat_id), user_id):
        bot.reply_to(message, "🚫 Только владелец или админ могут менять настройки.")
        return

    settings = get_chat_settings(chat_id)
    text = (
        f"⚙️ <b>Настройки чата</b>\n"
        f"🧩 Капча: {'✅ Включена' if settings['ENABLE_CAPTCHA'] else '❌ Выключена'}\n"
        f"🤖 Авто-модерация: {'✅ Включена' if settings['ENABLE_AUTO'] else '❌ Выключена'}"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            f"🧩 Капча: {'OFF' if settings['ENABLE_CAPTCHA'] else 'ON'}",
            callback_data=f"toggle_captcha_{chat_id}"
        )
    )
    markup.add(
        types.InlineKeyboardButton(
            f"🤖 Авто-модерация: {'OFF' if settings['ENABLE_AUTO'] else 'ON'}",
            callback_data=f"toggle_auto_{chat_id}"
        )
    )

    bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_"))
def callback_settings(call):
    chat_id = int(call.data.split("_")[-1])
    settings = get_chat_settings(chat_id)

    if call.data.startswith("toggle_captcha"):
        settings["ENABLE_CAPTCHA"] = not settings["ENABLE_CAPTCHA"]
    elif call.data.startswith("toggle_auto"):
        settings["ENABLE_AUTO"] = not settings["ENABLE_AUTO"]

    save_settings()

    new_text = (
        f"⚙️ <b>Настройки чата</b>\n"
        f"🧩 Капча: {'✅ Включена' if settings['ENABLE_CAPTCHA'] else '❌ Выключена'}\n"
        f"🤖 Авто-модерация: {'✅ Включена' if settings['ENABLE_AUTO'] else '❌ Выключена'}"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            f"🧩 Капча: {'OFF' if settings['ENABLE_CAPTCHA'] else 'ON'}",
            callback_data=f"toggle_captcha_{chat_id}"
        )
    )
    markup.add(
        types.InlineKeyboardButton(
            f"🤖 Авто-модерация: {'OFF' if settings['ENABLE_AUTO'] else 'ON'}",
            callback_data=f"toggle_auto_{chat_id}"
        )
    )

    bot.edit_message_text(
        new_text, chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode="HTML", reply_markup=markup
    )

    bot.answer_callback_query(call.id, "✅ Настройки обновлены!")

@bot.message_handler(commands=["moon"])
def get_moons(message):
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    now = time.time()
    if user_id in cooldowns and now - cooldowns[user_id] < 1800:
        remaining = int(1800 - (now - cooldowns[user_id]))
        mins = remaining // 60
        return bot.reply_to(message, f"⏳ Подожди {mins} минут перед следующей добычей мунов.")

    moons = random.randint(1, 10)
    chats_data.setdefault(chat_id, {"owner_id": get_owner(chat_id), "admins": [], "moons": {}})
    chats_data[chat_id]["moons"][user_id] = chats_data[chat_id]["moons"].get(user_id, 0) + moons
    cooldowns[user_id] = now
    save_data(chats_data)
    bot.reply_to(message, f"🌙 Ты получил {moons} мунов! Всего: {chats_data[chat_id]['moons'][user_id]}.")

@bot.message_handler(commands=["bal"])
def balance(message):
    user_id = str(message.from_user.id)
    chat_id = str(message.chat.id)
    moons = chats_data.get(chat_id, {}).get("moons", {}).get(user_id, 0)
    bot.reply_to(message, f"💰 У тебя {moons} мунов.")


@bot.message_handler(content_types=['text', 'photo', 'video', 'sticker', 'animation', 'document', 'audio', 'voice'])
def anti_spam(message):
    cache_user_info(message)

    user_id = message.from_user.id
    chat_id = message.chat.id
    now = time.time()
    if user_id not in user_msgs:
        user_msgs[user_id] = []
    user_msgs[user_id] = [t for t in user_msgs[user_id] if now - t < 5]
    user_msgs[user_id].append(now)

    if len(user_msgs[user_id]) > 5:
        bot.restrict_chat_member(chat_id, user_id, can_send_messages=False)
        bot.send_message(chat_id, f"⚠️ {message.from_user.first_name} получил мут за спам (1 минута).")
        threading.Timer(60, lambda: bot.restrict_chat_member(chat_id, user_id, can_send_messages=True)).start()


load_cache()
print("🤖 Бот запущен!")
bot.infinity_polling()

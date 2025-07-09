import os
import json
import time
import logging
import telebot
import gspread

from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ================== Настройки ==================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")
creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

AUTHORIZED_USERS = [123456789]  # заменить на свой Telegram ID

bot = telebot.TeleBot(BOT_TOKEN)

# ================ Логирование ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============== Авторизация Google Sheets ===============
creds = Credentials.from_service_account_info(
    json.loads(creds_json),
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly "]
)
gs = gspread.authorize(creds)
sheet = gs.open_by_url(SPREADSHEET_URL).sheet1

cached_roses = []

def refresh_cached_roses():
    global cached_roses
    try:
        cached_roses = sheet.get_all_records()
        logger.info("✅ Данные успешно загружены из Google Таблицы")
    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке данных: {e}")
        cached_roses = []

refresh_cached_roses()

# =============== Храним ID сообщений ===============
user_messages = {}

def delete_previous_messages(chat_id):
    if chat_id in user_messages:
        for msg_id in user_messages[chat_id]:
            try:
                bot.delete_message(chat_id, msg_id)
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение {msg_id}: {e}")
        user_messages[chat_id] = []

def send_typing_action(chat_id):
    bot.send_chat_action(chat_id, 'typing')
    time.sleep(0.8)

# =============== Команды ===============
@bot.message_handler(commands=['start'])
def send_welcome(message):
    delete_previous_messages(message.chat.id)
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🔎 Поиск"), KeyboardButton("📚 Каталог"))
    markup.row(KeyboardButton("📦 Заказать"), KeyboardButton("❓ Помощь"))
    msg = bot.send_message(message.chat.id, "🌸 <b>Добро пожаловать!</b>\n\nВыберите действие:", parse_mode='HTML', reply_markup=markup)
    user_messages[message.chat.id].append(msg.message_id)

@bot.message_handler(commands=['help'])
def send_help(message):
    bot.send_message(message.chat.id,
                     "💬 Бот поможет найти информацию о розах.\n"
                     "Введите название розы, чтобы начать поиск.\n"
                     "Команды:\n"
                     "/start — перезапуск бота\n"
                     "/help — помощь\n"
                     "/refresh — обновить данные (только для администратора)")

@bot.message_handler(commands=['refresh'])
def refresh_data(message):
    if message.from_user.id not in AUTHORIZED_USERS:
        bot.send_message(message.chat.id, "🚫 У вас нет доступа к этой команде.")
        return
    refresh_cached_roses()
    bot.send_message(message.chat.id, "🔄 Данные обновлены!")

# =============== Обработчики кнопок ===============
@bot.message_handler(func=lambda m: m.text == "🔎 Поиск")
def handle_search(message):
    delete_previous_messages(message.chat.id)
    msg = bot.send_message(message.chat.id, "🔍 Введите название розы:")
    user_messages[message.chat.id].append(msg.message_id)

@bot.message_handler(func=lambda m: m.text == "❓ Помощь")
def handle_help(message):
    delete_previous_messages(message.chat.id)
    msg = bot.send_message(message.chat.id, "📞 Свяжитесь с нами: @your_username")
    user_messages[message.chat.id].append(msg.message_id)

@bot.message_handler(func=lambda m: m.text == "📦 Заказать")
def handle_order(message):
    delete_previous_messages(message.chat.id)
    msg = bot.send_message(message.chat.id, "🛒 Сейчас вы можете оставить заявку. Напишите, какие сорта вас интересуют.")
    user_messages[message.chat.id].append(msg.message_id)

@bot.message_handler(func=lambda m: m.text == "📚 Каталог")
def handle_catalog(message):
    delete_previous_messages(message.chat.id)
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("Чайно-гибридные", callback_data="type_Чайно-гибридные"),
        InlineKeyboardButton("Плетистые", callback_data="type_Плетистые"),
        InlineKeyboardButton("Почвопокровные", callback_data="type_Почвопокровные"),
        InlineKeyboardButton("Флорибунда", callback_data="type_Флорибунда"),
        InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")
    ]
    keyboard.add(*buttons)
    msg = bot.send_message(message.chat.id, "📚 Выберите тип розы:", reply_markup=keyboard)
    user_messages[message.chat.id].append(msg.message_id)

# =============== Callbacks ===============
@bot.callback_query_handler(func=lambda call: call.data.startswith("type_"))
def handle_type(call):
    rose_type = call.data.replace("type_", "")
    roses = [r for r in cached_roses if r.get('Тип') == rose_type]
    if not roses:
        bot.answer_callback_query(call.id, "Нет роз этого типа")
        return

    keyboard = InlineKeyboardMarkup(row_width=1)
    for idx, rose in enumerate(roses):
        keyboard.add(InlineKeyboardButton(rose.get('Название', 'Без названия'), callback_data=f"rose_{idx}_{rose_type}"))
    keyboard.add(InlineKeyboardButton("⬅️ Назад", callback_data="back_to_catalog"))

    bot.edit_message_text("🌼 Розы этого типа:", call.message.chat.id, call.message.message_id, reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith("rose_"))
def handle_rose(call):
    _, idx, rose_type = call.data.split("_")
    idx = int(idx)
    roses = [r for r in cached_roses if r.get('Тип') == rose_type]
    if idx >= len(roses):
        bot.answer_callback_query(call.id, "Роза не найдена")
        return

    rose = roses[idx]
    caption = f"🌹 <b>{rose.get('Название', 'Без названия')}</b>\n\n{rose.get('price', 'Цена не указана')}"

    photo_url = rose.get('photo', 'https://example.com/default.jpg ')

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🪴 Уход", callback_data=f"care_{idx}_{rose_type}"),
        InlineKeyboardButton("📜 История", callback_data=f"history_{idx}_{rose_type}"),
        InlineKeyboardButton("📹 Видео", callback_data=f"video_{idx}_{rose_type}"),
        InlineKeyboardButton("📦 Описание", callback_data=f"description_{idx}_{rose_type}"),
        InlineKeyboardButton("⬅️ Назад", callback_data=f"type_{rose_type}")
    )

    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass

    msg = bot.send_photo(
        call.message.chat.id,
        photo_url,
        caption=caption,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    user_messages[call.message.chat.id].append(msg.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_menu"))
def handle_back_to_menu(call):
    delete_previous_messages(call.message.chat.id)
    send_welcome(call.message)

@bot.callback_query_handler(func=lambda call: call.data.startswith("back_to_catalog"))
def handle_back_to_catalog(call):
    handle_catalog(call.message)

# =============== Информация о розе ===============
@bot.callback_query_handler(func=lambda call: call.data.startswith(("care_", "history_", "video_", "description_")))
def handle_rose_details(call

bot.infinity_polling()

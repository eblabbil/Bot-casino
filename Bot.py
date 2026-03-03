"""
🎰 Telegram Casino Bot - аналог @banditplaybot
Виртуальное казино с балансом, играми и статистикой
"""

import os
import json
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Получаем токен из переменных окружения (безопасно)
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== КЛАССЫ ДЛЯ РАБОТЫ С ДАННЫМИ ====================

class UserData:
    """Класс для работы с данными пользователя"""
    
    def __init__(self, user_id: int, username: str = ""):
        self.user_id = user_id
        self.username = username
        self.balance = 1000  # Стартовый баланс
        self.total_bets = 0
        self.total_wins = 0
        self.total_losses = 0
        self.last_daily = None
        self.inventory = []  # Для будущих предметов
        
    def to_dict(self) -> dict:
        """Конвертация в словарь для сохранения"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "balance": self.balance,
            "total_bets": self.total_bets,
            "total_wins": self.total_wins,
            "total_losses": self.total_losses,
            "last_daily": self.last_daily.isoformat() if self.last_daily else None,
            "inventory": self.inventory
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        """Создание объекта из словаря"""
        user = cls(data["user_id"], data["username"])
        user.balance = data["balance"]
        user.total_bets = data["total_bets"]
        user.total_wins = data["total_wins"]
        user.total_losses = data["total_losses"]
        user.last_daily = datetime.fromisoformat(data["last_daily"]) if data["last_daily"] else None
        user.inventory = data.get("inventory", [])
        return user


class Database:
    """Простая база данных на JSON"""
    
    def __init__(self, filename: str = "casino_data.json"):
        self.filename = filename
        self.users: Dict[int, UserData] = {}
        self.load()
    
    def load(self):
        """Загрузка данных из файла"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for user_id, user_data in data.items():
                        self.users[int(user_id)] = UserData.from_dict(user_data)
                logger.info(f"Загружено {len(self.users)} пользователей")
        except Exception as e:
            logger.error(f"Ошибка загрузки базы данных: {e}")
    
    def save(self):
        """Сохранение данных в файл"""
        try:
            data = {}
            for user_id, user in self.users.items():
                data[str(user_id)] = user.to_dict()
            
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("База данных сохранена")
        except Exception as e:
            logger.error(f"Ошибка сохранения базы данных: {e}")
    
    def get_user(self, user_id: int, username: str = "") -> UserData:
        """Получить пользователя (создать если нет)"""
        if user_id not in self.users:
            self.users[user_id] = UserData(user_id, username)
            self.save()
        elif username and self.users[user_id].username != username:
            self.users[user_id].username = username
            self.save()
        
        return self.users[user_id]
    
    def update_user(self, user_id: int):
        """Обновить данные пользователя"""
        self.save()


# Инициализация базы данных
db = Database()


# ==================== ИГРОВЫЕ ФУНКЦИИ ====================

class SlotMachine:
    """Игровой автомат"""
    
    SYMBOLS = {
        "🍒": {"value": 2, "name": "Вишня"},
        "🍋": {"value": 3, "name": "Лимон"},
        "🍊": {"value": 4, "name": "Апельсин"},
        "🍇": {"value": 5, "name": "Виноград"},
        "💎": {"value": 10, "name": "Алмаз"},
        "7️⃣": {"value": 15, "name": "Семерка"},
        "🎰": {"value": 20, "name": "Джекпот"}
    }
    
    SYMBOLS_LIST = list(SYMBOLS.keys())
    
    @classmethod
    def spin(cls, bet: int) -> tuple:
        """
        Крутить слоты
        Возвращает (результаты, выигрыш, множитель, описание)
        """
        # Генерируем 3 случайных символа
        results = [random.choice(cls.SYMBOLS_LIST) for _ in range(3)]
        
        # Проверяем комбинации
        multiplier = 0
        
        # Три одинаковых
        if results[0] == results[1] == results[2]:
            multiplier = cls.SYMBOLS[results[0]]["value"]
        # Два одинаковых
        elif results[0] == results[1] or results[1] == results[2] or results[0] == results[2]:
            # Если есть два одинаковых, ищем какой символ
            if results[0] == results[1]:
                multiplier = cls.SYMBOLS[results[0]]["value"] * 0.5
            elif results[1] == results[2]:
                multiplier = cls.SYMBOLS[results[1]]["value"] * 0.5
            else:
                multiplier = cls.SYMBOLS[results[0]]["value"] * 0.5
        
        winnings = int(bet * multiplier) if multiplier > 0 else 0
        
        # Формируем описание
        if multiplier >= 15:
            description = "🔥 ДЖЕКПОТ! 🔥"
        elif multiplier >= 10:
            description = "✨ МЕГАВЫИГРЫШ! ✨"
        elif multiplier >= 5:
            description = "🎉 ХОРОШИЙ ВЫИГРЫШ! 🎉"
        elif multiplier > 0:
            description = "🍀 Маленький выигрыш 🍀"
        else:
            description = "😢 Повезет в следующий раз..."
        
        return results, winnings, multiplier, description


class DiceGame:
    """Игра в кости"""
    
    @classmethod
    def play(cls, bet: int, guess: str) -> tuple:
        """
        Игра в кости
        guess: 'over' (>3), 'under' (<3), 'exact' (3)
        """
        dice = random.randint(1, 6)
        win = False
        multiplier = 0
        
        if guess == "over" and dice > 3:
            win = True
            multiplier = 2
        elif guess == "under" and dice < 3:
            win = True
            multiplier = 2
        elif guess == "exact" and dice == 3:
            win = True
            multiplier = 5
        
        winnings = int(bet * multiplier) if win else 0
        
        # Результат в эмодзи
        dice_emoji = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"][dice - 1]
        
        return dice, dice_emoji, winnings, win


class CoinFlip:
    """Орёл и решка"""
    
    @classmethod
    def flip(cls, bet: int, choice: str) -> tuple:
        """
        choice: 'heads' (орёл) или 'tails' (решка)
        """
        result = random.choice(["heads", "tails"])
        win = (choice == result)
        
        winnings = bet * 2 if win else 0
        
        # Эмодзи для результата
        result_emoji = "🪙 Орёл" if result == "heads" else "🪙 Решка"
        
        return result, result_emoji, winnings, win


# ==================== ОБРАБОТЧИКИ КОМАНД ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    db.get_user(user.id, user.username or user.first_name)
    
    welcome_text = (
        f"🎰 Добро пожаловать в Casino Bot, {user.first_name}!\n\n"
        f"💰 Твой баланс: {db.get_user(user.id).balance} монет\n\n"
        f"Доступные команды:\n"
        f"🎮 /slots [ставка] - Игровой автомат\n"
        f"🎲 /dice [ставка] [больше/меньше/ровно] - Кости\n"
        f"🪙 /coinflip [ставка] [орёл/решка] - Орёл и решка\n"
        f"📊 /profile - Твой профиль и статистика\n"
        f"🎁 /daily - Ежедневный бонус\n"
        f"🏆 /top - Топ игроков\n"
        f"❓ /help - Помощь"
    )
    
    # Создаем клавиатуру
    keyboard = [
        [InlineKeyboardButton("🎰 Слоты", callback_data="menu_slots"),
         InlineKeyboardButton("🎲 Кости", callback_data="menu_dice")],
        [InlineKeyboardButton("🪙 Орёл/Решка", callback_data="menu_coinflip"),
         InlineKeyboardButton("📊 Профиль", callback_data="menu_profile")],
        [InlineKeyboardButton("🎁 Ежедневный бонус", callback_data="menu_daily")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать профиль пользователя"""
    user = update.effective_user
    user_data = db.get_user(user.id, user.username or user.first_name)
    
    # Расчет статистики
    total_games = user_data.total_bets
    win_rate = (user_data.total_wins / total_games * 100) if total_games > 0 else 0
    
    profile_text = (
        f"📊 **ПРОФИЛЬ ИГРОКА**\n\n"
        f"👤 Имя: {user.first_name}\n"
        f"🆔 ID: {user.id}\n"
        f"💰 Баланс: **{user_data.balance}** монет\n\n"
        f"📈 **Статистика:**\n"
        f"🎮 Всего игр: {total_games}\n"
        f"✅ Побед: {user_data.total_wins}\n"
        f"❌ Поражений: {user_data.total_losses}\n"
        f"📊 Процент побед: {win_rate:.1f}%"
    )
    
    await update.message.reply_text(profile_text, parse_mode='Markdown')


async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ежедневный бонус"""
    user = update.effective_user
    user_data = db.get_user(user.id, user.username or user.first_name)
    
    now = datetime.now()
    
    if user_data.last_daily:
        # Проверяем, прошло ли 24 часа
        time_diff = now - user_data.last_daily
        if time_diff < timedelta(hours=24):
            hours_left = 23 - time_diff.seconds // 3600
            minutes_left = 59 - (time_diff.seconds // 60) % 60
            await update.message.reply_text(
                f"⏳ Ты уже получал бонус! Следующий через {hours_left} ч {minutes_left} мин"
            )
            return
    
    # Начисляем бонус
    bonus = random.randint(100, 500)
    user_data.balance += bonus
    user_data.last_daily = now
    db.update_user(user.id)
    
    await update.message.reply_text(
        f"🎁 **ЕЖЕДНЕВНЫЙ БОНУС**\n\n"
        f"Ты получил {bonus} монет!\n"
        f"💰 Новый баланс: {user_data.balance} монет",
        parse_mode='Markdown'
    )


async def top_players(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Топ игроков по балансу"""
    # Сортируем пользователей по балансу
    sorted_users = sorted(db.users.values(), key=lambda x: x.balance, reverse=True)[:10]
    
    if not sorted_users:
        await update.message.reply_text("Пока нет игроков 😢")
        return
    
    top_text = "🏆 **ТОП ИГРОКОВ** 🏆\n\n"
    
    for i, user in enumerate(sorted_users, 1):
        name = user.username or f"Игрок {user.user_id}"
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🎮"
        top_text += f"{medal} {i}. {name}: **{user.balance}** монет\n"
    
    await update.message.reply_text(top_text, parse_mode='Markdown')


async def slots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для игры в слоты"""
    user = update.effective_user
    user_data = db.get_user(user.id, user.username or user.first_name)
    
    # Проверяем ставку
    if not context.args:
        await update.message.reply_text(
            f"❓ Использование: /slots [ставка]\n"
            f"💰 Твой баланс: {user_data.balance}"
        )
        return
    
    try:
        bet = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Ставка должна быть числом!")
        return
    
    # Проверка ставки
    if bet <= 0:
        await update.message.reply_text("❌ Ставка должна быть больше 0!")
        return
    
    if bet > user_data.balance:
        await update.message.reply_text(f"❌ Недостаточно средств! Баланс: {user_data.balance}")
        return
    
    # Крутим слоты
    results, winnings, multiplier, description = SlotMachine.spin(bet)
    
    # Обновляем статистику
    user_data.balance -= bet
    user_data.total_bets += 1
    
    if winnings > 0:
        user_data.balance += winnings
        user_data.total_wins += 1
    else:
        user_data.total_losses += 1
    
    db.update_user(user.id)
    
    # Формируем результат
    result_text = (
        f"🎰 **СЛОТЫ** 🎰\n\n"
        f"{' '.join(results)}\n\n"
        f"{description}\n"
        f"{'💰 ' + ('Джекпот! x' + str(multiplier) if multiplier >= 15 else 'x' + str(multiplier)) if winnings > 0 else '❌ Проигрыш'}\n\n"
        f"💰 Выигрыш: {winnings} монет\n"
        f"💵 Текущий баланс: {user_data.balance} монет"
    )
    
    await update.message.reply_text(result_text, parse_mode='Markdown')


async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для игры в кости"""
    user = update.effective_user
    user_data = db.get_user(user.id, user.username or user.first_name)
    
    # Проверяем аргументы
    if len(context.args) < 2:
        await update.message.reply_text(
            f"❓ Использование: /dice [ставка] [больше/меньше/ровно]\n"
            f"Пример: /dice 100 больше\n"
            f"💰 Твой баланс: {user_data.balance}"
        )
        return
    
    try:
        bet = int(context.args[0])
        guess = context.args[1].lower()
    except ValueError:
        await update.message.reply_text("❌ Ставка должна быть числом!")
        return
    
    # Проверка ставки
    if bet <= 0:
        await update.message.reply_text("❌ Ставка должна быть больше 0!")
        return
    
    if bet > user_data.balance:
        await update.message.reply_text(f"❌ Недостаточно средств! Баланс: {user_data.balance}")
        return
    
    # Проверка выбора
    guess_map = {
        "больше": "over",
        "over": "over",
        ">": "over",
        "меньше": "under",
        "under": "under",
        "<": "under",
        "ровно": "exact",
        "exact": "exact",
        "=": "exact"
    }
    
    if guess not in guess_map:
        await update.message.reply_text("❌ Выбери: больше, меньше или ровно")
        return
    
    # Играем
    dice, dice_emoji, winnings, win = DiceGame.play(bet, guess_map[guess])
    
    # Обновляем статистику
    user_data.balance -= bet
    user_data.total_bets += 1
    
    if win:
        user_data.balance += winnings
        user_data.total_wins += 1
    else:
        user_data.total_losses += 1
    
    db.update_user(user.id)
    
    # Результат
    result_text = (
        f"🎲 **КОСТИ** 🎲\n\n"
        f"Кубик: {dice_emoji} ({dice})\n"
        f"Твой выбор: {context.args[1]}\n\n"
        f"{'🎉 ВЫИГРЫШ! 🎉' if win else '❌ ПРОИГРЫШ'}\n\n"
        f"💰 Выигрыш: {winnings} монет\n"
        f"💵 Текущий баланс: {user_data.balance} монет"
    )
    
    await update.message.reply_text(result_text, parse_mode='Markdown')


async def coinflip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для орла и решки"""
    user = update.effective_user
    user_data = db.get_user(user.id, user.username or user.first_name)
    
    # Проверяем аргументы
    if len(context.args) < 2:
        await update.message.reply_text(
            f"❓ Использование: /coinflip [ставка] [орёл/решка]\n"
            f"Пример: /coinflip 100 орёл\n"
            f"💰 Твой баланс: {user_data.balance}"
        )
        return
    
    try:
        bet = int(context.args[0])
        choice = context.args[1].lower()
    except ValueError:
        await update.message.reply_text("❌ Ставка должна быть числом!")
        return
    
    # Проверка ставки
    if bet <= 0:
        await update.message.reply_text("❌ Ставка должна быть больше 0!")
        return
    
    if bet > user_data.balance:
        await update.message.reply_text(f"❌ Недостаточно средств! Баланс: {user_data.balance}")
        return
    
    # Проверка выбора
    choice_map = {
        "орёл": "heads",
        "орел": "heads",
        "heads": "heads",
        "решка": "tails",
        "tails": "tails"
    }
    
    if choice not in choice_map:
        await update.message.reply_text("❌ Выбери: орёл или решка")
        return
    
    # Играем
    result, result_emoji, winnings, win = CoinFlip.flip(bet, choice_map[choice])
    
    # Обновляем статистику
    user_data.balance -= bet
    user_data.total_bets += 1
    
    if win:
        user_data.balance += winnings
        user_data.total_wins += 1
    else:
        user_data.total_losses += 1
    
    db.update_user(user.id)
    
    # Результат
    user_choice_emoji = "🦅 Орёл" if choice_map[choice] == "heads" else "🪙 Решка"
    
    result_text = (
        f"🪙 **ОРЁЛ И РЕШКА** 🪙\n\n"
        f"Результат: {result_emoji}\n"
        f"Твой выбор: {user_choice_emoji}\n\n"
        f"{'🎉 ВЫИГРЫШ! 🎉' if win else '❌ ПРОИГРЫШ'}\n\n"
        f"💰 Выигрыш: {winnings} монет\n"
        f"💵 Текущий баланс: {user_data.balance} монет"
    )
    
    await update.message.reply_text(result_text, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    help_text = (
        "🎰 **КАЗИНО БОТ - ПОМОЩЬ** 🎰\n\n"
        "**ПРАВИЛА ИГР:**\n\n"
        "**🎰 Слоты**\n"
        "• Три одинаковых символа = выигрыш\n"
        "• Чем реже символ, тем выше множитель\n"
        "• Джекпот (🎰🎰🎰) = x20\n\n"
        "**🎲 Кости**\n"
        "• Угадай результат броска кубика\n"
        "• Больше 3 (>3), Меньше 3 (<3) или Ровно 3 (=3)\n"
        "• Угадал ровно 3 = x5\n\n"
        "**🪙 Орёл и Решка**\n"
        "• Классическая игра 50/50\n"
        "• Угадал = x2\n\n"
        "**ДОСТУПНЫЕ КОМАНДЫ:**\n"
        "/start - Главное меню\n"
        "/slots [ставка] - Игровой автомат\n"
        "/dice [ставка] [больше/меньше/ровно] - Кости\n"
        "/coinflip [ставка] [орёл/решка] - Орёл и решка\n"
        "/profile - Твой профиль\n"
        "/daily - Ежедневный бонус\n"
        "/top - Топ игроков\n"
        "/help - Это меню"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')


# ==================== ОБРАБОТЧИКИ КНОПОК ====================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_data = db.get_user(user.id, user.username or user.first_name)
    
    if query.data == "menu_slots":
        await query.edit_message_text(
            f"🎰 **СЛОТЫ**\n\n"
            f"💰 Твой баланс: {user_data.balance}\n\n"
            f"Используй команду:\n/slots [ставка]\n\n"
            f"Пример: /slots 100",
            parse_mode='Markdown'
        )
    
    elif query.data == "menu_dice":
        await query.edit_message_text(
            f"🎲 **КОСТИ**\n\n"
            f"💰 Твой баланс: {user_data.balance}\n\n"
            f"Используй команду:\n/dice [ставка] [больше/меньше/ровно]\n\n"
            f"Пример: /dice 100 больше",
            parse_mode='Markdown'
        )
    
    elif query.data == "menu_coinflip":
        await query.edit_message_text(
            f"🪙 **ОРЁЛ И РЕШКА**\n\n"
            f"💰 Твой баланс: {user_data.balance}\n\n"
            f"Используй команду:\n/coinflip [ставка] [орёл/решка]\n\n"
            f"Пример: /coinflip 100 орёл",
            parse_mode='Markdown'
        )
    
    elif query.data == "menu_profile":
        # Расчет статистики
        total_games = user_data.total_bets
        win_rate = (user_data.total_wins / total_games * 100) if total_games > 0 else 0
        
        profile_text = (
            f"📊 **ПРОФИЛЬ ИГРОКА**\n\n"
            f"👤 Имя: {user.first_name}\n"
            f"💰 Баланс: **{user_data.balance}** монет\n\n"
            f"📈 **Статистика:**\n"
            f"🎮 Всего игр: {total_games}\n"
            f"✅ Побед: {user_data.total_wins}\n"
            f"❌ Поражений: {user_data.total_losses}\n"
            f"📊 Процент побед: {win_rate:.1f}%"
        )
        
        keyboard = [[InlineKeyboardButton("◀ Назад", callback_data="menu_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(profile_text, parse_mode='Markdown', reply_markup=reply_markup)
    
    elif query.data == "menu_daily":
        now = datetime.now()
        
        if user_data.last_daily:
            time_diff = now - user_data.last_daily
            if time_diff < timedelta(hours=24):
                hours_left = 23 - time_diff.seconds // 3600
                minutes_left = 59 - (time_diff.seconds // 60) % 60
                await query.edit_message_text(
                    f"⏳ Ты уже получал бонус! Следующий через ~{hours_left} ч {minutes_left} мин"
                )
                return
        
        # Начисляем бонус
        bonus = random.randint(100, 500)
        user_data.balance += bonus
        user_data.last_daily = now
        db.update_user(user.id)
        
        keyboard = [[InlineKeyboardButton("◀ Назад", callback_data="menu_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🎁 **ЕЖЕДНЕВНЫЙ БОНУС**\n\n"
            f"Ты получил {bonus} монет!\n"
            f"💰 Новый баланс: {user_data.balance} монет",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    elif query.data == "menu_back":
        # Возврат в главное меню
        keyboard = [
            [InlineKeyboardButton("🎰 Слоты", callback_data="menu_slots"),
             InlineKeyboardButton("🎲 Кости", callback_data="menu_dice")],
            [InlineKeyboardButton("🪙 Орёл/Решка", callback_data="menu_coinflip"),
             InlineKeyboardButton("📊 Профиль", callback_data="menu_profile")],
            [InlineKeyboardButton("🎁 Ежедневный бонус", callback_data="menu_daily")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🎰 Главное меню\n\n💰 Твой баланс: {user_data.balance} монет",
            reply_markup=reply_markup
        )


# ==================== ОСНОВНАЯ ФУНКЦИЯ ====================

def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        print("❌ ОШИБКА: Не указан BOT_TOKEN в переменных окружения")
        return
    
    # Создаем приложение
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("daily", daily_bonus))
    app.add_handler(CommandHandler("top", top_players))
    app.add_handler(CommandHandler("slots", slots_command))
    app.add_handler(CommandHandler("dice", dice_command))
    app.add_handler(CommandHandler("coinflip", coinflip_command))
    app.add_handler(CommandHandler("help", help_command))
    
    # Обработчик кнопок
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Запускаем бота
    print("✅ Бот запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

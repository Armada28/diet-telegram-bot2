import asyncio
import aiosqlite
import os
import signal
import sys
import logging

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message

# Настройка логгинга
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен из переменных окружения
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    logger.error("Переменная BOT_TOKEN не найдена в окружении!")
    sys.exit(1)

DB_NAME = "bju_bot.db"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ─── ГРЕЧНЕВЫЙ МЕМ ───
@dp.message(F.text.lower().contains("греч"))
async def греч_мем(message: Message):
    txt = message.text.lower()
    
    food_keywords = ["съел", "сел", "скушал", "поел", "ем", "жру", "закинул", "грамм", "гр ", "кило", "порцию", "100", "200", "150"]
    
    if any(word in txt for word in food_keywords):
        await message.reply("Гречка level 100 активирован 🥣💪\nСколько уже кг сухой в тебя вошло?")
    elif any(word in txt for word in ["греция", "греческий", "афины", "олимп"]):
        await message.reply("Эй, это не та гречка, брат 😭")

# ─── СОСТОЯНИЯ ───
class Reg(StatesGroup):
    name = State()
    goal = State()

# ─── ГЛАВНАЯ КЛАВИАТУРА ───
def main_kb():
    kb = [
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="🍎 Быстрый перекус")],
        [KeyboardButton(text="♻️ Сброс дня")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=False)

# ─── ИНИЦИАЛИЗАЦИЯ БД ───
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT,
                goal REAL,
                eaten REAL DEFAULT 0
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS products (
                product_name TEXT PRIMARY KEY,
                kcal REAL
            )
        ''')
        await db.commit()

# ─── ДЕФОЛТНЫЕ ПРОДУКТЫ ───
async def add_default_products():
    products = [
        ("гречка", 313.0),
        ("капуста", 25.0),
        ("рис", 344.0),
        ("овсянка", 366.0),
        ("макароны", 371.0),
        ("картофель", 77.0),
        ("курица", 165.0),
        ("яйцо", 155.0),
        ("творог", 71.0),
        ("банан", 89.0),
    ]
    async with aiosqlite.connect(DB_NAME) as db:
        for name, kcal in products:
            await db.execute(
                "INSERT OR IGNORE INTO products (product_name, kcal) VALUES (?, ?)",
                (name.lower(), kcal)
            )
        await db.commit()
    logger.info("Добавлены дефолтные продукты")

# ─── КОМАНДЫ ───
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT name FROM users WHERE id = ?", (message.from_user.id,)) as cursor:
                user = await cursor.fetchone()
                if user:
                    await message.answer(f"С возвращением, {user[0]}!", reply_markup=main_kb())
                    return
        await message.answer("Привет! Давай зарегистрируемся. Как тебя зовут?")
        await state.set_state(Reg.name)
    except Exception as e:
        logger.error(f"Ошибка в /start: {e}")
        await message.answer("Произошла ошибка. Попробуй позже.")

@dp.message(Reg.name)
async def reg_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Имя не может быть пустым. Попробуй ещё раз.")
        return
    
    await state.update_data(name=name)
    await message.answer(
        f"Отлично, {name}! Теперь укажи свою дневную норму калорий.\n"
        "Пример: 2200 или 1850.5"
    )
    await state.set_state(Reg.goal)

@dp.message(Reg.goal)
async def reg_goal(message: types.Message, state: FSMContext):
    text = message.text.replace(',', '.').strip()
    try:
        goal = float(text)
        if goal <= 0:
            raise ValueError("Норма должна быть больше 0")
    except ValueError:
        await message.answer("Пожалуйста, введи нормальное число (можно с точкой).\nПример: 2100")
        return
    
    data = await state.get_data()
    name = data.get('name', 'Пользователь')
    
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT OR REPLACE INTO users (id, name, goal, eaten) VALUES (?, ?, ?, 0)",
                (message.from_user.id, name, goal)
            )
            await db.commit()
        
        await message.answer(
            f"Готово, {name}! Твоя цель — {goal} ккал в день.\n"
            "Теперь можешь добавлять еду в формате: продукт количество [продукт количество ...]\n"
            "Пример: гречка 100 курица 200 рис 150",
            reply_markup=main_kb()
        )
        await state.clear()
    
    except Exception as e:
        logger.error(f"Ошибка сохранения пользователя: {e}")
        await message.answer("Что-то пошло не так при сохранении. Попробуй /start заново.")

@dp.message(Command("addproduct"))
async def add_product(message: types.Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.reply("Формат: /addproduct продукт ккал\nПример: /addproduct яблоко 52")
        return
    product = parts[1].lower()
    try:
        kcal = float(parts[2].replace(',', '.'))
    except ValueError:
        await message.reply("Калории должны быть числом")
        return
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT OR REPLACE INTO products (product_name, kcal) VALUES (?, ?)",
                (product, kcal)
            )
            await db.commit()
        await message.reply(f"Продукт '{product}' добавлен с {kcal} ккал/100 г")
    except Exception as e:
        logger.error(f"Ошибка в add_product: {e}")
        await message.reply("Ошибка при добавлении продукта.")

# ─── КНОПКИ ───
@dp.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT goal, eaten FROM users WHERE id = ?", (message.from_user.id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    goal, eaten = row
                    left = goal - eaten if goal > eaten else 0
                    await message.answer(f"Цель: {goal} ккал\nСъедено: {eaten:.1f} ккал\nОсталось: {left:.1f} ккал")
                else:
                    await message.answer("Сначала зарегистрируйся через /start")
    except Exception as e:
        logger.error(f"Ошибка в show_stats: {e}")
        await message.answer("Ошибка при получении статистики.")

@dp.message(F.text == "♻️ Сброс дня")
async def reset_day(message: types.Message):
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET eaten = 0 WHERE id = ?", (message.from_user.id,))
            await db.commit()
        await message.answer("День сброшен! Счётчик калорий обнулён")
    except Exception as e:
        logger.error(f"Ошибка в reset_day: {e}")
        await message.answer("Ошибка при сбросе.")

@dp.message(F.text == "🍎 Быстрый перекус")
async def quick_snack(message: types.Message):
    await message.reply("Напиши что съел в формате: продукт количество [продукт количество ...]\nПример: гречка 100 курица 200")

# ─── ВВОД ЕДЫ (поддержка нескольких продуктов в одном сообщении) ───
@dp.message(F.text)
async def handle_food_input(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return

    text = message.text.lower().strip()
    words = text.split()

    if len(words) < 2 or len(words) % 2 != 0:
        return  # молчим, если не пары "продукт количество"

    added_items = []
    total_added_kcal = 0.0

    try:
        async with aiosqlite.connect(DB_NAME) as db:
            # проверяем существование пользователя один раз
            async with db.execute("SELECT id FROM users WHERE id = ?", (message.from_user.id,)) as cursor:
                if not await cursor.fetchone():
                    await message.reply("Сначала /start")
                    return

            i = 0
            while i < len(words) - 1:
                product = words[i]
                amount_str = words[i + 1]

                try:
                    amount = float(amount_str.replace(',', '.'))
                except ValueError:
                    i += 1
                    continue

                async with db.execute(
                    "SELECT kcal FROM products WHERE product_name = ?", (product,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        kcal_per_100 = row[0]
                        kcal_added = (kcal_per_100 / 100) * amount
                        total_added_kcal += kcal_added

                        await db.execute(
                            "UPDATE users SET eaten = eaten + ? WHERE id = ?",
                            (kcal_added, message.from_user.id)
                        )

                        added_items.append(f"{product.capitalize()} {amount} г → {kcal_added:.1f} ккал")

                i += 2

            if added_items:
                await db.commit()

                response = "Добавлено:\n" + "\n".join(added_items)
                if len(added_items) > 1:
                    response += f"\n\nИтого: +{total_added_kcal:.1f} ккал"
                await message.reply(response)

    except Exception as e:
        logger.error(f"Ошибка при добавлении продуктов: {e}")

# ─── GRACEFUL SHUTDOWN ───
async def shutdown():
    logger.info("Получен SIGTERM, graceful shutdown...")
    await bot.session.close()
    sys.exit(0)

def handle_sigterm(signum, frame):
    asyncio.create_task(shutdown())

signal.signal(signal.SIGTERM, handle_sigterm)

# ─── ЗАПУСК ───
async def main():
    logger.info("Бот запускается...")
    await init_db()
    await add_default_products()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

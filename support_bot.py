import os
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ---------- تنظیمات ----------
API_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
BUSINESS_NAME = "کسب‌وکار شما"
MIN_MATCH_SCORE = 1  # حداقل تعداد کلمه کلیدی مشترک برای این‌که یه جواب "پیدا شده" حساب بشه


# ---------- سرور کوچک برای Render/Railway ----------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def log_message(self, format, *args):
        pass


def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()


bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class AddFAQ(StatesGroup):
    keywords = State()
    answer = State()


class ReplyTicket(StatesGroup):
    waiting_for_reply = State()


# ---------- دیتابیس ----------
conn = sqlite3.connect("support.db")
cursor = conn.cursor()


def init_db():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS faqs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keywords TEXT NOT NULL,
        answer TEXT NOT NULL
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        user_name TEXT,
        question TEXT NOT NULL,
        status TEXT DEFAULT 'open'
    )
    """)
    conn.commit()


def seed_faqs():
    cursor.execute("SELECT COUNT(*) FROM faqs")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO faqs (keywords, answer) VALUES (?, ?)",
            [
                ("قیمت هزینه تعرفه", "برای اطلاع از قیمت‌ها می‌تونید با پشتیبانی تماس بگیرید یا صفحه قیمت‌گذاری سایت رو ببینید."),
                ("ساعت کاری زمان باز", "ساعت کاری ما هر روز از ۹ صبح تا ۶ عصر هست."),
                ("ارسال تحویل پیک", "زمان ارسال معمولاً بین ۱ تا ۳ روز کاری طول می‌کشه."),
            ]
        )
        conn.commit()


init_db()
seed_faqs()


# ---------- تطبیق کلمات کلیدی ----------
def find_best_answer(user_text):
    user_words = set(user_text.replace("؟", "").replace("!", "").split())

    cursor.execute("SELECT keywords, answer FROM faqs")
    best_score = 0
    best_answer = None

    for keywords, answer in cursor.fetchall():
        keyword_words = set(keywords.split())
        score = len(user_words & keyword_words)
        if score > best_score:
            best_score = score
            best_answer = answer

    if best_score >= MIN_MATCH_SCORE:
        return best_answer
    return None


# ---------- کیبوردها ----------
main_menu = ReplyKeyboardMarkup(resize_keyboard=True)
main_menu.add(KeyboardButton("❓ پرسیدن سوال"))
main_menu.add(KeyboardButton("📞 صحبت با پشتیبان انسانی"))
main_menu.add(KeyboardButton("ℹ️ راهنما"))

admin_menu = ReplyKeyboardMarkup(resize_keyboard=True)
admin_menu.add(KeyboardButton("📥 تیکت‌های باز"))
admin_menu.add(KeyboardButton("⚙️ مدیریت سوالات متداول"))
admin_menu.add(KeyboardButton("🔙 بازگشت"))


# ---------- شروع ----------
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    text = (
        f"سلام 👋\n"
        f"به دستیار پشتیبانی {BUSINESS_NAME} خوش اومدی!\n"
        f"سوالت رو مستقیم بپرس، یا از منوی زیر استفاده کن:"
    )
    await message.answer(text, reply_markup=main_menu)


@dp.message_handler(lambda m: m.text == "ℹ️ راهنما")
async def help_message(message: types.Message):
    text = (
        "📌 راهنما:\n\n"
        "می‌تونی سوالت رو مستقیم تایپ کنی، ربات سعی می‌کنه جواب بده.\n"
        "اگه جواب مناسبی پیدا نکرد، سوالت برای پشتیبان انسانی ارسال می‌شه."
    )
    await message.answer(text)


@dp.message_handler(lambda m: m.text == "❓ پرسیدن سوال")
async def ask_prompt(message: types.Message):
    await message.answer("سوالت رو بپرس، سعی می‌کنم کمکت کنم 🙂")


@dp.message_handler(lambda m: m.text == "📞 صحبت با پشتیبان انسانی")
async def request_human(message: types.Message):
    cursor.execute(
        "INSERT INTO tickets (user_id, user_name, question) VALUES (?, ?, ?)",
        (message.from_user.id, message.from_user.full_name, "درخواست صحبت مستقیم با پشتیبان")
    )
    conn.commit()
    await message.answer("درخواستت برای پشتیبان انسانی ارسال شد. به‌زودی باهات تماس می‌گیریم ✅")

    if ADMIN_ID:
        try:
            await bot.send_message(
                ADMIN_ID,
                f"📞 درخواست پشتیبانی انسانی از {message.from_user.full_name} "
                f"(آیدی: {message.from_user.id})"
            )
        except Exception:
            pass


# ---------- پنل ادمین ----------
@dp.message_handler(commands=['admin'])
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("شما دسترسی ادمین ندارید.")
        return
    await message.answer("⚙️ پنل ادمین:", reply_markup=admin_menu)


@dp.message_handler(lambda m: m.text == "🔙 بازگشت")
async def back_to_main(message: types.Message):
    await message.answer("بازگشت به منوی اصلی.", reply_markup=main_menu)


@dp.message_handler(lambda m: m.text == "📥 تیکت‌های باز")
async def admin_open_tickets(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    cursor.execute("SELECT id, user_name, question FROM tickets WHERE status = 'open' ORDER BY id DESC LIMIT 20")
    rows = cursor.fetchall()

    if not rows:
        await message.answer("تیکت باز وجود نداره ✅")
        return

    kb = InlineKeyboardMarkup()
    for ticket_id, user_name, question in rows:
        label = f"#{ticket_id} | {user_name} | {question[:30]}"
        kb.add(InlineKeyboardButton(label, callback_data=f"ticket_{ticket_id}"))
    await message.answer("📥 تیکت‌های باز:", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data.startswith("ticket_"))
async def view_ticket(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("دسترسی ندارید.", show_alert=True)
        return

    ticket_id = int(callback_query.data.split("_")[1])
    cursor.execute("SELECT user_id, user_name, question FROM tickets WHERE id = ?", (ticket_id,))
    row = cursor.fetchone()
    if not row:
        await callback_query.answer("تیکت پیدا نشد.", show_alert=True)
        return

    user_id, user_name, question = row
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✅ بستن تیکت", callback_data=f"closeticket_{ticket_id}"))

    await state.update_data(reply_to_user_id=user_id, ticket_id=ticket_id)
    await callback_query.message.answer(
        f"🎫 تیکت #{ticket_id}\n👤 {user_name}\n❓ {question}\n\nبرای پاسخ، پیامت رو بفرست:",
        reply_markup=kb
    )
    await ReplyTicket.waiting_for_reply.set()
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("closeticket_"))
async def close_ticket(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("دسترسی ندارید.", show_alert=True)
        return
    ticket_id = int(callback_query.data.split("_")[1])
    cursor.execute("UPDATE tickets SET status = 'closed' WHERE id = ?", (ticket_id,))
    conn.commit()
    await callback_query.message.answer(f"تیکت #{ticket_id} بسته شد ✅")
    await state.finish()
    await callback_query.answer()


@dp.message_handler(state=ReplyTicket.waiting_for_reply)
async def send_reply_to_user(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("reply_to_user_id")
    ticket_id = data.get("ticket_id")

    try:
        await bot.send_message(user_id, f"💬 پاسخ پشتیبانی:\n\n{message.text}")
        await message.answer("پاسخ ارسال شد ✅")
        cursor.execute("UPDATE tickets SET status = 'closed' WHERE id = ?", (ticket_id,))
        conn.commit()
    except Exception:
        await message.answer("ارسال پیام به کاربر ناموفق بود ❌")

    await state.finish()


@dp.message_handler(lambda m: m.text == "⚙️ مدیریت سوالات متداول")
async def admin_manage_faqs(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardMarkup()
    cursor.execute("SELECT id, keywords FROM faqs")
    for faq_id, keywords in cursor.fetchall():
        kb.add(InlineKeyboardButton(f"❌ حذف: {keywords}", callback_data=f"delfaq_{faq_id}"))
    kb.add(InlineKeyboardButton("➕ افزودن سوال متداول جدید", callback_data="add_faq"))
    await message.answer("⚙️ مدیریت سوالات متداول:", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data.startswith("delfaq_"))
async def delete_faq(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("دسترسی ندارید.", show_alert=True)
        return
    faq_id = int(callback_query.data.split("_")[1])
    cursor.execute("DELETE FROM faqs WHERE id = ?", (faq_id,))
    conn.commit()
    await callback_query.message.answer("سوال متداول حذف شد ✅")
    await callback_query.answer()


@dp.callback_query_handler(lambda c: c.data == "add_faq")
async def add_faq_start(callback_query: types.CallbackQuery):
    if callback_query.from_user.id != ADMIN_ID:
        await callback_query.answer("دسترسی ندارید.", show_alert=True)
        return
    await callback_query.message.answer(
        "کلمات کلیدی مربوط به این سوال رو با فاصله بفرست (مثلاً: قیمت هزینه تعرفه):"
    )
    await AddFAQ.keywords.set()
    await callback_query.answer()


@dp.message_handler(state=AddFAQ.keywords)
async def add_faq_keywords(message: types.Message, state: FSMContext):
    await state.update_data(keywords=message.text)
    await message.answer("حالا متن پاسخ رو بفرست:")
    await AddFAQ.answer.set()


@dp.message_handler(state=AddFAQ.answer)
async def add_faq_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute(
        "INSERT INTO faqs (keywords, answer) VALUES (?, ?)",
        (data["keywords"], message.text)
    )
    conn.commit()
    await state.finish()
    await message.answer("سوال متداول جدید اضافه شد ✅")


# ---------- پاسخ‌دهی هوشمند به هر پیام آزاد ----------
@dp.message_handler()
async def smart_reply(message: types.Message):
    answer = find_best_answer(message.text)

    if answer:
        await message.answer(f"{answer}\n\n(اگه جواب کافی نبود، از گزینه «📞 صحبت با پشتیبان انسانی» استفاده کن)")
    else:
        cursor.execute(
            "INSERT INTO tickets (user_id, user_name, question) VALUES (?, ?, ?)",
            (message.from_user.id, message.from_user.full_name, message.text)
        )
        conn.commit()

        await message.answer(
            "متأسفانه جواب دقیقی برای این سوال ندارم 🙏\n"
            "سوالت رو برای پشتیبان انسانی ارسال کردم، به‌زودی جواب می‌گیری."
        )

        if ADMIN_ID:
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"🆕 سوال بی‌جواب از {message.from_user.full_name}:\n\n{message.text}"
                )
            except Exception:
                pass


# ---------- اجرای ربات ----------
if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start()
    print("ربات پشتیبانی در حال اجراست...")
    executor.start_polling(dp, skip_updates=True)

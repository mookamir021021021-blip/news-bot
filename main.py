import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from aiogram.enums import ContentType
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, CHANNEL_ID, ADMIN_GROUP_ID, ADMIN_IDS
from database import init_db, save_ticket
from ai_handler import analyze_news

logging.basicConfig(level=logging.INFO)
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)
pending_tickets = {}

# ==================== States ====================
class ReportState(StatesGroup):
    waiting_for_report = State()

class ReplyState(StatesGroup):
    waiting_for_reply = State()

# ==================== Keyboards ====================
def user_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 ثبت تیکت جدید")],
            [KeyboardButton(text="📋 وضعیت تیکت‌های من"), KeyboardButton(text="ℹ️ راهنما")],
        ],
        resize_keyboard=True
    )
    return keyboard

def admin_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 ثبت تیکت جدید")],
            [KeyboardButton(text="📋 وضعیت تیکت‌های من"), KeyboardButton(text="ℹ️ راهنما")],
            [KeyboardButton(text="⚙️ پنل ادمین")],
        ],
        resize_keyboard=True
    )
    return keyboard

def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ انصراف")]],
        resize_keyboard=True
    )

# ==================== Start ====================
@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
   
    is_admin = message.from_user.id in ADMIN_IDS
   
    welcome_text = (
        "سلام 👋\n\n"
        "به ربات پشتیبانی نیوز پلاس خوش اومدید.\n"
        "از دکمه‌های زیر استفاده کنید:"
    )
   
    if is_admin:
        await message.answer(welcome_text, reply_markup=admin_main_keyboard())
    else:
        await message.answer(welcome_text, reply_markup=user_main_keyboard())

# ==================== راهنما ====================
@dp.message(F.text == "ℹ️ راهنما")
async def help_handler(message: Message):
    text = (
        "📖 راهنمای استفاده از ربات:\n\n"
        "۱. روی دکمه «ثبت تیکت جدید» بزنید\n"
        "۲. متن، عکس یا فیلم مد نظرتون خود را ارسال کنید\n"
        "۳.تیکت شما بررسی می‌شود\n"
    )
    await message.answer(text)

# ==================== ثبت تیکت جدید ====================
@dp.message(F.text == "📝 ثبت تیکت جدید")
async def new_report_handler(message: Message, state: FSMContext):
    await state.set_state(ReportState.waiting_for_report)
    await message.answer(
        "لطفاً جزئیات تیکت خود را ارسال کنید:\n"
        "(می‌توانید عکس یا فیلم هم بفرستید)\n\n"
        "برای انصراف روی دکمه «انصراف» بزنید.",
        reply_markup=cancel_keyboard()
    )

@dp.message(F.text == "❌ انصراف")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    is_admin = message.from_user.id in ADMIN_IDS
    keyboard = admin_main_keyboard() if is_admin else user_main_keyboard()
    await message.answer("عملیات لغو شد.", reply_markup=keyboard)

# ==================== دریافت تیکت ====================
@dp.message(ReportState.waiting_for_report, F.content_type.in_({
    ContentType.TEXT, ContentType.PHOTO, ContentType.VIDEO, ContentType.DOCUMENT
}))
async def process_report(message: Message, state: FSMContext):
    user = message.from_user
    text = message.text or message.caption or ""
    content_type = message.content_type
    file_id = None

    if message.photo:
        file_id = message.photo[-1].file_id
        content_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        content_type = "video"
    elif message.document:
        file_id = message.document.file_id
        content_type = "document"

    await message.answer("در حال بررسی تیکت شما...")

    has_media = file_id is not None
    ai_result = await analyze_news(text, has_media=has_media)
    is_important = ai_result["is_important"]
    summary = ai_result["summary"]

    ticket_id = await save_ticket(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        content_type=content_type,
        text_content=text,
        file_id=file_id,
        is_important=is_important,
        ai_summary=summary
    )

    pending_tickets[ticket_id] = {
        "user_id": user.id,
        "full_name": user.full_name,
        "text": text,
        "file_id": file_id,
        "content_type": content_type,
        "summary": summary,
        "is_important": is_important
    }

    # دکمه‌های تأیید / رد / پاسخ
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأیید و انتشار", callback_data=f"approve_{ticket_id}"),
            InlineKeyboardButton(text="❌ رد کردن", callback_data=f"reject_{ticket_id}")
        ],
        [
            InlineKeyboardButton(text="💬 پاسخ به کاربر", callback_data=f"reply_{ticket_id}")
        ]
    ])

    admin_text = (
        f"🎫 تیکت جدید #{ticket_id}\n\n"
        f"👤 {user.full_name}\n"
        f"🆔 `{user.id}`\n"
        f"📌 تشخیص AI: {'مهم ✅' if is_important else 'غیرمهم ❌'}\n\n"
        f"📝 متن:\n{text or '(بدون متن)'}"
    )
    if summary:
        admin_text += f"\n\n🤖 پیشنهاد کپشن:\n{summary}"

    try:
        if file_id and content_type == "photo":
            await bot.send_photo(ADMIN_GROUP_ID, photo=file_id, caption=admin_text, reply_markup=keyboard)
        elif file_id and content_type == "video":
            await bot.send_video(ADMIN_GROUP_ID, video=file_id, caption=admin_text, reply_markup=keyboard)
        else:
            await bot.send_message(ADMIN_GROUP_ID, admin_text, reply_markup=keyboard)
    except Exception as e:
        print("Admin error:", e)

    is_admin = user.id in ADMIN_IDS
    main_kb = admin_main_keyboard() if is_admin else user_main_keyboard()
   
    await message.answer(
        f"✅ تیکت شما با شماره #{ticket_id} ثبت شد و برای بررسی ارسال گردید.",
        reply_markup=main_kb
    )
    await state.clear()

# ==================== وضعیت تیکت‌ها ====================
@dp.message(F.text == "📋 وضعیت تیکت‌های من")
async def my_tickets_handler(message: Message):
    await message.answer(
        "این بخش به زودی کامل می‌شود.\n"
        "فعلاً بعد از ثبت تیکت، شماره تیکت به شما داده می‌شود."
    )

# ==================== پنل ادمین ====================
@dp.message(F.text == "⚙️ پنل ادمین")
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("شما دسترسی ندارید.")
        return
   
    await message.answer(
        "⚙️ پنل ادمین\n\n"
        "تیکت‌های جدید به صورت خودکار به گروه ادمین ارسال می‌شوند.\n"
        "از دکمه‌های تأیید / رد / پاسخ در گروه استفاده کنید."
    )

# ==================== دکمه‌های تأیید و رد ====================
@dp.callback_query(F.data.startswith("approve_"))
async def approve_handler(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("دسترسی ندارید", show_alert=True)
        return

    ticket_id = int(callback.data.split("_")[1])
    ticket = pending_tickets.get(ticket_id)

    if not ticket:
        await callback.answer("تیکت منقضی شده", show_alert=True)
        return

    summary = ticket.get("summary") or ticket.get("text") or "گزارش خبری"
    file_id = ticket.get("file_id")
    content_type = ticket.get("content_type")

    try:
        if content_type == "photo" and file_id:
            await bot.send_photo(CHANNEL_ID, photo=file_id, caption=summary)
        elif content_type == "video" and file_id:
            await bot.send_video(CHANNEL_ID, video=file_id, caption=summary)
        else:
            await bot.send_message(CHANNEL_ID, text=summary)

        new_text = (callback.message.caption or callback.message.text or "") + "\n\n✅ تأیید و منتشر شد"
        if callback.message.caption:
            await callback.message.edit_caption(caption=new_text, reply_markup=None)
        else:
            await callback.message.edit_text(text=new_text, reply_markup=None)

        await bot.send_message(ticket["user_id"], f"✅ گزارش #{ticket_id} شما تأیید و در کانال منتشر شد.")
        await callback.answer("منتشر شد ✅")
    except Exception as e:
        print("Approve error:", e)
        await callback.answer("خطا در انتشار", show_alert=True)

    if ticket_id in pending_tickets:
        del pending_tickets[ticket_id]

@dp.callback_query(F.data.startswith("reject_"))
async def reject_handler(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("دسترسی ندارید", show_alert=True)
        return

    ticket_id = int(callback.data.split("_")[1])
    ticket = pending_tickets.get(ticket_id)

    if not ticket:
        await callback.answer("تیکت منقضی شده", show_alert=True)
        return

    try:
        new_text = (callback.message.caption or callback.message.text or "") + "\n\n❌ رد شد"
        if callback.message.caption:
            await callback.message.edit_caption(caption=new_text, reply_markup=None)
        else:
            await callback.message.edit_text(text=new_text, reply_markup=None)

        await bot.send_message(ticket["user_id"], f"❌ تیکت #{ticket_id} شما رد شد.")
        await callback.answer("رد شد")
    except Exception as e:
        print("Reject error:", e)

    if ticket_id in pending_tickets:
        del pending_tickets[ticket_id]

# ==================== پاسخ به کاربر ====================
@dp.callback_query(F.data.startswith("reply_"))
async def reply_start_handler(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("دسترسی ندارید", show_alert=True)
        return

    ticket_id = int(callback.data.split("_")[1])
    ticket = pending_tickets.get(ticket_id)

    if not ticket:
        await callback.answer("تیکت منقضی شده", show_alert=True)
        return

    await state.set_state(ReplyState.waiting_for_reply)
    await state.update_data(reply_ticket_id=ticket_id, reply_user_id=ticket["user_id"])

    await callback.message.answer(
        f"در حال پاسخ به تیکت #{ticket_id}\n\n"
        f"پیام خود را بنویسید تا برای کاربر ارسال شود.\n"
        f"برای لغو، /cancel را بفرستید."
    )
    await callback.answer()

@dp.message(ReplyState.waiting_for_reply)
async def process_admin_reply(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    data = await state.get_data()
    ticket_id = data.get("reply_ticket_id")
    user_id = data.get("reply_user_id")

    if not ticket_id or not user_id:
        await state.clear()
        return await message.answer("خطا رخ داد.")

    try:
        await bot.send_message(
            user_id,
            f"📩 پاسخ ادمین به تیکت #{ticket_id}:\n\n{message.text}"
        )
        await message.answer("✅ پیام شما با موفقیت برای کاربر ارسال شد.")
    except Exception as e:
        await message.answer(f"خطا در ارسال پیام به کاربر:\n{e}")

    await state.clear()

@dp.message(F.text == "/cancel")
async def cancel_reply(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("پاسخ لغو شد.")

# ==================== پیام‌های معمولی ====================
@dp.message(F.content_type.in_({ContentType.TEXT, ContentType.PHOTO, ContentType.VIDEO}))
async def fallback_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == ReportState.waiting_for_report.state:
        return
   
    await message.answer(
        "لطفاً از دکمه‌های منو استفاده کنید.\n"
        "برای شروع روی /start بزنید."
    )

async def main():
    await init_db()
    print("Bot started successfully")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

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
from database import (
    init_db, save_ticket, get_user_tickets, update_ticket_status,
    get_or_create_user, update_custom_name, get_user_profile
)
from ai_handler import analyze_news

logging.basicConfig(level=logging.INFO)
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)
pending_tickets = {}

# ==================== States ====================
class ReportState(StatesGroup):
    waiting_for_title = State()
    waiting_for_report = State()

class ReplyState(StatesGroup):
    waiting_for_reply = State()

class SettingsState(StatesGroup):
    waiting_for_name = State()

# ==================== Keyboards ====================
def user_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 ثبت تیکت جدید")],
            [KeyboardButton(text="📋 وضعیت تیکت‌ها"), KeyboardButton(text="⚙️ تنظیمات")],
            [KeyboardButton(text="📖 راهنما")],
        ],
        resize_keyboard=True
    )

def admin_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 ثبت تیکت جدید")],
            [KeyboardButton(text="📋 وضعیت تیکت‌ها"), KeyboardButton(text="⚙️ تنظیمات")],
            [KeyboardButton(text="🛠️ پنل ادمین"), KeyboardButton(text="📖 راهنما")],
        ],
        resize_keyboard=True
    )

def settings_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ تغییر نام")],
            [KeyboardButton(text="👤 پروفایل من")],
            [KeyboardButton(text="🔙 بازگشت به منو")],
        ],
        resize_keyboard=True
    )

def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ انصراف")]],
        resize_keyboard=True
    )

# ==================== Start ====================
@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    
    is_admin = message.from_user.id in ADMIN_IDS
    welcome_text = (
        f"سلام {message.from_user.first_name} 👋\n\n"
        "به ربات پشتیبانی **نیوز پلاس** خوش اومدید.\n"
        "از دکمه‌های زیر استفاده کنید:"
    )
    keyboard = admin_main_keyboard() if is_admin else user_main_keyboard()
    await message.answer(welcome_text, reply_markup=keyboard)

# ==================== راهنما ====================
@dp.message(F.text == "📖 راهنما")
async def help_handler(message: Message):
    text = (
        "📖 *راهنمای ربات*\n\n"
        "🔸 *ثبت تیکت جدید*\n"
        "عنوان + توضیحات + عکس یا فیلم\n\n"
        "🔸 *وضعیت تیکت‌ها*\n"
        "لیست تیکت‌ها (پاسخ پشتیبانی با 🟢 نشون داده می‌شود)\n\n"
        "🔸 *تنظیمات*\n"
        "تغییر نام نمایشی"
    )
    await message.answer(text, parse_mode="Markdown")

# ==================== ثبت تیکت جدید ====================
@dp.message(F.text == "📝 ثبت تیکت جدید")
async def new_report_handler(message: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📝 ارسال گزارش", callback_data="new_report")
        ]
    ])
    await message.answer("📝 *ثبت تیکت جدید*\n\nیکی از گزینه‌های زیر را انتخاب کنید:", 
                         reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(F.data == "new_report")
async def new_report_confirm(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ReportState.waiting_for_title)
    await callback.message.answer(
        "لطفاً *عنوان تیکت* را بنویسید:\n\nمثال: انفجار در تهران / صدای پدافند\n\nبرای انصراف روی «❌ انصراف» بزنید.",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

# ==================== ثبت تیکت جدید (ارسال گزارش) ====================
@dp.message(ReportState.waiting_for_title, F.text)
async def process_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) < 3:
        await message.answer("عنوان خیلی کوتاه است. لطفاً عنوان بهتری بنویسید:")
        return

    await state.update_data(title=title)
    await state.set_state(ReportState.waiting_for_report)
    await message.answer(
        f"عنوان ثبت شد: *{title}*\n\n"
        "حالا توضیحات تیکت را ارسال کنید (متن، عکس یا فیلم):",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(ReportState.waiting_for_report, F.content_type.in_({
    ContentType.TEXT, ContentType.PHOTO, ContentType.VIDEO, ContentType.DOCUMENT
}))
async def process_report(message: Message, state: FSMContext):
    data = await state.get_data()
    title = data.get("title", "بدون عنوان")

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

    profile = await get_user_profile(user.id)
    display_name = profile["custom_name"] if profile and profile["custom_name"] else user.full_name

    has_media = file_id is not None
    ai_result = await analyze_news(f"{title}\n{text}", has_media=has_media)
    is_important = ai_result["is_important"]
    summary = ai_result["summary"]

    ticket_id = await save_ticket(
        user_id=user.id,
        username=user.username,
        full_name=display_name,
        title=title,
        content_type=content_type,
        text_content=text,
        file_id=file_id,
        is_important=is_important,
        ai_summary=summary
    )

    pending_tickets[ticket_id] = {
        "user_id": user.id,
        "full_name": display_name,
        "title": title,
        "text": text,
        "file_id": file_id,
        "content_type": content_type,
        "summary": summary,
        "is_important": is_important
    }

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
        f"📌 عنوان: {title}\n"
        f"👤 {display_name}\n"
        f"🆔 `{user.id}`\n"
        f"🔍 تشخیص AI: {'مهم ✅' if is_important else 'غیرمهم ❌'}\n\n"
        f"📝 توضیحات:\n{text or '(بدون متن)'}"
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
        f"✅ تیکت شما با شماره *#{ticket_id}* ثبت شد.\nعنوان: {title}",
        reply_markup=main_kb,
        parse_mode="Markdown"
    )
    await state.clear()

# ==================== وضعیت تیکت‌ها ====================
@dp.message(F.text == "📋 وضعیت تیکت‌ها")
async def my_tickets_handler(message: Message):
    tickets = await get_user_tickets(message.from_user.id)

    if not tickets:
        await message.answer("شما هنوز هیچ تیکتی ثبت نکرده‌اید.")
        return

    text = "📋 *آخرین تیکت‌های شما:*\n\n"
    for t in tickets:
        status = "🟢 باز" if t["status"] == "open" else "🔴 بسته"
        important = " ⭐" if t["is_important"] else ""
        text += f"*#{t['id']}* | {t['title'] or 'بدون عنوان'}{important}\nوضعیت: {status}\n\n"

    await message.answer(text, parse_mode="Markdown")

# ==================== تنظیمات ====================
@dp.message(F.text == "⚙️ تنظیمات")
async def settings_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "⚙️ *تنظیمات حساب کاربری*\n\nیکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=settings_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(F.text == "🔙 بازگشت به منو")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    is_admin = message.from_user.id in ADMIN_IDS
    keyboard = admin_main_keyboard() if is_admin else user_main_keyboard()
    await message.answer("به منوی اصلی بازگشتید.", reply_markup=keyboard)

@dp.message(F.text == "👤 پروفایل من")
async def profile_handler(message: Message):
    profile = await get_user_profile(message.from_user.id)
    if not profile:
        await message.answer("پروفایلی یافت نشد.")
        return
    text = (
        f"👤 *پروفایل شما*\n\n"
        f"🆔 آیدی: `{profile['user_id']}`\n"
        f"📝 نام نمایشی: {profile['custom_name'] or 'ثبت نشده'}\n"
        f"👤 یوزرنیم: @{profile['username'] or 'ندارد'}"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "✏️ تغییر نام")
async def change_name_start(message: Message, state: FSMContext):
    await state.set_state(SettingsState.waiting_for_name)
    await message.answer(
        "نام جدید خود را بنویسید:\n\n"
        "برای انصراف روی «❌ انصراف» بزنید.",
        reply_markup=cancel_keyboard()
    )

@dp.message(SettingsState.waiting_for_name, F.text)
async def process_new_name(message: Message, state: FSMContext):
    if message.text == "❌ انصراف":
        await state.clear()
        await message.answer("لغو شد.", reply_markup=settings_keyboard())
        return

    new_name = message.text.strip()
    if len(new_name) < 2 or len(new_name) > 40:
        await message.answer("نام باید بین ۲ تا ۴۰ حرف باشد. دوباره بنویسید:")
        return

    await update_custom_name(message.from_user.id, new_name)
    await state.clear()
    await message.answer(
        f"✅ نام شما به **{new_name}** تغییر کرد.",
        reply_markup=settings_keyboard(),
        parse_mode="Markdown"
    )

# ==================== پنل ادمین ====================
@dp.message(F.text == "🛠️ پنل ادمین")
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("شما دسترسی ندارید.")
        return
    await message.answer(
        "🛠️ *پنل ادمین*\n\nتیکت‌های جدید به گروه ادمین ارسال می‌شوند.\nاز دکمه‌های تأیید / رد / پاسخ استفاده کنید.",
        parse_mode="Markdown"
    )

# ==================== دکمه‌های ادمین ====================
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

    summary = ticket.get("summary") or ticket.get("text") or ticket.get("title") or "گزارش خبری"
    try:
        if ticket["content_type"] == "photo" and ticket["file_id"]:
            await bot.send_photo(CHANNEL_ID, photo=ticket["file_id"], caption=summary)
        elif ticket["content_type"] == "video" and ticket["file_id"]:
            await bot.send_video(CHANNEL_ID, video=ticket["file_id"], caption=summary)
        else:
            await bot.send_message(CHANNEL_ID, text=summary)

        new_text = (callback.message.caption or callback.message.text or "") + "\n\n✅ تأیید و منتشر شد"
        if callback.message.caption:
            await callback.message.edit_caption(caption=new_text, reply_markup=None)
        else:
            await callback.message.edit_text(text=new_text, reply_markup=None)

        await bot.send_message(ticket["user_id"], f"✅ تیکت #{ticket_id} شما تأیید و در کانال منتشر شد.")
        await update_ticket_status(ticket_id, "closed")
        await callback.answer("منتشر شد ✅")
    except Exception as e:
        print("Approve error:", e)
        await callback.answer("خطا در انتشار", show_alert=True)

    pending_tickets.pop(ticket_id, None)

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

    new_text = (callback.message.caption or callback.message.text or "") + "\n\n❌ رد شد"
    if callback.message.caption:
        await callback.message.edit_caption(caption=new_text, reply_markup=None)
    else:
        await callback.message.edit_text(text=new_text, reply_markup=None)

    await bot.send_message(ticket["user_id"], f"❌ تیکت #{ticket_id} شما رد شد.")
    await update_ticket_status(ticket_id, "closed")
    await callback.answer("رد شد")
    pending_tickets.pop(ticket_id, None)

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
        f"پیام خود را بنویسید:\n"
        f"(برای لغو /cancel بفرستید)"
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
        await bot.send_message(user_id, f"📩 پاسخ ادمین به تیکت #{ticket_id}:\n\n{message.text}")
        await message.answer("✅ پیام برای کاربر ارسال شد.")
    except Exception as e:
        await message.answer(f"خطا در ارسال: {e}")

    await state.clear()

@dp.message(F.text == "/cancel")
async def cancel_reply(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("پاسخ لغو شد.")

# ==================== Fallback ====================
@dp.message(F.content_type.in_({ContentType.TEXT, ContentType.PHOTO, ContentType.VIDEO}))
async def fallback_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state in [
        ReportState.waiting_for_title.state, 
        ReportState.waiting_for_report.state,
        SettingsState.waiting_for_name.state
    ]:
        return
    await message.answer("لطفاً از دکمه‌های منو استفاده کنید.\nبرای شروع /start بزنید.")

async def main():
    await init_db()
    print("Bot started successfully")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

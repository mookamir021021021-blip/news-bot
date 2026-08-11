import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.enums import ContentType

from config import BOT_TOKEN, CHANNEL_ID, ADMIN_GROUP_ID, ADMIN_IDS
from database import init_db, save_ticket
from ai_handler import analyze_news

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ذخیره موقت اطلاعات تیکت‌ها برای دکمه‌ها
pending_tickets = {}

@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "سلام\n"
        "گزارش خبری خود را بفرستید (متن، عکس یا فیلم).\n"
        "گزارش شما بررسی و در صورت نیاز منتشر می‌شود."
    )

@dp.message(F.content_type.in_({
    ContentType.TEXT, 
    ContentType.PHOTO, 
    ContentType.VIDEO, 
    ContentType.DOCUMENT
}))
async def report_handler(message: Message):
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

    await message.answer("گزارش شما ثبت شد و در حال بررسی است...")

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

    # ذخیره اطلاعات برای دکمه‌ها
    pending_tickets[ticket_id] = {
        "user_id": user.id,
        "full_name": user.full_name,
        "text": text,
        "file_id": file_id,
        "content_type": content_type,
        "summary": summary,
        "is_important": is_important
    }

    # ساخت دکمه‌ها
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تأیید و انتشار", callback_data=f"approve_{ticket_id}"),
            InlineKeyboardButton(text="❌ رد کردن", callback_data=f"reject_{ticket_id}")
        ]
    ])

    admin_text = (
        f"🎫 تیکت جدید #{ticket_id}\n\n"
        f"👤 {user.full_name}\n"
        f"🆔 `{user.id}`\n"
        f"📌 تشخیص هوش مصنوعی: {'مهم ✅' if is_important else 'غیرمهم ❌'}\n\n"
        f"📝 متن گزارش:\n{text or '(بدون متن)'}\n"
    )
    
    if summary:
        admin_text += f"\n🤖 پیشنهاد کپشن:\n{summary}"

    try:
        if file_id and content_type == "photo":
            await bot.send_photo(ADMIN_GROUP_ID, photo=file_id, caption=admin_text, reply_markup=keyboard)
        elif file_id and content_type == "video":
            await bot.send_video(ADMIN_GROUP_ID, video=file_id, caption=admin_text, reply_markup=keyboard)
        else:
            await bot.send_message(ADMIN_GROUP_ID, admin_text, reply_markup=keyboard)
    except Exception as e:
        print("Admin group error:", e)
        await message.answer("خطا در ارسال به ادمین.")

@dp.callback_query(F.data.startswith("approve_"))
async def approve_handler(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("شما دسترسی ندارید", show_alert=True)
        return

    ticket_id = int(callback.data.split("_")[1])
    ticket = pending_tickets.get(ticket_id)

    if not ticket:
        await callback.answer("این تیکت منقضی شده", show_alert=True)
        return

    summary = ticket["summary"] or ticket["text"] or "گزارش خبری"
    file_id = ticket["file_id"]
    content_type = ticket["content_type"]

    try:
        if content_type == "photo" and file_id:
            await bot.send_photo(CHANNEL_ID, photo=file_id, caption=summary)
        elif content_type == "video" and file_id:
            await bot.send_video(CHANNEL_ID, video=file_id, caption=summary)
        else:
            await bot.send_message(CHANNEL_ID, text=summary)

        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n✅ توسط ادمین تأیید و منتشر شد",
            reply_markup=None
        ) if callback.message.caption else await callback.message.edit_text(
            text=callback.message.text + "\n\n✅ توسط ادمین تأیید و منتشر شد",
            reply_markup=None
        )

        await bot.send_message(ticket["user_id"], "گزارش شما تأیید و در کانال منتشر شد.")
        await callback.answer("منتشر شد ✅")

    except Exception as e:
        print("Post error:", e)
        await callback.answer("خطا در انتشار", show_alert=True)

    # پاک کردن از حافظه موقت
    if ticket_id in pending_tickets:
        del pending_tickets[ticket_id]

@dp.callback_query(F.data.startswith("reject_"))
async def reject_handler(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("شما دسترسی ندارید", show_alert=True)
        return

    ticket_id = int(callback.data.split("_")[1])
    ticket = pending_tickets.get(ticket_id)

    if not ticket:
        await callback.answer("این تیکت منقضی شده", show_alert=True)
        return

    try:
        if callback.message.caption:
            await callback.message.edit_caption(
                caption=callback.message.caption + "\n\n❌ توسط ادمین رد شد",
                reply_markup=None
            )
        else:
            await callback.message.edit_text(
                text=callback.message.text + "\n\n❌ توسط ادمین رد شد",
                reply_markup=None
            )

        await bot.send_message(ticket["user_id"], "گزارش شما بررسی شد اما منتشر نشد.")
        await callback.answer("رد شد ❌")

    except Exception as e:
        print("Reject error:", e)

    if ticket_id in pending_tickets:
        del pending_tickets[ticket_id]

async def main():
    await init_db()
    print("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

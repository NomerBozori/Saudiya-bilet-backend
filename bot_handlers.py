from aiogram import Router, Bot
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from config import settings
import database as db
from order_actions import confirm_order, reject_order

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Assalomu alaykum! ✈️\n\n"
        "Bu bot orqali Toshkent/Samarqand — Jidda/Madina yo'nalishida "
        "aviachipta buyurtma qilishingiz mumkin.\n\n"
        "Pastdagi tugma (Mini App) orqali chiptalarni qidiring, "
        "pasport ma'lumotlaringizni kiriting va to'lovni amalga oshiring. "
        "To'lovingiz tasdiqlangandan so'ng elektron chiptangiz shu yerga yuboriladi."
    )


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    # Admin/kanal chat_id larni aniqlash uchun yordamchi buyruq
    await message.answer(f"Ushbu chat ID: <code>{message.chat.id}</code>", parse_mode="HTML")


@router.message(Command("confirm_order"))
async def cmd_confirm_order(message: Message, command: CommandObject, bot: Bot):
    """Faqat admin guruhida ishlaydi: /confirm_order <order_id>"""
    if message.chat.id != settings.ADMIN_CHAT_ID:
        return
    if not command.args:
        await message.answer("Foydalanish: /confirm_order <buyurtma_id>")
        return
    try:
        order_id = int(command.args.strip())
    except ValueError:
        await message.answer("Buyurtma ID raqam bo'lishi kerak.")
        return

    result = await confirm_order(bot, order_id)
    if result["ok"]:
        await message.answer(f"✅ Buyurtma #{order_id} tasdiqlandi va chipta xaridorga yuborildi.")
    else:
        await message.answer(f"❌ {result['error']}")


@router.message(Command("reject_order"))
async def cmd_reject_order(message: Message, command: CommandObject, bot: Bot):
    """Faqat admin guruhida ishlaydi: /reject_order <order_id> <sabab>"""
    if message.chat.id != settings.ADMIN_CHAT_ID:
        return
    if not command.args:
        await message.answer("Foydalanish: /reject_order <buyurtma_id> <sabab>")
        return

    parts = command.args.strip().split(maxsplit=1)
    try:
        order_id = int(parts[0])
    except ValueError:
        await message.answer("Buyurtma ID raqam bo'lishi kerak.")
        return
    reason = parts[1] if len(parts) > 1 else "To'lov tasdiqlanmadi"

    result = await reject_order(bot, order_id, reason)
    if result["ok"]:
        await message.answer(f"Buyurtma #{order_id} rad etildi va xaridorga xabar yuborildi.")
    else:
        await message.answer(f"❌ {result['error']}")


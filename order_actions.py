import logging

from aiogram import Bot
from aiogram.types import BufferedInputFile

import database as db
from pdf_generator import generate_ticket_pdf

log = logging.getLogger("order_actions")


async def confirm_order(bot: Bot, order_id: int) -> dict:
    order = db.get_order(order_id)
    if not order:
        return {"ok": False, "error": "Buyurtma topilmadi"}

    passport = db.get_passport_by_order(order_id)
    if not passport:
        return {"ok": False, "error": "Bu buyurtma uchun pasport ma'lumotlari topilmadi"}

    try:
        pdf_bytes = generate_ticket_pdf(order, passport)
    except Exception as e:
        log.exception(f"PDF chipta yaratishda xatolik #{order_id}")
        return {"ok": False, "error": f"PDF chipta yaratishda xatolik: {e}"}

    file = BufferedInputFile(pdf_bytes, filename=f"eticket_{order_id}.pdf")
    try:
        await bot.send_document(
            chat_id=order["telegram_user_id"],
            document=file,
            caption=(
                f"✅ Buyurtmangiz (#{order_id}) tasdiqlandi!\n"
                "Elektron chiptangiz ilova qilingan hujjatda."
            ),
        )
    except Exception as e:
        log.exception(f"Chiptani xaridorga yuborishda xatolik #{order_id}")
        return {"ok": False, "error": f"Chiptani xaridorga yuborishda xatolik: {e}"}

    db.update_order(order_id, {"status": "confirmed"})
    return {"ok": True}


async def reject_order(bot: Bot, order_id: int, reason: str) -> dict:
    order = db.get_order(order_id)
    if not order:
        return {"ok": False, "error": "Buyurtma topilmadi"}

    try:
        await bot.send_message(
            order["telegram_user_id"],
            f"❌ Buyurtmangiz (#{order_id}) rad etildi.\nSabab: {reason}\n\nSavollar uchun admin bilan bog'laning.",
        )
    except Exception as e:
        log.exception(f"Xaridorga xabar yuborishda xatolik #{order_id}")
        return {"ok": False, "error": f"Xaridorga xabar yuborishda xatolik: {e}"}

    db.update_order(order_id, {"status": "rejected"})
    return {"ok": True}

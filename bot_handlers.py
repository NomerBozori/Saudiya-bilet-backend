import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

import database as db
from config import settings
from order_actions import confirm_order, reject_order

log = logging.getLogger("bot_handlers")
router = Router()


# ==================== ASOSIY MENYU ====================

def get_main_keyboard() -> InlineKeyboardMarkup:
    web_app_url = settings.WEBHOOK_BASE_URL.rstrip('/') if settings.WEBHOOK_BASE_URL else ""
    buttons = []
    
    # 1. Asosiy Mini App (Aviachipta qidirish)
    if web_app_url and web_app_url.startswith("http"):
        buttons.append([
            InlineKeyboardButton(
                text="✈️ Aviabiletlarni Qidirish (Mini App)",
                web_app=WebAppInfo(url=web_app_url)
            )
        ])
    
    # 2. Mening Chiptalarim va Viza
    buttons.append([
        InlineKeyboardButton(text="🗂 Mening Chiptalarim", callback_data="bot_my_orders"),
        InlineKeyboardButton(text="📑 Viza Xizmatlari", callback_data="bot_menu_visa")
    ])

    # 3. Aloqa
    buttons.append([
        InlineKeyboardButton(text=f"📞 Bog'lanish (@{settings.ADMIN_USERNAME})", callback_data="bot_menu_contact")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==================== /start ====================

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_name = message.from_user.first_name if message.from_user and message.from_user.first_name else "Hurmatli mijoz"
    
    welcome_text = (
        f"✈️ <b>Saudiya Biletlar Botiga xush kelibsiz, {user_name}!</b>\n\n"
        f"🕋 Umra va Ziyorat reyslari uchun eng hamyonbop aviachiptalar.\n"
        f"⚡️ Ticket band qilish, elektron chiptalar va tezkor viza xizmati.\n\n"
        f"Pastdagi <b>«✈️ Aviabiletlarni Qidirish»</b> tugmasi orqali barcha reyslar va narxlarni ko'rishingiz mumkin!"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )


# ==================== MENING CHIPTALARIM (/myorders) ====================

@router.message(Command("myorders"))
@router.callback_query(F.data == "bot_my_orders")
async def cb_my_orders(event: Message | CallbackQuery):
    user_id = event.from_user.id if event.from_user else 0
    
    try:
        orders = db.get_orders_by_user(user_id, limit=5)
    except Exception as e:
        log.warning(f"Buyurtmalarni olishda xatolik: {e}")
        orders = []

    if not orders:
        text = (
            "📭 <b>Sizda hali buyurtmalar mavjud emas.</b>\n\n"
            "Chipta xarid qilish uchun pastdagi «✈️ Aviabiletlarni Qidirish» tugmasidan foydalaning."
        )
    else:
        text = "🗂 <b>SIZNING BUYURTMALARINGIZ TARIXI:</b>\n\n"
        STATUS_MAP = {
            "new": "🆕 Yangi (Ko'rib chiqilmoqda)",
            "awaiting_confirmation": "⏳ To'lov cheki tasdiqlanmoqda",
            "confirmed": "✅ Tasdiqlangan (Chipta yuborilgan)",
            "rejected": "❌ Rad etilgan"
        }
        for o in orders:
            p_raw = o.get("passports")
            if isinstance(p_raw, list) and len(p_raw) > 0:
                passport = p_raw[0] if isinstance(p_raw[0], dict) else {}
            elif isinstance(p_raw, dict):
                passport = p_raw
            else:
                passport = {}

            st = STATUS_MAP.get(o.get("status"), o.get("status") or "Noma'lum")
            first_n = passport.get("first_name") or ""
            last_n = passport.get("last_name") or ""
            passenger_name = f"{first_n} {last_n}".strip() or "-"
            origin = (o.get("origin") or "-").upper()
            destination = (o.get("destination") or "-").upper()
            order_id = o.get("id", "-")
            depart_date = o.get("depart_date", "-")
            price = o.get("price", "-")

            text += (
                f"🎫 <b>Buyurtma #{order_id}</b>\n"
                f"   ✈️ {origin} ➔ {destination}\n"
                f"   👤 Yo'lovchi: {passenger_name}\n"
                f"   📅 Sana: {depart_date} | 💵 ${price}\n"
                f"   📊 Holati: <b>{st}</b>\n"
                f"   ──────────────\n"
            )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✈️ Yangi Bilet Qidirish", callback_data="bot_main_menu")],
        [InlineKeyboardButton(text="💬 Adminga Yozish", url=f"https://t.me/{settings.ADMIN_USERNAME}")]
    ])

    if isinstance(event, CallbackQuery):
        if event.message:
            await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")


# ==================== CALLBACKS ====================

@router.callback_query(F.data == "bot_main_menu")
async def cb_main_menu(call: CallbackQuery):
    text = (
        "✈️ <b>Saudiya Biletlar Bosh Menyusi</b>\n\n"
        "Kerakli bo'limni tanlang:"
    )
    if call.message:
        await call.message.edit_text(text, reply_markup=get_main_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "bot_menu_visa")
async def cb_visa_services(call: CallbackQuery):
    text = (
        "📑 <b>SAUDIYA ARABISTONI VIZA XIZMATLARI</b>\n\n"
        "1️⃣ <b>1 Yillik Multi Turistik Viza</b>\n"
        "• 1 yil davomida ko'p martalik kirish-chiqish\n"
        "• Har safar 90 kungacha qolish imkoniyati\n"
        "• Tayyor bo'lish vaqti: <b>24–48 soat</b>\n"
        "• Kerakli hujjat: Zagran pasport nusxasi va 3.5x4.5 rasm\n\n"
        "2️⃣ <b>Rasmiy Umra Vizasi (Nusuk)</b>\n"
        "• 90 kunlik rasmiy ziyorat vizasi va to'liq sug'urta\n"
        "• Tayyor bo'lish vaqti: <b>1–3 ish kuni</b>\n\n"
        "<i>Viza narxi va rasmiylashtirish uchun operatorimizga murojaat qiling:</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✍️ Viza Rasmiylashtirish (@{settings.ADMIN_USERNAME})", url=f"https://t.me/{settings.ADMIN_USERNAME}")],
        [InlineKeyboardButton(text="🔙 Asosiy Menyu", callback_data="bot_main_menu")]
    ])
    if call.message:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "bot_menu_contact")
async def cb_contact(call: CallbackQuery):
    text = (
        "📞 <b>BIZ BILAN BOG'LANISH</b>\n\n"
        f"👤 <b>Bosh Operator / Admin:</b> @{settings.ADMIN_USERNAME}\n"
        "🤖 <b>Rasmiy Bot:</b> @Saudiya_Biletlarbot\n"
        "⏰ <b>Ish tartibi:</b> 24/7 uzluksiz xizmatingizdamiz\n\n"
        "Savollaringiz bo'lsa, to'g'ridan-to'g'ri adminga yozishingiz mumkin:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💬 Adminga Yozish (@{settings.ADMIN_USERNAME})", url=f"https://t.me/{settings.ADMIN_USERNAME}")],
        [InlineKeyboardButton(text="🔙 Asosiy Menyu", callback_data="bot_main_menu")]
    ])
    if call.message:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


# ==================== ADMIN BUYRUQLARI ====================

def is_admin(message: Message) -> bool:
    user_id = message.from_user.id if message.from_user else 0
    return message.chat.id == settings.ADMIN_CHAT_ID or user_id == settings.ADMIN_CHAT_ID


@router.message(Command("myid"))
async def cmd_myid(message: Message):
    await message.answer(f"Ushbu chat ID: <code>{message.chat.id}</code>", parse_mode="HTML")


@router.message(Command("confirm_order"))
async def cmd_confirm_order(message: Message, command: CommandObject, bot: Bot):
    if not is_admin(message):
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
        await message.answer(f"✅ Buyurtma #{order_id} tasdiqlandi va PDF chipta mijozga yuborildi.")
    else:
        await message.answer(f"❌ Xatolik: {result['error']}")


@router.message(Command("reject_order"))
async def cmd_reject_order(message: Message, command: CommandObject, bot: Bot):
    if not is_admin(message):
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
        await message.answer(f"❌ Buyurtma #{order_id} rad etildi va mijozga xabar yuborildi.")
    else:
        await message.answer(f"❌ Xatolik: {result['error']}")

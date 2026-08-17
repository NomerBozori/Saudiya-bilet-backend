from aiogram import Router, Bot, F
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo
)

from config import settings
import database as db
from order_actions import confirm_order, reject_order

router = Router()

# ==================== ASOSIY MENYULAR ====================

def get_main_keyboard():
    # Agar WEBHOOK_BASE_URL berilgan bo'lsa, Mini App tugmasini qo'shamiz
    web_app_url = settings.WEBHOOK_BASE_URL
    
    buttons = []
    
    # 1-qator: Asosiy Mini App / Chipta qidirish
    if web_app_url and web_app_url.startswith("http"):
        buttons.append([
            InlineKeyboardButton(
                text="✈️ Aviachipta Qidirish (Mini App)",
                web_app=WebAppInfo(url=web_app_url)
            )
        ])
    
    # 2-qator: Xizmatlar
    buttons.append([
        InlineKeyboardButton(text="🕋 Umra Paketlari", callback_data="bot_menu_umrah"),
        InlineKeyboardButton(text="📑 Viza Xizmati", callback_data="bot_menu_visa")
    ])
    
    # 3-qator: Mehmonxona va Transfer
    buttons.append([
        InlineKeyboardButton(text="🏨 Mehmonxonalar", callback_data="bot_menu_hotels"),
        InlineKeyboardButton(text="🚖 VIP Transfer", callback_data="bot_menu_transfers")
    ])
    
    # 4-qator: Qaynoq takliflar va Aloqa
    buttons.append([
        InlineKeyboardButton(text="🔥 Qaynoq Reyslar", callback_data="bot_menu_hot"),
        InlineKeyboardButton(text="📞 Operator / Aloqa", callback_data="bot_menu_contact")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==================== /start BUYRUG'I ====================

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_name = message.from_user.first_name or "Hurmatli mijoz"
    
    welcome_text = (
        f"🕌 <b>Assalomu alaykum va rahmatullohi va barakotuh, {user_name}!</b>\n\n"
        f"🌟 <b>Umra & Saudiya Aviachiptalari</b> rasmiy tizimiga xush kelibsiz!\n\n"
        f"Biz orqali quyidagi xizmatlardan qulay va xavfsiz foydalanishingiz mumkin:\n"
        f"✈️ <b>Toshkent, Samarqand, Namangan</b> ➔ <b>Jidda, Madina</b> to'g'ridan-to'g'ri va tranzit reyslar;\n"
        f"🕋 <b>14 kunlik to'liq Umra ziyorat paketlari</b> (mehmonxona, 3 mahal taom, viza va gid bilan);\n"
        f"📑 <b>1 yillik Saudiya Multi-vizasi</b> va rasmiy Umra vizalarini rasmiylashtirish;\n"
        f"🏨 <b>Haramga yaqin mehmonxonalar</b> va 🚖 <b>Aeroport transferlari</b>.\n\n"
        f"👇 <i>Chiptalarni qidirish yoki kerakli bo'limni tanlash uchun quyidagi tugmalardan foydalaning:</i>"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )


# ==================== INLINE CALLBACK HANDLERLAR ====================

@router.callback_query(F.data == "bot_main_menu")
async def cb_main_menu(call: CallbackQuery):
    user_name = call.from_user.first_name or "Hurmatli mijoz"
    text = (
        f"🕌 <b>Asosiy Menyu</b>\n\n"
        f"Kerakli bo'limni tanlang:"
    )
    await call.message.edit_text(text, reply_markup=get_main_keyboard(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "bot_menu_umrah")
async def cb_umrah_packages(call: CallbackQuery):
    text = (
        "🕋 <b>MUQADDAS UMRA ZIYORAT PAKETLARI (14 KUN)</b>\n\n"
        "🌟 <b>1. EKONOM PAKET — $1,050</b>\n"
        "• To'g'ridan-to'g'ri aviaparvoz (Borish-qaytish)\n"
        "• Rasmiy viza va tibbiy sug'urta\n"
        "• Makka (800m, 24/7 bepul avtobus) + Madina (350m)\n"
        "• Kuniga 2 mahal issiq milliy taom\n"
        "• Tajribali ellikboshi va ziyoratlar\n"
        "• 5L Zam-Zam suvi, sumka, nimcha, kitobcha hadiya\n\n"
        "🌟 <b>2. STANDART PAKET — $1,250</b>\n"
        "• Makka: 4★ (400-500m piyoda) + Madina: 4★ (200m)\n"
        "• 2-3 mahal shved stoli taomlari\n"
        "• Qulay VIP avtobus transferi va Toif safari\n\n"
        "🌟 <b>3. VIP / LYUKS PAKET — $1,850</b>\n"
        "• Saudia Airlines to'g'ridan-to'g'ri VIP reys\n"
        "• Makka: 5★ Clock Tower (Haram ro'parasi)\n"
        "• Madina: 5★ Dar Al Taqwa / Oberoi (1-qator)\n"
        "• Shaxsiy GMC Yukon transfer va 24/7 xizmat\n\n"
        "<i>Buyurtma berish uchun operatorimiz bilan bog'laning:</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Operatorga Yozish", url="https://t.me/Saudiya_Admin")],
        [InlineKeyboardButton(text="🔙 Asosiy Menyu", callback_data="bot_main_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "bot_menu_visa")
async def cb_visa_services(call: CallbackQuery):
    text = (
        "📑 <b>SAUDIYA ARABISTONI VIZA XIZMATLARI</b>\n\n"
        "1️⃣ <b>1 Yillik Multi Turistik Viza — $130</b>\n"
        "• 1 yil davomida ko'p martalik kirish-chiqish\n"
        "• Har safar 90 kungacha qolish imkoniyati\n"
        "• Tayyor bo'lish vaqti: <b>24–48 soat</b>\n"
        "• Kerakli hujjat: Zagran pasport va 3.5x4.5 rasm\n\n"
        "2️⃣ <b>Rasmiy Umra Vizasi (Nusuk) — $160</b>\n"
        "• 90 kunlik rasmiy ziyorat vizasi va to'liq sug'urta\n"
        "• Tayyor bo'lish vaqti: <b>1–3 ish kuni</b>\n\n"
        "3️⃣ <b>Tijorat va Biznes Vizalari — $240</b> dan\n\n"
        "<i>Viza rasmiylashtirish uchun operatorimizga murojaat qiling:</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Viza Rasmiylashtirish", url="https://t.me/Saudiya_Admin")],
        [InlineKeyboardButton(text="🔙 Asosiy Menyu", callback_data="bot_main_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "bot_menu_hotels")
async def cb_hotels(call: CallbackQuery):
    text = (
        "🏨 <b>MAKKA VA MADINA MEHMONXONALARI</b>\n\n"
        "📍 <b>Makka Mukarrama:</b>\n"
        "• <b>Swissôtel Al Maqam 5★</b> — 0 metr (Clock Tower) — <i>$180/kecha</i>\n"
        "• <b>Anjum Hotel 5★</b> — 200 metr (Piyoda 3 daqiqa) — <i>$120/kecha</i>\n"
        "• <b>Al Kiswah Towers 4★</b> — 900m (Bepul 24/7 avtobus) — <i>$45/kecha</i>\n\n"
        "📍 <b>Madina Munavvara:</b>\n"
        "• <b>Dar Al Taqwa 5★</b> — 0 metr (Hovlida) — <i>$190/kecha</i>\n"
        "• <b>Pullman Zamzam 5★</b> — 150 metr — <i>$110/kecha</i>\n"
        "• <b>Artal Taiba 3★</b> — 350 metr — <i>$40/kecha</i>\n\n"
        "<i>Xona band qilish uchun operator bilan bog'laning:</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏨 Xona Band Qilish", url="https://t.me/Saudiya_Admin")],
        [InlineKeyboardButton(text="🔙 Asosiy Menyu", callback_data="bot_main_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "bot_menu_transfers")
async def cb_transfers(call: CallbackQuery):
    text = (
        "🚖 <b>SAUDIYA VIP TRANSFER XIZMATLARI</b>\n\n"
        "Yangi, qulay va konditsionerli avtomobillarda aeroportda kutib olish va eltib qo'yish:\n\n"
        "🛣 <b>Jidda Aeroport ➔ Makka Mehmonxona:</b>\n"
        "• Sedan (Camry / Sonata, 3-4 kishi) — <b>$45</b>\n"
        "• GMC Yukon / Chevrolet Tahoe (VIP, 6-7 kishi) — <b>$85</b>\n"
        "• Hyundai H1 Miniven (7-10 kishi) — <b>$70</b>\n\n"
        "🛣 <b>Makka ➔ Madina (Haramain Tezurar yoki Avtomobil):</b>\n"
        "• GMC VIP transfer — <b>$160</b>\n"
        "• Guruhli qulay avtobus — <b>$25/kishi</b>\n\n"
        "<i>Transfer buyurtma qilish uchun operatorga yozing:</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚖 Transfer Buyurtma Qilish", url="https://t.me/Saudiya_Admin")],
        [InlineKeyboardButton(text="🔙 Asosiy Menyu", callback_data="bot_main_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "bot_menu_hot")
async def cb_hot_deals(call: CallbackQuery):
    text = (
        "🔥 <b>ENG QAYNOQ VA CHEGIRMADAGI REYSLAR:</b>\n\n"
        "✈️ <b>Toshkent ➔ Jidda</b> (To'g'ridan-to'g'ri)\n"
        "   📅 Yaqin sanalarga | Narxi: <b>$370</b> dan\n\n"
        "✈️ <b>Namangan ➔ Jidda</b> (Flynas)\n"
        "   📅 Ushbu haftada | Narxi: <b>$370</b>\n\n"
        "✈️ <b>Samarqand ➔ Madina</b>\n"
        "   📅 Qulay reys | Narxi: <b>$310</b>\n\n"
        "🕋 <b>14 kunlik Ekonom Umra paketi</b>: <b>$1,050</b>\n\n"
        "⚡️ <i>Joylar soni cheklangan, hoziroq band qilishga shoshiling!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡️ Hoziroq Band Qilish", url="https://t.me/Saudiya_Admin")],
        [InlineKeyboardButton(text="🔙 Asosiy Menyu", callback_data="bot_main_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "bot_menu_contact")
async def cb_contact(call: CallbackQuery):
    text = (
        "📞 <b>BIZ BILAN BOG'LANISH VA QO'LLAB-QUVVATLASH</b>\n\n"
        "Savollaringiz bormi yoki chipta xarid qilmoqchimisiz? Biz 24/7 xizmatingizdamiz!\n\n"
        "👤 <b>Bosh Operator:</b> @Saudiya_Admin\n"
        "📱 <b>O'zbekiston tel:</b> +998 90 123 45 67\n"
        "🇸🇦 <b>Saudiya tel:</b> +966 50 123 4567\n"
        "📢 <b>Rasmiy Kanal:</b> @Saudiya_Biletla\n"
        "⏰ <b>Ish tartibi:</b> 24/7 uzluksiz\n\n"
        "<i>To'g'ridan-to'g'ri operatorga yozish uchun quyidagi tugmani bosing:</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Adminga Yozish", url="https://t.me/Saudiya_Admin")],
        [InlineKeyboardButton(text="📢 Kanalga A'zo Bo'lish", url="https://t.me/Saudiya_Biletla")],
        [InlineKeyboardButton(text="🔙 Asosiy Menyu", callback_data="bot_main_menu")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await call.answer()


# ==================== ADMIN BUYRUQLARI ====================

@router.message(Command("myid"))
async def cmd_myid(message: Message):
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
        await message.answer(f"✅ Buyurtma #{order_id} muvaffaqiyatli tasdiqlandi va elektron PDF chipta mijozga yuborildi.")
    else:
        await message.answer(f"❌ Xatolik: {result['error']}")


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
        await message.answer(f"❌ Buyurtma #{order_id} rad etildi va mijozga xabar yuborildi.")
    else:
        await message.answer(f"❌ Xatolik: {result['error']}")

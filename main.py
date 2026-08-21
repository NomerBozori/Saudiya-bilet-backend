import io
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from aiogram import Bot, Dispatcher
from aiogram.types import BufferedInputFile, Update
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import database as db
import travelpayouts as tp
from bot_handlers import router as bot_router
from config import settings
from keyboards import admin_order_keyboard
from order_actions import confirm_order as confirm_order_action
from order_actions import reject_order as reject_order_action

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("saudiya-bilet")

# Joriy build versiyasi — deploy yangilanganini tekshirish uchun (/api/version)
APP_BUILD = "v12"
APP_BUILD_FEATURES = [
    "avto-post 3-35 kun",
    "top-deals avto tavsiyalar",
    "arzon narxlar taqvimi",
    "boarding pass",
    "3D karta + nusxalash",
    "admin: o'chirish/tozalash/excel/CBU",
]

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()
dp.include_router(bot_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    webhook_url = f"{settings.WEBHOOK_BASE_URL.rstrip('/')}/webhook" if settings.WEBHOOK_BASE_URL else ""
    if webhook_url and webhook_url.startswith("http"):
        try:
            await bot.set_webhook(webhook_url, drop_pending_updates=False)
            log.info(f"Webhook o'rnatildi: {webhook_url}")
        except Exception as e:
            log.warning(f"Webhook o'rnatishda xatolik: {e}")
    yield
    try:
        await bot.session.close()
    except Exception as e:
        log.debug(f"Bot session yopishda xatolik: {e}")


app = FastAPI(title="Saudiya Biletlar API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Telegram Mini App statik fayllarni juda uzoq keshlaydi — natijada foydalanuvchi
# eski dizaynni ko'rib qoladi. HTML/JS/CSS uchun keshni butunlay o'chiramiz.
@app.middleware("http")
async def no_cache_for_static(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path.lower()
    if path.endswith((".html", ".js", ".css")) or path in ("/", "/admin/", "/admin"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# /admin -> /admin/ avtomatik redirect (StaticFiles mountdan OLDIN e'lon qilinadi)
@app.get("/admin", include_in_schema=False)
async def admin_redirect():
    return RedirectResponse(url="/admin/", status_code=307)


app.mount("/admin", StaticFiles(directory="admin_static", html=True), name="admin")


def verify_admin(x_admin_password: str = Header(default="")):
    if x_admin_password != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Noto'g'ri admin parol")
    return True


# ==================== TELEGRAM WEBHOOK ====================
@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        update = Update.model_validate(data)
        await dp.feed_update(bot, update)
    except Exception:
        log.exception("Telegram webhook xatosi")
    return {"ok": True}


# ==================== CHIPTA QIDIRUV ====================
@app.get("/api/search")
async def api_search(origin: str, destination: str, depart_date: str):
    origin_iata = tp.to_iata(origin)
    dest_iata = tp.to_iata(destination)

    # 1) Qo'lda qo'shilgan chiptalar
    try:
        manual = db.list_manual_flights(origin_iata, dest_iata, depart_date)
    except Exception:
        log.exception("manual_flights xatolik")
        manual = []

    manual_results = [{
        "origin": (f.get("origin") or origin_iata).upper(),
        "destination": (f.get("destination") or dest_iata).upper(),
        "price": f.get("price"),
        "airline": f.get("airline") or "Saudiya Biletlar",
        "flight_number": f.get("flight_number") or "SAU-001",
        "departure_at": f"{f.get('depart_date')}T{f.get('departure_time') or '09:30'}:00",
        "transfers": f.get("transfers", 0),
        "seats_available": f.get("seats_available", 10),
        "source": "manual",
        "manual_flight_id": f.get("id"),
    } for f in manual]

    # 2) Travelpayouts API
    try:
        api_results = await tp.search_flights(origin, destination, depart_date)
        for r in api_results:
            r["source"] = "api"
    except Exception:
        log.exception("search error")
        api_results = []

    return {"results": manual_results + api_results}


# ==================== BUYURTMA YARATISH ====================
@app.post("/api/orders")
async def api_create_order(payload: dict):
    required = ["telegram_user_id", "origin", "destination", "depart_date", "flight_data", "passport"]
    for field in required:
        if field not in payload:
            raise HTTPException(status_code=400, detail=f"'{field}' maydoni yo'q")

    flight_data = payload.get("flight_data") or {}
    price = payload.get("price")
    if price is None and isinstance(flight_data, dict):
        price = flight_data.get("price")

    order = db.create_order({
        "telegram_user_id": payload["telegram_user_id"],
        "username": payload.get("username"),
        "origin": str(payload["origin"]).upper(),
        "destination": str(payload["destination"]).upper(),
        "depart_date": payload["depart_date"],
        "passengers": payload.get("passengers", 1),
        "flight_data": flight_data,
        "price": price,
        "status": "new",
    })

    passport_data = payload.get("passport") or {}
    order_id = order.get("id")
    passport = db.save_passport(order_id, passport_data)

    first_n = passport.get("first_name") or "-"
    last_n = passport.get("last_name") or ""
    p_num = passport.get("passport_number") or "-"
    b_year = passport.get("birth_year") or "-"
    exp_date = passport.get("expiry_date") or "-"

    text = (
        f"🆕 <b>Yangi buyurtma #{order_id}</b>\n\n"
        f"👤 {first_n} {last_n}\n"
        f"🛂 Passport: {p_num}\n"
        f"📅 Tug'ilgan yil: {b_year}\n"
        f"⏳ Amal qilish: {exp_date}\n\n"
        f"✈️ {order.get('origin')} ➔ {order.get('destination')}\n"
        f"🗓 {order.get('depart_date')} | 👥 {order.get('passengers', 1)} yo'lovchi\n"
        f"💵 <b>${order.get('price', '-')} USD</b>\n\n"
        f"👇 Pastdagi tugmalar orqali 1 bosishda boshqaring:"
    )
    try:
        await bot.send_message(
            settings.ADMIN_CHAT_ID,
            text,
            parse_mode="HTML",
            reply_markup=admin_order_keyboard(order_id),
        )
    except Exception as e:
        log.warning(f"Admin guruhiga xabar yuborilmadi: {e}")

    return {"order_id": order_id}


# ==================== TO'LOV CHEKI ====================
@app.post("/api/orders/{order_id}/payment")
async def api_upload_payment(order_id: int, file: UploadFile = File(...)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    content = await file.read()
    filename = file.filename or "receipt.jpg"
    url = db.upload_file("payments", f"{order_id}_{filename}", content, file.content_type or "image/jpeg")
    db.update_order(order_id, {"payment_screenshot_url": url, "status": "awaiting_confirmation"})

    try:
        photo = BufferedInputFile(content, filename=filename)
        await bot.send_photo(
            settings.ADMIN_CHAT_ID,
            photo,
            caption=(
                f"💳 <b>To'lov cheki — buyurtma #{order_id}</b>\n\n"
                f"✈️ {(order.get('origin') or '').upper()} ➔ {(order.get('destination') or '').upper()}\n"
                f"🗓 {order.get('depart_date') or '-'} | 💵 <b>${order.get('price', '-')}</b>\n\n"
                f"👇 1 bosishda tasdiqlang yoki rad eting:"
            ),
            parse_mode="HTML",
            reply_markup=admin_order_keyboard(order_id),
        )
    except Exception as e:
        log.warning(f"Admin guruhiga to'lov cheki yuborilmadi: {e}")

    return {"ok": True, "url": url}


# ==================== MIJOZNING BUYURTMALARI TARIXI ====================
@app.get("/api/my-orders")
async def api_my_orders(telegram_user_id: int):
    try:
        orders = db.get_orders_by_user(telegram_user_id, limit=20)
        return {"orders": orders}
    except Exception:
        log.exception("my-orders xatolik")
        return {"orders": []}


# ==================== MARKAZIY BANK (CBU) JONLI KURSI ====================
CBU_USD_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/USD/"
_cbu_cache: dict = {"rate": None, "date": None, "diff": None, "ts": 0.0}
CBU_CACHE_TTL = 30 * 60  # 30 daqiqa
CBU_FALLBACK_RATE = 12850.0


async def get_cbu_usd_rate() -> dict:
    """Markaziy Bankdan (cbu.uz) USD/UZS jonli kursini oladi (30 daqiqa kesh)."""
    now = time.time()
    if _cbu_cache["rate"] and (now - _cbu_cache["ts"]) < CBU_CACHE_TTL:
        return {
            "rate": _cbu_cache["rate"],
            "date": _cbu_cache["date"],
            "diff": _cbu_cache["diff"],
            "source": "cbu.uz (kesh)",
        }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(CBU_USD_URL)
            r.raise_for_status()
            data = r.json()
            item = data[0] if isinstance(data, list) and data else data
            rate = float(str(item.get("Rate")).replace(",", "."))
            _cbu_cache.update({
                "rate": rate,
                "date": item.get("Date"),
                "diff": item.get("Diff"),
                "ts": now,
            })
            return {"rate": rate, "date": item.get("Date"), "diff": item.get("Diff"), "source": "cbu.uz"}
    except Exception as e:
        log.warning(f"CBU kursini olishda xatolik: {e}")
        return {
            "rate": _cbu_cache["rate"] or CBU_FALLBACK_RATE,
            "date": _cbu_cache["date"],
            "diff": _cbu_cache["diff"],
            "source": "zaxira",
        }


@app.get("/api/cbu-rate")
async def api_cbu_rate():
    """Markaziy Bankning jonli USD kursi (Mini App va admin panel uchun)."""
    return await get_cbu_usd_rate()


# ==================== 🔥 AVTO NARX TAVSIYALARI (TOP DEALS) ====================
_deals_cache: dict = {"data": None, "ts": 0.0}
DEALS_CACHE_TTL = 30 * 60  # 30 daqiqa


@app.get("/api/top-deals")
async def api_top_deals(limit: int = 8, refresh: bool = False):
    """Mini App ochilishida avtomatik ko'rsatiladigan eng arzon takliflar.

    O'zbekistonning 11 ta aeroportidan Jidda/Madinaga, faqat yaqin 3–35 kun
    ichidagi reyslar. Narxlar 30 daqiqa keshlanadi (avtomatik yangilanadi).
    """
    limit = max(1, min(int(limit or 8), 11))
    now = time.time()

    cached = _deals_cache.get("data")
    if cached and not refresh and (now - float(_deals_cache.get("ts") or 0)) < DEALS_CACHE_TTL:
        deals = cached
    else:
        try:
            tickets = await tp.get_daily_cheapest()
        except Exception:
            log.exception("Top-deals narxlarini olishda xatolik")
            tickets = []

        valid = tp.filter_offers_by_window([t for t in (tickets or []) if t.get("value") is not None])
        valid = tp.top_up_missing_cities(valid)
        picked = tp.pick_mixed_offers(valid, limit=11)

        deals = []
        for t in picked:
            try:
                price = round(float(t.get("value")), 2)
            except (TypeError, ValueError):
                continue
            origin = str(t.get("origin") or "").upper()
            dest = str(t.get("destination") or "").upper()
            deals.append({
                "origin": origin,
                "origin_name": t.get("origin_name") or tp.city_name(origin),
                "destination": dest,
                "destination_name": t.get("destination_name") or tp.city_name(dest),
                "price": price,
                "depart_date": t.get("depart_date"),
                "depart_date_label": t.get("depart_date_label") or tp.format_date_uz(t.get("depart_date")),
                "days_left": t.get("days_left"),
                "source": t.get("source") or "api",
            })

        deals.sort(key=lambda d: d["price"])
        for i, d in enumerate(deals):
            d["is_cheapest"] = i == 0
        _deals_cache.update({"data": deals, "ts": now})

    rate_info = await get_cbu_usd_rate()
    return {
        "deals": deals[:limit],
        "rate": rate_info.get("rate") or CBU_FALLBACK_RATE,
        "window": {"min_days": tp.MIN_DAYS_AHEAD, "max_days": tp.MAX_DAYS_AHEAD},
        "updated_at": datetime.now().strftime("%H:%M"),
    }


# ==================== ARZON NARXLAR TAQVIMI ====================
@app.get("/api/calendar")
async def api_calendar(
    origin: str = "TAS",
    destination: str = "JED",
    start_date: str | None = None,
    days: int = 30,
):
    """Har bir kun bo'yicha eng arzon narxlar (gorizontal taqvim uchun)."""
    origin_iata = tp.to_iata(origin)
    dest_iata = tp.to_iata(destination)

    try:
        calendar = await tp.get_calendar_prices(origin_iata, dest_iata, start_date, days)
    except Exception:
        log.exception("Taqvim narxlarini olishda xatolik")
        calendar = []

    # Qo'lda qo'shilgan chiptalar taqvimdagi narxlardan arzon bo'lsa — ularni ustun qo'yamiz
    try:
        manual = db.list_manual_flights(origin_iata, dest_iata, None)
    except Exception:
        manual = []

    manual_by_date: dict[str, float] = {}
    for f in manual:
        d = str(f.get("depart_date") or "")[:10]
        try:
            price = float(f.get("price"))
        except (TypeError, ValueError):
            continue
        if d and (d not in manual_by_date or price < manual_by_date[d]):
            manual_by_date[d] = price

    for day in calendar:
        m_price = manual_by_date.get(day["date"])
        if m_price is not None and (day.get("price") is None or m_price < float(day["price"])):
            day["price"] = m_price
            day["source"] = "manual"
            day["airline"] = "Saudiya Biletlar"

    prices = [float(d["price"]) for d in calendar if d.get("price") is not None]
    cheapest_price = min(prices) if prices else None
    cheapest_date = None
    if cheapest_price is not None:
        for d in calendar:
            if d.get("price") is not None and float(d["price"]) == cheapest_price:
                cheapest_date = d["date"]
                break
        for d in calendar:
            d["is_cheapest"] = d.get("date") == cheapest_date

    return {
        "origin": origin_iata,
        "destination": dest_iata,
        "origin_name": tp.city_name(origin_iata),
        "destination_name": tp.city_name(dest_iata),
        "cheapest_price": cheapest_price,
        "cheapest_date": cheapest_date,
        "days": calendar,
    }


# ==================== KANALGA CHIROYLI AVTO-POST ====================
@app.post("/api/cron/daily-post")
@app.get("/api/cron/daily-post")
async def api_daily_post(
    secret: str = "",
    limit: int = 11,
    min_days: int = tp.MIN_DAYS_AHEAD,
    max_days: int = tp.MAX_DAYS_AHEAD,
):
    """O'zbekistonning 11 ta xalqaro aeroportidan Jidda va Madinaga aralash reyslar posti.

    Faqat yaqin `min_days`–`max_days` (sukut bo'yicha 3–35) kun ichidagi sanalar chiqadi —
    uzoq dekabr/yanvar sanalari postga tushmaydi.
    """
    if secret != settings.CRON_SECRET:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    # Sana oynasini xavfsiz chegaralarga keltiramiz
    min_days = max(0, int(min_days))
    max_days = max(min_days, int(max_days))

    try:
        tickets = await tp.get_daily_cheapest(min_days=min_days, max_days=max_days)
    except Exception:
        log.exception("Kunlik narxlarni olishda xatolik")
        tickets = []

    # 1) Faqat narxi bor va sanasi 3–35 kun oynasiga tushadigan takliflar
    valid_tickets = tp.filter_offers_by_window(
        [t for t in (tickets or []) if t.get("value") is not None],
        min_days=min_days,
        max_days=max_days,
    )

    used_fallback = not valid_tickets

    # 2) API'dan tushmagan shaharlar zaxira (taxminiy) narxlar bilan to'ldiriladi,
    #    shunda kanal bo'sh qolmaydi va 11 ta aeroport ham qatnashadi
    valid_tickets = tp.top_up_missing_cities(
        valid_tickets,
        min_days=min_days,
        max_days=max_days,
    )

    # Turfa xil aralash reyslar: bitta shahar (aeroport) takrorlanmaydi
    selected = tp.pick_mixed_offers(valid_tickets, limit=max(1, min(int(limit or 11), 11)))
    if not selected:
        return {"posted": 0}

    rate_info = await get_cbu_usd_rate()
    uzs_rate = float(rate_info.get("rate") or CBU_FALLBACK_RATE)

    today_str = datetime.now().strftime("%d.%m.%Y")
    text = (
        "🕋 <b>SAUDIYA BILETLAR | BUGUNGI ENG ARZON REYSLAR</b> ✈️\n"
        f"📆 <i>{today_str}</i> — O'zbekistonning barcha aeroportlaridan Jidda va Madinaga\n"
        f"🗓 <i>Faqat yaqin {min_days}–{max_days} kun ichidagi reyslar:</i>\n\n"
    )

    for t in selected:
        origin = str(t.get("origin") or "").upper()
        dest = str(t.get("destination") or "").upper()
        val = int(float(t.get("value") or 380))
        val_uzs = f"{int(val * uzs_rate):,}".replace(",", " ")
        origin_name = t.get("origin_name") or tp.city_name(origin)
        dest_name = t.get("destination_name") or tp.city_name(dest)
        dest_icon = "🕋" if dest == "MED" else "🌅"
        date_label = t.get("depart_date_label") or tp.format_date_uz(t.get("depart_date"))
        days_left = t.get("days_left")
        if days_left is None:
            days_left = tp.days_until(t.get("depart_date"))
        days_note = f" — {days_left} kundan keyin" if days_left is not None else ""
        text += (
            f"{dest_icon} <b>{origin_name} ({origin}) ➔ {dest_name} ({dest})</b>\n"
            f"   📅 Sana: <code>{date_label}</code>{days_note}\n"
            f"   💵 Narxi: <b>${val}</b> (~{val_uzs} so'm)\n"
            f"   🧳 Bagaj: 30 kg + 7 kg | 🍽 Issiq taom bepul\n"
            f"   ──────────────\n"
        )

    text += (
        f"\n💱 Markaziy Bank kursi: <b>1$ = {int(uzs_rate):,}</b> so'm\n".replace(",", " ")
        + "⚡️ <i>Joylar soni cheklangan! Chipta band qilish uchun botga kiring:</i>\n"
        "👉 @Saudiya_Biletlarbot\n"
        f"👤 Savollar uchun: @{settings.ADMIN_USERNAME}"
    )

    try:
        await bot.send_message(settings.CHANNEL_ID, text, parse_mode="HTML")
        return {
            "posted": len(selected),
            "fallback": used_fallback,
            "window": {"min_days": min_days, "max_days": max_days},
            "cities": [str(t.get("origin") or "").upper() for t in selected],
            "dates": [t.get("depart_date") for t in selected],
        }
    except Exception as e:
        log.exception("Kanalga post yuborishda xatolik")
        raise HTTPException(status_code=500, detail=f"Kanalga xabar yuborishda xatolik: {e}")


# ==================== ADMIN PANEL ====================
@app.get("/api/admin/orders", dependencies=[Depends(verify_admin)])
async def admin_list_orders(status: str | None = None):
    orders = db.get_orders_with_passport(status=status)
    return {"orders": orders}


def _generate_excel_bytes(orders: list[dict], as_csv: bool = False) -> bytes:
    """Admin uchun buyurtmalarni Excel (xlsx) yoki CSV fayl sifatida generatsiya qiladi."""
    if HAS_OPENPYXL and not as_csv:
        wb = Workbook()
        ws = wb.active
        ws.title = "Buyurtmalar"

        headers = [
            "ID",
            "Ism",
            "Familiya",
            "Pasport Raqami",
            "Tug'ilgan yil",
            "Pasport Muddati",
            "Yo'nalish",
            "Sana",
            "Yo'lovchilar",
            "Narx ($)",
            "Holati",
            "Telegram ID",
            "Username",
            "To'lov Cheki URL",
            "Yaratilgan sana",
        ]

        header_fill = PatternFill(start_color="0F5132", end_color="0F5132", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=11)
        border = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0"),
        )
        center = Alignment(horizontal="center", vertical="center")
        left_align = Alignment(horizontal="left", vertical="center")

        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center
            cell.border = border

        STATUS_UZ = {
            "new": "Yangi",
            "awaiting_confirmation": "Tasdiq kutilmoqda",
            "confirmed": "Tasdiqlangan",
            "rejected": "Rad etilgan",
        }

        for row_idx, order in enumerate(orders, 2):
            p_raw = order.get("passports")
            if isinstance(p_raw, list) and len(p_raw) > 0 and isinstance(p_raw[0], dict):
                passport = p_raw[0]
            elif isinstance(p_raw, dict):
                passport = p_raw
            else:
                passport = {}

            route = f"{(order.get('origin') or '').upper()} -> {(order.get('destination') or '').upper()}"

            row = [
                order.get("id"),
                passport.get("first_name") or "",
                passport.get("last_name") or "",
                passport.get("passport_number") or "",
                passport.get("birth_year") or "",
                passport.get("expiry_date") or "",
                route,
                order.get("depart_date") or "",
                order.get("passengers") or 1,
                order.get("price") or "",
                STATUS_UZ.get(order.get("status"), order.get("status") or ""),
                order.get("telegram_user_id") or "",
                order.get("username") or "",
                order.get("payment_screenshot_url") or "",
                str(order.get("created_at") or "")[:19],
            ]

            for col_idx, val in enumerate(row, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.border = border
                cell.alignment = left_align if col_idx in (2, 3, 4, 13, 14) else center
                if row_idx % 2 == 0:
                    cell.fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

        # Auto width
        widths = [6, 14, 14, 16, 10, 14, 16, 12, 10, 10, 18, 14, 14, 28, 18]
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w

        ws.auto_filter.ref = ws.dimensions
        ws.freeze_panes = "A2"

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf.read()
    else:
        # Fallback: CSV (Excel ham ochadi)
        import csv

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "ID", "Ism", "Familiya", "Pasport", "Tugilgan yil", "Muddat",
            "Yonalish", "Sana", "Yolovchilar", "Narx", "Holati", "Telegram ID", "Username", "Chek URL"
        ])
        for order in orders:
            p_raw = order.get("passports")
            if isinstance(p_raw, list) and p_raw and isinstance(p_raw[0], dict):
                passport = p_raw[0]
            elif isinstance(p_raw, dict):
                passport = p_raw
            else:
                passport = {}
            writer.writerow([
                order.get("id"),
                passport.get("first_name"),
                passport.get("last_name"),
                passport.get("passport_number"),
                passport.get("birth_year"),
                passport.get("expiry_date"),
                f"{order.get('origin')}->{order.get('destination')}",
                order.get("depart_date"),
                order.get("passengers"),
                order.get("price"),
                order.get("status"),
                order.get("telegram_user_id"),
                order.get("username"),
                order.get("payment_screenshot_url"),
            ])
        return buf.getvalue().encode("utf-8-sig")


@app.get("/api/admin/orders/export", dependencies=[Depends(verify_admin)])
async def admin_export_orders(status: str | None = None, format: str = "csv"):
    """Buyurtmalarni Excel (xlsx) yoki CSV formatida eksport qilish.

    format=csv  -> Excel ochadigan CSV (UTF-8 BOM bilan)
    format=xlsx -> chiroyli formatlangan Excel fayl (openpyxl bo'lsa)
    """
    orders = db.get_orders_with_passport(status=status if status else None)

    fmt = (format or "csv").strip().lower()
    as_csv = fmt == "csv" or not HAS_OPENPYXL
    data_bytes = _generate_excel_bytes(orders, as_csv=as_csv)

    ext = "csv" if as_csv else "xlsx"
    filename = f"buyurtmalar_{datetime.now().strftime('%Y-%m-%d')}.{ext}"
    media_type = (
        "text/csv; charset=utf-8"
        if as_csv
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    return StreamingResponse(
        io.BytesIO(data_bytes),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/api/admin/orders/{order_id}/confirm", dependencies=[Depends(verify_admin)])
async def admin_confirm_order(order_id: int):
    result = await confirm_order_action(bot, order_id)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/admin/orders/{order_id}/reject", dependencies=[Depends(verify_admin)])
async def admin_reject_order(order_id: int, payload: dict):
    reason = payload.get("reason", "To'lov tasdiqlanmadi")
    result = await reject_order_action(bot, order_id, reason)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.delete("/api/admin/orders/rejected", dependencies=[Depends(verify_admin)])
@app.post("/api/admin/orders/clear-rejected", dependencies=[Depends(verify_admin)])
async def admin_clear_rejected_orders():
    """[🗑 Rad etilganlarni tozalash] — barcha rad etilgan buyurtmalarni o'chiradi."""
    try:
        deleted = db.delete_orders_by_status("rejected")
        return {"ok": True, "deleted": deleted}
    except Exception as e:
        log.exception("Rad etilgan buyurtmalarni tozalashda xatolik")
        raise HTTPException(status_code=500, detail=f"Tozalashda xatolik: {e}")


@app.delete("/api/admin/orders/{order_id}", dependencies=[Depends(verify_admin)])
async def admin_delete_order(order_id: int):
    """Oxirgi o'chirish tugmasi – buyurtmani to'liq o'chirish."""
    try:
        db.delete_order(order_id)
        return {"ok": True, "deleted_id": order_id}
    except Exception as e:
        log.exception(f"Buyurtmani o'chirishda xatolik #{order_id}")
        raise HTTPException(status_code=500, detail=f"O'chirishda xatolik: {e}")


@app.get("/api/admin/flights", dependencies=[Depends(verify_admin)])
async def admin_list_flights():
    return {"flights": db.list_all_manual_flights()}


@app.post("/api/admin/flights", dependencies=[Depends(verify_admin)])
async def admin_create_flight(payload: dict):
    required = ["origin", "destination", "depart_date", "price"]
    for field in required:
        if field not in payload or payload[field] is None or str(payload[field]).strip() == "":
            raise HTTPException(status_code=400, detail=f"'{field}' maydoni to'ldirilmagan")

    origin_code = tp.to_iata(str(payload["origin"])).lower()
    dest_code = tp.to_iata(str(payload["destination"])).lower()

    try:
        price = float(payload["price"])
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Narx son bo'lishi kerak")

    seats = payload.get("seats_available")
    if seats is not None:
        try:
            seats = int(seats)
        except (ValueError, TypeError):
            seats = None

    flight = db.create_manual_flight({
        "origin": origin_code,
        "destination": dest_code,
        "depart_date": str(payload["depart_date"]).strip(),
        "departure_time": payload.get("departure_time") or None,
        "price": price,
        "airline": payload.get("airline") or "Saudiya Biletlar",
        "flight_number": payload.get("flight_number") or None,
        "transfers": int(payload.get("transfers", 0) or 0),
        "seats_available": seats,
        "is_active": True,
    })
    return {"flight": flight}


@app.delete("/api/admin/flights/{flight_id}", dependencies=[Depends(verify_admin)])
async def admin_delete_flight(flight_id: int):
    db.delete_manual_flight(flight_id)
    return {"ok": True}


@app.post("/api/admin/login")
async def admin_login(payload: dict):
    if payload.get("password") != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Noto'g'ri parol")
    return {"ok": True}


@app.get("/api/health")
async def api_health():
    return {
        "status": "ok",
        "service": "Saudiya Biletlar backend faol ishlayapti",
        "build": APP_BUILD,
    }


@app.get("/api/version")
async def api_version():
    """Qaysi build jonli ishlayotganini tekshirish uchun (eski deployni aniqlash)."""
    return {
        "build": APP_BUILD,
        "features": APP_BUILD_FEATURES,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/payment-info")
async def api_payment_info():
    return {
        "card_number": settings.PAYMENT_CARD_NUMBER,
        "card_owner": settings.PAYMENT_CARD_OWNER,
        "admin_username": settings.ADMIN_USERNAME,
    }


# ==================== MINI APP FRONTEND STATIC MOUNT ====================
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

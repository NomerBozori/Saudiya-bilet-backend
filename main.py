import logging
import os
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.types import BufferedInputFile, Update
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import database as db
import travelpayouts as tp
from bot_handlers import router as bot_router
from config import settings
from order_actions import confirm_order as confirm_order_action
from order_actions import reject_order as reject_order_action

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("saudiya-bilet")

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
        f"To'lov cheki kelgach tasdiqlash uchun:\n"
        f"<code>/confirm_order {order_id}</code>"
    )
    try:
        await bot.send_message(settings.ADMIN_CHAT_ID, text, parse_mode="HTML")
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
                f"Tasdiqlash: <code>/confirm_order {order_id}</code>\n"
                f"Rad etish: <code>/reject_order {order_id} &lt;sabab&gt;</code>"
            ),
            parse_mode="HTML"
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


# ==================== KANALGA CHIROYLI AVTO-POST ====================
@app.post("/api/cron/daily-post")
@app.get("/api/cron/daily-post")
async def api_daily_post(secret: str = ""):
    if secret != settings.CRON_SECRET:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    tickets = await tp.get_daily_cheapest()
    if not tickets:
        return {"posted": 0}

    valid_tickets = [t for t in tickets if t.get("value") is not None]
    if not valid_tickets:
        return {"posted": 0}

    cheapest = sorted(valid_tickets, key=lambda x: float(x.get("value") or 999999))[:4]
    
    UZS_RATE = 12850  # Taxminiy so'm kursi

    text = (
        "🕋 <b>SAUDIYA BILETLAR | BUGUNGI ENG ARZON REYSLAR</b> ✈️\n\n"
        "Jidda va Madinaga eng hamyonbop aviachiptalar narxlari:\n\n"
    )
    
    for t in cheapest:
        val = int(t.get("value") or 380)
        val_uzs = f"{val * UZS_RATE:,}".replace(",", " ")
        text += (
            f"🔹 <b>{t['origin']} ➔ {t['destination']}</b>\n"
            f"   📅 Sana: <code>{t.get('depart_date', 'Yaqin kunlar')}</code>\n"
            f"   💵 Narxi: <b>${val}</b> (~{val_uzs} so'm)\n"
            f"   🧳 Bagaj: 30 kg + 7 kg | 🍽 Issiq taom bepul\n"
            f"   ──────────────\n"
        )

    text += (
        "\n⚡️ <i>Joylar soni cheklangan! Chipta band qilish uchun botga kiring:</i>\n"
        "👉 @Saudiya_Biletlarbot\n"
        f"👤 Savollar uchun: @{settings.ADMIN_USERNAME}"
    )

    try:
        await bot.send_message(settings.CHANNEL_ID, text, parse_mode="HTML")
        return {"posted": len(cheapest)}
    except Exception as e:
        log.exception("Kanalga post yuborishda xatolik")
        raise HTTPException(status_code=500, detail=f"Kanalga xabar yuborishda xatolik: {e}")


# ==================== ADMIN PANEL ====================
@app.get("/api/admin/orders", dependencies=[Depends(verify_admin)])
async def admin_list_orders(status: str | None = None):
    orders = db.get_orders_with_passport(status=status)
    return {"orders": orders}


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
    return {"status": "ok", "service": "Saudiya Biletlar backend faol ishlayapti"}


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

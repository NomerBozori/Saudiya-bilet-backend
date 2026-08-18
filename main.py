import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, UploadFile, File, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher
from aiogram.types import Update, BufferedInputFile

from config import settings
import database as db
import travelpayouts as tp
from bot_handlers import router as bot_router
from order_actions import confirm_order as confirm_order_action, reject_order as reject_order_action

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("saudiya-bilet")

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()
dp.include_router(bot_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    webhook_url = f"{settings.WEBHOOK_BASE_URL}/webhook"
    await bot.set_webhook(webhook_url, drop_pending_updates=False)
    log.info(f"Webhook o'rnatildi: {webhook_url}")
    yield


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
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.get("/")
async def root():
    return {"status": "ok", "service": "Saudiya Biletlar backend faol ishlayapti"}


# ==================== CHIPTA QIDIRUV ====================
@app.get("/api/search")
async def api_search(origin: str, destination: str, depart_date: str):
    # 1) Qo'lda qo'shilgan chiptalar
    try:
        manual = db.list_manual_flights(origin, destination, depart_date)
    except Exception as e:
        log.exception("manual_flights xatolik")
        manual = []

    manual_results = [{
        "origin": origin.upper(),
        "destination": destination.upper(),
        "price": f["price"],
        "airline": f.get("airline", "Saudiya Biletlar"),
        "flight_number": f.get("flight_number", "SAU-001"),
        "departure_at": f"{f['depart_date']}T{f.get('departure_time') or '09:30'}:00",
        "transfers": f.get("transfers", 0),
        "seats_available": f.get("seats_available", 10),
        "source": "manual",
        "manual_flight_id": f["id"],
    } for f in manual]

    # 2) Travelpayouts API
    try:
        api_results = await tp.search_flights(origin, destination, depart_date)
        for r in api_results:
            r["source"] = "api"
    except Exception as e:
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

    order = db.create_order({
        "telegram_user_id": payload["telegram_user_id"],
        "username": payload.get("username"),
        "origin": payload["origin"],
        "destination": payload["destination"],
        "depart_date": payload["depart_date"],
        "passengers": payload.get("passengers", 1),
        "flight_data": payload["flight_data"],
        "price": payload["flight_data"].get("price"),
        "status": "new",
    })
    passport = db.save_passport(order["id"], payload["passport"])

    text = (
        f"🆕 <b>Yangi buyurtma #{order['id']}</b>\n\n"
        f"👤 {passport['first_name']} {passport['last_name']}\n"
        f"🛂 Passport: {passport['passport_number']}\n"
        f"📅 Tug'ilgan yil: {passport['birth_year']}\n"
        f"⏳ Amal qilish: {passport['expiry_date']}\n\n"
        f"✈️ {order['origin']} ➔ {order['destination']}\n"
        f"🗓 {order['depart_date']} | 👥 {order['passengers']} yo'lovchi\n"
        f"💵 <b>${order['price']} USD</b>\n\n"
        f"To'lov cheki kelgach tasdiqlash uchun:\n"
        f"<code>/confirm_order {order['id']}</code>"
    )
    await bot.send_message(settings.ADMIN_CHAT_ID, text, parse_mode="HTML")
    return {"order_id": order["id"]}


# ==================== TO'LOV CHEKI ====================
@app.post("/api/orders/{order_id}/payment")
async def api_upload_payment(order_id: int, file: UploadFile = File(...)):
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Buyurtma topilmadi")

    content = await file.read()
    url = db.upload_file("payments", f"{order_id}_{file.filename}", content, file.content_type or "image/jpeg")
    db.update_order(order_id, {"payment_screenshot_url": url, "status": "awaiting_confirmation"})

    photo = BufferedInputFile(content, filename=file.filename)
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
    return {"ok": True, "url": url}


# ==================== MIJOZNING BUYURTMALARI TARIXI ====================
@app.get("/api/my-orders")
async def api_my_orders(telegram_user_id: int):
    try:
        res = db.supabase.table("orders").select("*, passports(*)").eq("telegram_user_id", telegram_user_id).order("id", desc=True).limit(20).execute()
        return {"orders": res.data or []}
    except Exception as e:
        log.exception("my-orders xatolik")
        return {"orders": []}


# ==================== KANALGA CHIROYLI AVTO-POST ====================
@app.post("/api/cron/daily-post")
async def api_daily_post(secret: str):
    if secret != settings.CRON_SECRET:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    tickets = await tp.get_daily_cheapest()
    if not tickets:
        return {"posted": 0}

    cheapest = sorted(tickets, key=lambda x: x.get("value") or 999999)[:4]
    
    UZS_RATE = 12850  # Taxminiy so'm kursi

    text = (
        "🕋 <b>SAUDIYA BILETLAR | BUGUNGI ENG ARZON REYSLAR</b> ✈️\n\n"
        "Jidda va Madinaga eng hamyonbop aviachiptalar narxlari:\n\n"
    )
    
    for t in cheapest:
        val = int(t.get("value", 380))
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
        "👤 Savollar uchun: @nuriddinovdfg"
    )

    await bot.send_message(settings.CHANNEL_ID, text, parse_mode="HTML")
    return {"posted": len(cheapest)}


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
        if field not in payload or not payload[field]:
            raise HTTPException(status_code=400, detail=f"'{field}' maydoni to'ldirilmagan")

    flight = db.create_manual_flight({
        "origin": payload["origin"].strip().lower(),
        "destination": payload["destination"].strip().lower(),
        "depart_date": payload["depart_date"],
        "departure_time": payload.get("departure_time"),
        "price": payload["price"],
        "airline": payload.get("airline", "Saudiya Biletlar"),
        "flight_number": payload.get("flight_number"),
        "transfers": payload.get("transfers", 0),
        "seats_available": payload.get("seats_available"),
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

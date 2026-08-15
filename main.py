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
log = logging.getLogger("umra-chipta")

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()
dp.include_router(bot_router)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ilova ishga tushganda Telegram webhook'ni o'rnatamiz
    webhook_url = f"{settings.WEBHOOK_BASE_URL}/webhook"
    await bot.set_webhook(webhook_url, drop_pending_updates=False)
    log.info(f"Webhook o'rnatildi: {webhook_url}")
    yield
    # Eslatma: shutdown paytida webhookni ATAYLAB o'chirmaymiz —
    # Render'ning bepul tarifi tez-tez qayta ishga tushadi va bu webhookni
    # bo'shatib qo'yishi mumkin edi.


app = FastAPI(title="Umra Chipta API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Xohlasangiz faqat Vercel domeningizni yozing
    allow_methods=["*"],
    allow_headers=["*"],
)

# Admin panel — https://SIZNING-BACKEND.onrender.com/admin manzilida ochiladi
app.mount("/admin", StaticFiles(directory="admin_static", html=True), name="admin")


def verify_admin(x_admin_password: str = Header(default="")):
    """Admin API endpointlarini himoya qiladi. So'rov header'ida X-Admin-Password kerak."""
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
    return {"status": "ok", "service": "Umra Chipta backend ishlayapti"}


# ==================== CHIPTA QIDIRUV ====================
@app.get("/api/search")
async def api_search(origin: str, destination: str, depart_date: str):
    # 1) O'zimiz (admin panel orqali) qo'lda qo'shgan chiptalar — har doim birinchi ko'rsatiladi
    try:
        manual = db.list_manual_flights(origin, destination, depart_date)
    except Exception as e:
        log.exception("manual_flights so'rovida xato (jadval hali yaratilmagan bo'lishi mumkin)")
        manual = []

    manual_results = [{
        "origin": origin.upper(),
        "destination": destination.upper(),
        "price": f["price"],
        "airline": f.get("airline"),
        "flight_number": f.get("flight_number"),
        "departure_at": f"{f['depart_date']}T{f.get('departure_time') or '00:00'}:00",
        "transfers": f.get("transfers", 0),
        "seats_available": f.get("seats_available"),
        "source": "manual",
        "manual_flight_id": f["id"],
    } for f in manual]

    # 2) Travelpayouts API'dan real vaqtdagi narxlar
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
        f"⏳ Amal qilish muddati: {passport['expiry_date']}\n\n"
        f"✈️ {order['origin']} → {order['destination']}\n"
        f"🗓 {order['depart_date']}, {order['passengers']} yo'lovchi\n"
        f"💵 {order['price']} USD\n\n"
        f"To'lov cheki kelgach tasdiqlash uchun:\n"
        f"<code>/confirm_order {order['id']}</code>"
    )
    await bot.send_message(settings.ADMIN_CHAT_ID, text, parse_mode="HTML")
    return {"order_id": order["id"]}


# ==================== TO'LOV CHEKINI YUKLASH ====================
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
            f"💳 To'lov cheki — buyurtma #{order_id}\n\n"
            f"Tasdiqlash: /confirm_order {order_id}\n"
            f"Rad etish: /reject_order {order_id} <sabab>"
        ),
    )
    return {"ok": True, "url": url}


# ==================== KUNLIK AVTO-POST (tashqi cron orqali chaqiriladi) ====================
@app.post("/api/cron/daily-post")
async def api_daily_post(secret: str):
    if secret != settings.CRON_SECRET:
        raise HTTPException(status_code=403, detail="Ruxsat yo'q")

    tickets = await tp.get_daily_cheapest()
    if not tickets:
        return {"posted": 0}

    cheapest = sorted(tickets, key=lambda x: x.get("value") or 999999)[:3]
    text = "🔥 <b>Bugungi eng arzon chiptalar</b>\n\n"
    for t in cheapest:
        text += f"✈️ {t['origin']} → {t['destination']}: <b>${t['value']}</b> ({t.get('depart_date', '-')})\n"
    text += "\nBuyurtma qilish uchun botga /start yozing 👇"

    await bot.send_message(settings.CHANNEL_ID, text, parse_mode="HTML")
    return {"posted": len(cheapest)}


# ==================== ADMIN PANEL: BUYURTMALAR ====================
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


# ==================== ADMIN PANEL: QO'LDA CHIPTA QO'SHISH ====================
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
        "airline": payload.get("airline", "Umra Chipta"),
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
    """Admin panel login sahifasi shu orqali parolni tekshiradi."""
    if payload.get("password") != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Noto'g'ri parol")
    return {"ok": True}

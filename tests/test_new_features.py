"""Yangi funksiyalar uchun testlar: avto-post, taqvim, inline tugmalar, admin panel."""
import os
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("BOT_TOKEN", "123456:fake_bot_token_for_testing")
os.environ.setdefault("ADMIN_CHAT_ID", "-100123456789")
os.environ.setdefault("CHANNEL_ID", "-100987654321")
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy")
os.environ.setdefault("TRAVELPAYOUTS_TOKEN", "dummy_travelpayouts_token")
os.environ.setdefault("WEBHOOK_BASE_URL", "https://example.com")
os.environ.setdefault("ADMIN_PASSWORD", "testpass")
os.environ.setdefault("CRON_SECRET", "testcron")

from httpx import ASGITransport, AsyncClient  # noqa: E402

import bot_handlers  # noqa: E402
import database as db  # noqa: E402
import main  # noqa: E402
import travelpayouts as tp  # noqa: E402
from keyboards import admin_order_keyboard  # noqa: E402
from main import app  # noqa: E402


# ==================== 1. AVTO-POST: 11 TA AEROPORT ====================
def test_uz_airports_list():
    assert tp.UZ_AIRPORTS == ["TAS", "NMA", "SKD", "FEG", "BHK", "AZN", "UGC", "TMJ", "NVI", "KSQ", "NCU"]
    assert len(tp.UZ_AIRPORTS) == 11
    assert tp.SAUDI_DESTINATIONS == ["JED", "MED"]


def test_fallback_offers_cover_all_airports():
    offers = tp.build_fallback_offers()
    origins = {o["origin"] for o in offers}
    assert origins == set(tp.UZ_AIRPORTS)
    assert {o["destination"] for o in offers} == {"JED", "MED"}
    assert all(o["value"] > 0 for o in offers)


def test_pick_mixed_offers_no_duplicate_cities():
    offers = tp.build_fallback_offers()
    picked = tp.pick_mixed_offers(offers, limit=11)
    origins = [p["origin"] for p in picked]
    assert len(origins) == 11
    assert len(set(origins)) == 11, "Bitta shahar ikki marta takrorlanmasligi kerak"
    dests = {p["destination"] for p in picked}
    assert dests == {"JED", "MED"}, "Jidda va Madina aralash bo'lishi kerak"


def test_pick_mixed_offers_picks_cheapest_per_city():
    offers = [
        {"origin": "TAS", "destination": "JED", "value": 500},
        {"origin": "TAS", "destination": "JED", "value": 300},
        {"origin": "NMA", "destination": "MED", "value": 410},
    ]
    picked = tp.pick_mixed_offers(offers, limit=5)
    tas = [p for p in picked if p["origin"] == "TAS"][0]
    assert tas["value"] == 300
    assert len(picked) == 2


@pytest.mark.asyncio
async def test_daily_post_mixes_all_airports():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("travelpayouts.get_daily_cheapest", return_value=[]), \
             patch("main.get_cbu_usd_rate", new=AsyncMock(return_value={"rate": 12500.0})), \
             patch("main.bot.send_message", new_callable=AsyncMock) as mock_send:
            res = await ac.post("/api/cron/daily-post?secret=testcron")
    assert res.status_code == 200
    body = res.json()
    assert body["posted"] == 11
    assert len(set(body["cities"])) == 11
    text = mock_send.await_args.args[1]
    for code in tp.UZ_AIRPORTS:
        assert code in text
    assert "JED" in text and "MED" in text


# ==================== 1B. AVTO-POST SANA OYNASI: 3–35 KUN ====================
def test_window_constants():
    assert tp.MIN_DAYS_AHEAD == 3
    assert tp.MAX_DAYS_AHEAD == 35


def test_is_within_window():
    today = date(2026, 8, 21)
    assert tp.is_within_window("2026-08-24", today=today) is True   # +3 kun
    assert tp.is_within_window("2026-09-25", today=today) is True   # +35 kun
    assert tp.is_within_window("2026-08-22", today=today) is False  # +1 kun (juda yaqin)
    assert tp.is_within_window("2026-09-26", today=today) is False  # +36 kun
    assert tp.is_within_window("2026-12-15", today=today) is False  # uzoq dekabr
    assert tp.is_within_window("2027-01-10", today=today) is False  # uzoq yanvar
    assert tp.is_within_window("2026-08-01", today=today) is False  # o'tgan sana
    assert tp.is_within_window(None, today=today) is False


def test_filter_offers_by_window_drops_far_dates():
    today = date(2026, 8, 21)
    offers = [
        {"origin": "TAS", "destination": "JED", "value": 300, "depart_date": "2026-09-01"},
        {"origin": "NMA", "destination": "MED", "value": 280, "depart_date": "2026-12-20"},
        {"origin": "SKD", "destination": "JED", "value": 290, "depart_date": "2027-01-05"},
        {"origin": "FEG", "destination": "MED", "value": 310, "depart_date": None},
    ]
    kept = tp.filter_offers_by_window(offers, today=today)
    assert [o["origin"] for o in kept] == ["TAS"]
    assert kept[0]["days_left"] == 11
    assert kept[0]["depart_date_label"].startswith("01.09.2026")


def test_fallback_offers_only_inside_window():
    today = date.today()
    offers = tp.build_fallback_offers()
    assert offers, "Zaxira takliflar bo'sh bo'lmasligi kerak"
    for o in offers:
        left = (date.fromisoformat(o["depart_date"]) - today).days
        assert tp.MIN_DAYS_AHEAD <= left <= tp.MAX_DAYS_AHEAD, f"{o['origin']} sanasi oynadan tashqarida"


def test_top_up_missing_cities_fills_all_airports():
    offers = [{"origin": "TAS", "destination": "JED", "value": 300,
               "depart_date": (date.today() + timedelta(days=5)).isoformat()}]
    topped = tp.top_up_missing_cities(offers)
    origins = {o["origin"] for o in topped}
    assert origins == set(tp.UZ_AIRPORTS)
    assert len([o for o in topped if o["origin"] == "TAS"]) == 1, "Mavjud shahar takrorlanmasligi kerak"


def test_format_date_uz():
    assert tp.format_date_uz("2026-08-21") == "21.08.2026 (Juma)"


@pytest.mark.asyncio
async def test_daily_post_excludes_far_dates():
    """API uzoq dekabr/yanvar sanalarini qaytarsa ham, postga tushmasligi kerak."""
    soon = (date.today() + timedelta(days=7)).isoformat()
    far = (date.today() + timedelta(days=120)).isoformat()
    api_offers = [
        {"origin": "TAS", "destination": "JED", "value": 300, "depart_date": soon},
        {"origin": "NMA", "destination": "MED", "value": 250, "depart_date": far},
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("travelpayouts.get_daily_cheapest", new=AsyncMock(return_value=api_offers)), \
             patch("main.get_cbu_usd_rate", new=AsyncMock(return_value={"rate": 12500.0})), \
             patch("main.bot.send_message", new_callable=AsyncMock) as mock_send:
            res = await ac.post("/api/cron/daily-post?secret=testcron")

    assert res.status_code == 200
    body = res.json()
    assert body["window"] == {"min_days": 3, "max_days": 35}
    assert far not in body["dates"], "Uzoq sana postga tushmasligi kerak"
    assert soon in body["dates"]

    today = date.today()
    for iso in body["dates"]:
        left = (date.fromisoformat(iso) - today).days
        assert 3 <= left <= 35

    text = mock_send.await_args.args[1]
    assert "2026-12" not in text and "2027-01" not in text
    assert len(set(body["cities"])) == 11


@pytest.mark.asyncio
async def test_get_daily_cheapest_filters_api_dates():
    soon = (date.today() + timedelta(days=9)).isoformat()
    far = (date.today() + timedelta(days=200)).isoformat()

    async def fake_route(client, origin, destination, min_days, max_days, today=None):
        return [
            {"origin": origin, "destination": destination, "value": 300, "depart_date": soon},
            {"origin": origin, "destination": destination, "value": 200, "depart_date": far},
        ]

    with patch.object(tp, "_fetch_route_offers", new=fake_route):
        offers = await tp.get_daily_cheapest(origins=["TAS"], destinations=["JED"])

    assert len(offers) == 1
    assert offers[0]["depart_date"] == soon


# ==================== 2. ARZON NARXLAR TAQVIMI ====================
@pytest.mark.asyncio
async def test_calendar_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(db, "list_manual_flights", return_value=[]), \
             patch("travelpayouts.get_calendar_prices", new=AsyncMock(return_value=[
                 {"date": "2026-09-01", "price": 400.0, "airline": "HY", "flight_number": "601", "transfers": 0, "source": "api"},
                 {"date": "2026-09-02", "price": 350.0, "airline": "XY", "flight_number": "612", "transfers": 0, "source": "api"},
             ])):
            res = await ac.get("/api/calendar?origin=Toshkent&destination=jidda&days=2")
    assert res.status_code == 200
    data = res.json()
    assert data["origin"] == "TAS"
    assert data["destination"] == "JED"
    assert data["cheapest_price"] == 350.0
    assert data["cheapest_date"] == "2026-09-02"
    assert len(data["days"]) == 2
    assert data["days"][1]["is_cheapest"] is True


@pytest.mark.asyncio
async def test_calendar_prefers_cheaper_manual_flight():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(db, "list_manual_flights", return_value=[
                 {"depart_date": "2026-09-01", "price": 199}
             ]), \
             patch("travelpayouts.get_calendar_prices", new=AsyncMock(return_value=[
                 {"date": "2026-09-01", "price": 400.0, "source": "api"},
             ])):
            res = await ac.get("/api/calendar?origin=TAS&destination=JED&days=1")
    day = res.json()["days"][0]
    assert day["price"] == 199
    assert day["source"] == "manual"


def test_calendar_pseudo_price_is_stable():
    a = tp._pseudo_price("TAS", "JED", "2026-09-01")
    b = tp._pseudo_price("TAS", "JED", "2026-09-01")
    assert a == b and a > 0


# ==================== 3. TELEGRAM ADMIN 1-CLICK TUGMALARI ====================
def test_admin_order_keyboard_buttons():
    kb = admin_order_keyboard(42)
    row = kb.inline_keyboard[0]
    assert row[0].text == "✅ Tasdiqlash & PDF"
    assert row[0].callback_data == "adm_confirm:42"
    assert row[1].text == "❌ Rad etish"
    assert row[1].callback_data == "adm_reject:42"


def _fake_callback(data: str, admin: bool = True):
    call = MagicMock()
    call.data = data
    call.from_user.id = -100123456789 if admin else 555
    call.message.chat.id = -100123456789 if admin else 555
    call.message.caption = None
    call.message.text = "🆕 Yangi buyurtma #42"
    call.message.edit_text = AsyncMock()
    call.message.edit_caption = AsyncMock()
    call.message.edit_reply_markup = AsyncMock()
    call.message.answer = AsyncMock()
    call.answer = AsyncMock()
    return call


@pytest.mark.asyncio
async def test_callback_confirm_sends_pdf():
    call = _fake_callback("adm_confirm:42")
    bot_mock = AsyncMock()
    with patch.object(bot_handlers, "confirm_order", new=AsyncMock(return_value={"ok": True})) as mock_confirm:
        await bot_handlers.cb_admin_confirm(call, bot_mock)
    mock_confirm.assert_awaited_once_with(bot_mock, 42)
    call.message.edit_text.assert_awaited_once()
    assert "tasdiqlandi" in call.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_callback_reject_asks_confirmation_then_rejects():
    call = _fake_callback("adm_reject:42")
    await bot_handlers.cb_admin_reject(call)
    call.message.edit_reply_markup.assert_awaited_once()

    call2 = _fake_callback("adm_rejyes:42")
    bot_mock = AsyncMock()
    with patch.object(bot_handlers, "reject_order", new=AsyncMock(return_value={"ok": True})) as mock_reject:
        await bot_handlers.cb_admin_reject_confirm(call2, bot_mock)
    mock_reject.assert_awaited_once()
    assert mock_reject.await_args.args[1] == 42
    assert "rad etildi" in call2.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_callback_rejects_non_admin():
    call = _fake_callback("adm_confirm:42", admin=False)
    with patch.object(bot_handlers, "confirm_order", new=AsyncMock()) as mock_confirm:
        await bot_handlers.cb_admin_confirm(call, AsyncMock())
    mock_confirm.assert_not_awaited()
    call.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_new_order_message_has_inline_buttons():
    transport = ASGITransport(app=app)
    payload = {
        "telegram_user_id": 111,
        "origin": "TAS",
        "destination": "JED",
        "depart_date": "2026-09-01",
        "flight_data": {"price": 380},
        "passport": {"first_name": "Ali", "last_name": "Valiyev"},
    }
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(db, "create_order", return_value={"id": 55, "origin": "TAS", "destination": "JED", "price": 380}), \
             patch.object(db, "save_passport", return_value=payload["passport"]), \
             patch("main.bot.send_message", new_callable=AsyncMock) as mock_send:
            res = await ac.post("/api/orders", json=payload)
    assert res.status_code == 200
    kb = mock_send.await_args.kwargs["reply_markup"]
    assert kb.inline_keyboard[0][0].callback_data == "adm_confirm:55"


# ==================== 6. ADMIN PANEL: TOZALASH VA CBU KURSI ====================
@pytest.mark.asyncio
async def test_clear_rejected_orders():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res_unauth = await ac.post("/api/admin/orders/clear-rejected")
        assert res_unauth.status_code == 401

        with patch.object(db, "delete_orders_by_status", return_value=3) as mock_del:
            res = await ac.post("/api/admin/orders/clear-rejected", headers={"X-Admin-Password": "testpass"})
    assert res.status_code == 200
    assert res.json() == {"ok": True, "deleted": 3}
    mock_del.assert_called_once_with("rejected")


@pytest.mark.asyncio
async def test_cbu_rate_endpoint():
    transport = ASGITransport(app=app)
    main._cbu_cache.update({"rate": None, "ts": 0})
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch("main.httpx.AsyncClient") as mock_client:
            instance = mock_client.return_value.__aenter__.return_value
            response = MagicMock()
            response.raise_for_status = MagicMock()
            response.json.return_value = [{"Rate": "12750.55", "Date": "21.08.2026", "Diff": "10.5"}]
            instance.get = AsyncMock(return_value=response)
            res = await ac.get("/api/cbu-rate")
    assert res.status_code == 200
    data = res.json()
    assert data["rate"] == 12750.55
    assert data["date"] == "21.08.2026"


@pytest.mark.asyncio
async def test_cbu_rate_fallback_on_error():
    main._cbu_cache.update({"rate": None, "ts": 0})
    with patch("main.httpx.AsyncClient", side_effect=RuntimeError("tarmoq yo'q")):
        data = await main.get_cbu_usd_rate()
    assert data["rate"] == main.CBU_FALLBACK_RATE
    assert data["source"] == "zaxira"


def test_delete_orders_by_status_query():
    fake_table = MagicMock()
    select_chain = fake_table.select.return_value.eq.return_value
    select_chain.execute.return_value = MagicMock(data=[{"id": 1}, {"id": 2}])
    with patch.object(db, "supabase") as fake_sb:
        fake_sb.table.return_value = fake_table
        deleted = db.delete_orders_by_status("rejected")
    assert deleted == 2


# ==================== 7. /admin -> /admin/ REDIRECT ====================
@pytest.mark.asyncio
async def test_admin_redirect():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/admin")
    assert res.status_code in (302, 307)
    assert res.headers["location"] == "/admin/"

    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as ac:
        res2 = await ac.get("/admin")
    assert res2.status_code == 200
    assert "Boshqaruv Paneli" in res2.text


# ==================== 4 & 5. MINI APP UI (statik fayllar) ====================
@pytest.mark.asyncio
async def test_miniapp_contains_new_ui_blocks():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        html = (await ac.get("/")).text
        js = (await ac.get("/app.js")).text
        css = (await ac.get("/style.css")).text
    # 2. Taqvim
    assert 'id="price-calendar"' in html
    assert "loadPriceCalendar" in js
    assert ".pc-strip" in css
    # 4. Boarding pass natijalar
    assert "flightBoardingPassHTML" in js
    assert ".bp-book-btn" in css
    # 5. Nusxalash tugmasi
    assert 'id="btn-copy-card"' in html
    assert "📋 Nusxalash" in html
    assert "copyToClipboard" in js


@pytest.mark.asyncio
async def test_admin_panel_contains_new_controls():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as ac:
        html = (await ac.get("/admin/")).text
        js = (await ac.get("/admin/admin.js")).text
    assert 'id="clear-rejected-btn"' in html
    assert "🗑 Rad etilganlarni tozalash" in html
    assert "📊 Excel (CSV) Yuklab Olish" in html
    assert 'id="cbu-rate-value"' in html
    assert "loadCbuRate" in js
    assert "clear-rejected" in js


# ==================== EXPORT: CSV / XLSX ====================
@pytest.mark.asyncio
async def test_export_csv_and_xlsx():
    orders = [{
        "id": 1, "origin": "TAS", "destination": "JED", "depart_date": "2026-09-01",
        "passengers": 1, "price": 380, "status": "confirmed", "telegram_user_id": 5,
        "username": "ali", "payment_screenshot_url": "", "created_at": "2026-08-21T10:00:00",
        "passports": [{"first_name": "Ali", "last_name": "Valiyev", "passport_number": "FA1234567"}],
    }]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(db, "get_orders_with_passport", return_value=orders):
            csv_res = await ac.get("/api/admin/orders/export?format=csv", headers={"X-Admin-Password": "testpass"})
            xlsx_res = await ac.get("/api/admin/orders/export?format=xlsx", headers={"X-Admin-Password": "testpass"})

    assert csv_res.status_code == 200
    assert ".csv" in csv_res.headers["content-disposition"]
    assert "Valiyev" in csv_res.content.decode("utf-8-sig")

    assert xlsx_res.status_code == 200
    assert ".xlsx" in xlsx_res.headers["content-disposition"]
    assert xlsx_res.content[:2] == b"PK"

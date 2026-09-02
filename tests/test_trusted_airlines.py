import json
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Set dummy env vars for testing before importing settings
os.environ["BOT_TOKEN"] = "123456:fake_bot_token_for_testing"
os.environ["ADMIN_CHAT_ID"] = "-100123456789"
os.environ["CHANNEL_ID"] = "-100987654321"
os.environ["SUPABASE_URL"] = "https://fake.supabase.co"
os.environ["SUPABASE_KEY"] = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy"
os.environ["TRAVELPAYOUTS_TOKEN"] = "dummy_travelpayouts_token"
os.environ["WEBHOOK_BASE_URL"] = "https://example.com"
os.environ["ADMIN_PASSWORD"] = "testpass"
os.environ["CRON_SECRET"] = "testcron"

import database as db
import travelpayouts as tp
from main import AIRLINE_OFFICIAL_SITES, _official_airline_site, app

# ==================== 1. TRUSTED_AIRLINES FILTRI ====================

EXPECTED_TRUSTED = {"HY", "C6", "SV", "TK", "FZ", "G9", "XY", "QR", "EK", "KC", "WY", "MS"}


def test_trusted_airlines_constant():
    assert set(tp.TRUSTED_AIRLINES) == EXPECTED_TRUSTED
    assert "SU" not in tp.TRUSTED_AIRLINES  # Aeroflot ishonchli emas


class FakeTpResponse:
    status_code = 200

    def __init__(self, items):
        self._items = items

    def json(self):
        return {"data": self._items}


async def _search_with_fake_http(items):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=FakeTpResponse(items))
    with patch("travelpayouts.httpx.AsyncClient", return_value=client):
        return await tp.search_flights("Tashkent", "Jeddah", "2026-09-15")


@pytest.mark.asyncio
async def test_search_flights_keeps_only_trusted_airlines():
    results = await _search_with_fake_http([
        {"price": 300, "airline": "HY", "flight_number": "HY-501"},
        {"price": 310, "airline": "SV"},
        {"price": 200, "airline": "SU"},           # ishonchsiz -> tashlab ketiladi
        {"price": 250, "airline": "XY"},
        {"price": 400, "airline": "C6", "transfers": 0},
    ])
    airlines = [r["airline"] for r in results]
    assert "HY" in airlines
    assert "SV" in airlines
    assert "XY" in airlines
    assert "SU" not in airlines
    assert "⭐ Centrum Air (To'g'ridan-to'g'ri)" in airlines


@pytest.mark.asyncio
async def test_search_flights_accepts_partner_airline_full_name():
    # Travelpayouts ba'zan kodi o'rniga to'liq nom yuboradi — Centrum Air / Air Arabia
    # nom bilan kelganda ham kodlari (C6/G9) ishonchli ro'yxatda ekani hisobga olinadi.
    results = await _search_with_fake_http([
        {"price": 320, "airline": "centrum air"},
        {"price": 280, "airline": "Some Unknown Charter"},
        {"price": 260, "airline": "SU"},
    ])
    codes = {r.get("airline_code") or r["airline"] for r in results}
    assert "C6" in codes
    assert all(tp.is_trusted_offer(r) for r in results)


@pytest.mark.asyncio
async def test_api_search_filters_untrusted_but_keeps_manual_and_partner():
    manual = [{
        "id": 1,
        "origin": "TAS",
        "destination": "JED",
        "depart_date": "2026-09-15",
        "departure_time": "09:30",
        "price": 450,
        "airline": "Saudiya Biletlar",
        "flight_number": "SAU-001",
        "transfers": 0,
        "seats_available": 10,
    }]
    api_offers = [
        {"origin": "TAS", "destination": "JED", "price": 300, "airline": "HY"},
        {"origin": "TAS", "destination": "JED", "price": 250, "airline": "SU"},
        {"origin": "TAS", "destination": "JED", "price": 400, "airline": "C6", "transfers": 0},
    ]
    transport = ASGITransport(app=app)
    with patch("main.db.list_manual_flights", return_value=manual), \
         patch("main.tp.search_flights", new=AsyncMock(return_value=api_offers)):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/search?origin=TAS&destination=JED&depart_date=2026-09-15")

    assert response.status_code == 200
    results = response.json()["results"]
    airlines = [r["airline"] for r in results]
    sources = [r["source"] for r in results]
    # Qo'lda qo'shilgan chipta saqlanib qoladi
    assert "Saudiya Biletlar" in airlines
    assert "manual" in sources
    # API'dan faqat ishonchli aviakompaniyalar
    assert "HY" in airlines
    assert "⭐ Centrum Air (To'g'ridan-to'g'ri)" in airlines
    assert "SU" not in airlines


# ==================== 2. STRING flight_data PARSE QILISH ====================

async def _create_order(flight_data, price=None):
    transport = ASGITransport(app=app)
    payload = {
        "telegram_user_id": 123456,
        "origin": "TAS",
        "destination": "JED",
        "depart_date": "2026-09-01",
        "flight_data": flight_data,
        "passport": {
            "first_name": "Ali",
            "last_name": "Valiyev",
            "passport_number": "AA1234567",
        },
    }
    if price is not None:
        payload["price"] = price
    with patch.object(db, "create_order", return_value={
        "id": 80, "origin": "TAS", "destination": "JED",
        "depart_date": "2026-09-01", "passengers": 1, "price": 380,
    }) as mock_create, \
         patch.object(db, "save_passport", return_value=payload["passport"]), \
         patch("main.bot.send_message", new_callable=AsyncMock) as mock_send:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post("/api/orders", json=payload)
        return res, mock_send, mock_create


@pytest.mark.asyncio
async def test_create_order_parses_string_flight_data_for_admin_message():
    flight_data = json.dumps({
        "price": 380,
        "airline": "HY",
        "flight_number": "HY-501",
        "departure_at": "2026-09-01T09:30:00",
        "link": "https://www.aviasales.com/search/TAS0101JED1?marker=1",
    })
    res, mock_send, mock_create = await _create_order(flight_data)
    assert res.status_code == 200

    # DBga dict ko'rinishida saqlanadi
    stored = mock_create.call_args.args[0]
    assert isinstance(stored["flight_data"], dict)
    assert stored["flight_data"]["airline"] == "HY"

    text = mock_send.await_args.args[1]
    assert "🛫 Aviakompaniya: HY (HY-501)" in text
    assert "🕐 Jo'nash vaqti: 2026-09-01T09:30:00" in text
    assert "🔗 Chiptani shu havoladan oling: https://www.aviasales.com/search/TAS0101JED1?marker=1" in text


@pytest.mark.asyncio
async def test_create_order_string_flight_data_escapes_html_and_drops_bad_link():
    flight_data = json.dumps({
        "airline": "Turkish Airlines <hack>",
        "flight_number": "TK-199",
        "departure_time": "21:40",
        "link": "javascript:alert(1)",
    })
    res, mock_send, _ = await _create_order(flight_data)
    assert res.status_code == 200
    text = mock_send.await_args.args[1]
    assert "🛫 Aviakompaniya: Turkish Airlines &lt;hack&gt; (TK-199)" in text
    assert "🕐 Jo'nash vaqti: 21:40" in text
    assert "javascript:" not in text
    assert "Chiptani shu havoladan oling" not in text


@pytest.mark.asyncio
async def test_create_order_invalid_string_flight_data_still_creates_order():
    res, mock_send, _ = await _create_order("not-json{")
    assert res.status_code == 200
    assert res.json()["order_id"] == 80


# ==================== 3. RASMIY SAYT QATORI ====================

def test_official_airline_site_lookup_by_code_and_name():
    assert _official_airline_site({"airline": "HY"}) == ("UZBEKISTAN AIRWAYS", "https://www.uzairways.com")
    assert _official_airline_site({"airline": "uzbekistan airways"}) == ("UZBEKISTAN AIRWAYS", "https://www.uzairways.com")
    assert _official_airline_site({"airline_code": "SV", "airline": "⭐ Saudi"}) == ("SAUDIA", "https://www.saudia.com")
    assert _official_airline_site({"airline": "Centrum Air"}) == ("CENTRUM AIR", "https://centrum-air.com")
    assert _official_airline_site({"airline": "Saudiya Biletlar"}) is None
    assert _official_airline_site({"airline": ""}) is None


@pytest.mark.parametrize("code,official_name,url", [
    ("HY", "UZBEKISTAN AIRWAYS", "https://www.uzairways.com"),
    ("C6", "CENTRUM AIR", "https://centrum-air.com"),
    ("SV", "SAUDIA", "https://www.saudia.com"),
    ("TK", "TURKISH AIRLINES", "https://www.turkishairlines.com"),
    ("FZ", "FLYDUBAI", "https://www.flydubai.com"),
    ("G9", "AIR ARABIA", "https://www.airarabia.com"),
    ("XY", "FLYNAS", "https://flynas.com"),
    ("QR", "QATAR AIRWAYS", "https://www.qatarairways.com"),
    ("EK", "EMIRATES", "https://www.emirates.com"),
])
@pytest.mark.asyncio
async def test_admin_message_contains_official_site_by_airline_code(code, official_name, url):
    res, mock_send, _ = await _create_order({"airline": code, "flight_number": f"{code}-001"})
    assert res.status_code == 200
    text = mock_send.await_args.args[1]
    assert f"✅ Xavfsiz xarid (rasmiy sayt): {official_name} — {url}" in text


@pytest.mark.asyncio
async def test_admin_message_contains_official_site_by_full_name():
    res, mock_send, _ = await _create_order({"airline": "Uzbekistan Airways"})
    assert res.status_code == 200
    text = mock_send.await_args.args[1]
    assert "✅ Xavfsiz xarid (rasmiy sayt): UZBEKISTAN AIRWAYS — https://www.uzairways.com" in text


@pytest.mark.asyncio
async def test_admin_message_no_official_site_for_unknown_airline():
    res, mock_send, _ = await _create_order({"airline": "Saudiya Biletlar", "link": "https://example.com/ticket"})
    assert res.status_code == 200
    text = mock_send.await_args.args[1]
    assert "Xavfsiz xarid" not in text
    assert "🔗 Chiptani shu havoladan oling: https://example.com/ticket" in text


def test_official_sites_map_matches_trusted_spec():
    # Rasmiy sayti bor aviakompaniyalar TRUSTED_AIRLINES ichida
    assert set(AIRLINE_OFFICIAL_SITES).issubset(tp.TRUSTED_AIRLINES)


# ==================== 4. ADMIN PANELDA CHIPTA XARID TUGMASI ====================

@pytest.mark.asyncio
async def test_admin_js_order_card_has_flight_info_and_buy_button():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        js = (await client.get("/admin/admin.js")).text
    # flight_data string (JSON) ham parse qilinadi
    assert "JSON.parse(flightData)" in js
    # Aviakompaniya/reys/vaqt kartada chiqadi
    assert "flightData.airline" in js
    assert "flightData.flight_number" in js
    assert "flightData.departure_at" in js
    assert "flightData.departure_time" in js
    # Link bo'lsa — "🔗 Chiptani xarid qilish" tugmasi (yangi oynada ochiladi)
    assert "🔗 Chiptani xarid qilish" in js
    assert 'target="_blank"' in js

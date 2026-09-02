"""Admin buyurtma xabaridagi "Xavfsiz xarid" havolasi — aynan o'sha reysga olib borishi kerak.

Tekshiriladigan narsalar:
  1) main.py `_google_flights_url()` — Google Flights so'rovi (marshrut + sana + aviakompaniya)
  2) api_create_order() admin xabari — "✅ Xavfsiz xarid" va "🏢 Rasmiy sayt" qatorlari
  3) admin_static/admin.js — link bo'lmaganda "🛡 O'sha reysni xavfsiz ochish" tugmasi
"""

import json
import os
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

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

import html
import database as db
from main import AIRLINE_OFFICIAL_SITES, GOOGLE_FLIGHTS_BASE, _google_flights_url, app

ORDER_ROW = {
    "id": 80,
    "origin": "TAS",
    "destination": "JED",
    "depart_date": "2026-09-01",
    "passengers": 1,
    "price": 380,
}


async def _create_order(flight_data, order_row=None):
    """Buyurtma yaratadi va admin guruhiga yuborilgan xabar matnini qaytaradi."""
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
    with patch.object(db, "create_order", return_value=dict(order_row or ORDER_ROW)), \
         patch.object(db, "save_passport", return_value=payload["passport"]), \
         patch("main.bot.send_message", new_callable=AsyncMock) as mock_send:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post("/api/orders", json=payload)
    assert res.status_code == 200
    return mock_send.await_args.args[1]


# ==================== 1. GOOGLE FLIGHTS URL YASALISHI ====================

def test_google_flights_url_exact_for_route_date_and_airline():
    url = _google_flights_url(ORDER_ROW, {"airline": "HY"})
    assert url == (
        "https://www.google.com/travel/flights?q="
        "flights%20from%20TAS%20to%20JED%20on%202026-09-01%20on%20HY"
    )


def test_google_flights_url_without_airline_suffix():
    url = _google_flights_url(ORDER_ROW, {})
    assert url == GOOGLE_FLIGHTS_BASE + "flights%20from%20TAS%20to%20JED%20on%202026-09-01"
    assert "2026-09-01%20on%20" not in url  # bo'sh aviakompaniya qo'shilmaydi


def test_google_flights_url_ignores_blank_airline():
    assert _google_flights_url(ORDER_ROW, {"airline": "   "}) == _google_flights_url(ORDER_ROW, {})


def test_google_flights_url_takes_date_part_from_departure_at():
    url = _google_flights_url(ORDER_ROW, {"departure_at": "2026-09-01T09:30:00", "airline": "SV"})
    assert "%20on%202026-09-01%20on%20SV" in url
    assert "09%3A30" not in url  # vaqt qismi so'rovga tushmaydi


def test_google_flights_url_falls_back_to_order_date_for_time_only():
    # flight_data'da faqat vaqt ("09:30") bo'lsa — buyurtma sanasi ishlatiladi
    url = _google_flights_url(ORDER_ROW, {"departure_time": "09:30", "airline": "TK"})
    assert "flights%20from%20TAS%20to%20JED%20on%202026-09-01%20on%20TK" in url


def test_google_flights_url_percent_encodes_spaces():
    url = _google_flights_url(ORDER_ROW, {"airline": "Uzbekistan Airways"})
    assert " " not in url
    assert "%20" in url
    assert "Uzbekistan%20Airways" in url


def test_google_flights_url_encodes_html_special_chars():
    url = _google_flights_url(ORDER_ROW, {"airline": '"><script>alert(1)</script>'})
    assert "<" not in url and ">" not in url and '"' not in url.split("?q=", 1)[1]
    assert "%3Cscript%3E" in url


def test_google_flights_url_roundtrips_through_parse_qs():
    url = _google_flights_url(ORDER_ROW, {"airline": "Centrum Air", "departure_at": "2026-09-15T07:05:00"})
    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "https://www.google.com/travel/flights"
    assert parse_qs(parsed.query)["q"] == ["flights from TAS to JED on 2026-09-15 on Centrum Air"]


# ==================== 2. ADMIN XABARIDAGI QATORLAR ====================

@pytest.mark.asyncio
async def test_admin_message_safe_purchase_line_format():
    text = await _create_order({"airline": "HY", "flight_number": "HY-501"})
    expected_href = html.escape(
        "https://www.google.com/travel/flights?q="
        "flights%20from%20TAS%20to%20JED%20on%202026-09-01%20on%20HY",
        quote=True,
    )
    assert (
        f'✅ <b>Xavfsiz xarid:</b> <a href="{expected_href}">O\'sha reysni ochish ➔</a>' in text
    )


@pytest.mark.asyncio
async def test_admin_message_safe_purchase_before_official_site():
    text = await _create_order({"airline": "HY", "flight_number": "HY-501"})
    assert "✅ <b>Xavfsiz xarid:</b>" in text
    assert "🏢 <b>Rasmiy sayt:</b> UZBEKISTAN AIRWAYS — https://www.uzairways.com" in text
    assert text.index("Xavfsiz xarid") < text.index("Rasmiy sayt")


@pytest.mark.asyncio
async def test_admin_message_href_is_html_escaped():
    text = await _create_order({"airline": "Air & Sky <b>"})
    # URL to'liq encode qilingan: href ichida ochiq & yoki < belgisi qolmaydi
    href = text.split('<a href="', 1)[1].split('">', 1)[0]
    assert href.startswith("https://www.google.com/travel/flights?q=")
    assert href == html.escape(href)
    assert "%26" in href and "%3Cb%3E" in href
    assert "<b>" not in href


@pytest.mark.asyncio
async def test_admin_message_rejects_script_injection_via_airline():
    text = await _create_order({"airline": '"><script>alert(1)</script>'})
    assert "<script>" not in text
    assert "%3Cscript%3E" in text


@pytest.mark.asyncio
async def test_admin_message_safe_purchase_without_flight_link():
    text = await _create_order({"airline": "SV", "flight_number": "SV-201"})
    assert "Chiptani shu havoladan oling" not in text
    assert "google.com/travel/flights" in text
    assert "🏢 <b>Rasmiy sayt:</b> SAUDIA — https://www.saudia.com" in text


@pytest.mark.asyncio
async def test_admin_message_safe_purchase_alongside_aviasales_link():
    link = "https://www.aviasales.com/search/TAS0109JED1?marker=1"
    text = await _create_order({"airline": "C6", "link": link})
    assert f"🔗 Chiptani shu havoladan oling: {link}" in text
    assert "✅ <b>Xavfsiz xarid:</b>" in text
    assert "%20on%20C6" in text


@pytest.mark.asyncio
async def test_admin_message_safe_purchase_with_invalid_json_flight_data():
    # flight_data JSON bo'lmasa ham marshrut/sana bo'yicha havola qo'shiladi
    text = await _create_order("not-json{")
    assert "flights%20from%20TAS%20to%20JED%20on%202026-09-01" in text
    assert "Rasmiy sayt" not in text


@pytest.mark.asyncio
async def test_admin_message_official_site_line_for_all_mapped_airlines():
    for code, (official_name, official_url) in AIRLINE_OFFICIAL_SITES.items():
        text = await _create_order({"airline": code, "flight_number": f"{code}-001"})
        assert f"🏢 <b>Rasmiy sayt:</b> {official_name} — {official_url}" in text, code


# ==================== 3. ADMIN PANEL TUGMASI (admin.js) ====================

@pytest.fixture
async def admin_js():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/admin/admin.js")
    assert res.status_code == 200
    return res.text


@pytest.mark.asyncio
async def test_admin_js_served_and_has_safe_purchase_button(admin_js):
    assert "🛡 O'sha reysni xavfsiz ochish ➔" in admin_js
    assert "https://www.google.com/travel/flights?q=" in admin_js
    assert "encodeURIComponent(gfQuery)" in admin_js


@pytest.mark.asyncio
async def test_admin_js_skips_manual_agency_sources(admin_js):
    assert 'NON_PUBLIC_SOURCES = ["manual", "direct_agency", "centrum_air"]' in admin_js
    assert "!flightLink && !NON_PUBLIC_SOURCES.includes(flightSource)" in admin_js
    assert "flightData.source" in admin_js


@pytest.mark.asyncio
async def test_admin_js_keeps_aviasales_button_and_opens_new_tab(admin_js):
    assert "🔗 Chiptani xarid qilish (Aviasales)" in admin_js
    assert 'target="_blank"' in admin_js
    assert 'rel="noopener noreferrer"' in admin_js


@pytest.mark.asyncio
async def test_admin_js_renders_button_in_order_card(admin_js):
    card_body = admin_js.split("card.innerHTML = `", 1)[1].split("list.appendChild(card)", 1)[0]
    assert "${safeBuyLinkHtml}" in card_body
    assert "${flightLinkHtml}" in card_body

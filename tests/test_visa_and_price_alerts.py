"""Viza arizalari va narx tushishi obunalari uchun integratsion testlar."""
import hashlib
import hmac
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import AsyncMock, patch

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

import database as db  # noqa: E402
import main  # noqa: E402
from main import app  # noqa: E402


def telegram_headers(user_id: int) -> dict[str, str]:
    values = {
        "auth_date": str(int(time.time())),
        "query_id": "AAE-test-query",
        "user": json.dumps({"id": user_id, "first_name": "Test"}, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return {"X-Telegram-Init-Data": urlencode(values)}


@pytest.fixture
def visa_payload():
    return {
        "telegram_user_id": 123456,
        "username": "ali",
        "visa_type": "umrah_nusuk",
        "first_name": "Ali",
        "last_name": "Valiyev",
        "phone": "+998901234567",
        "passport_number": "FA1234567",
        "birth_date": "1990-05-10",
        "travel_date": (date.today() + timedelta(days=20)).isoformat(),
        "notes": "Oilaviy safar",
    }


@pytest.mark.asyncio
async def test_create_visa_application_and_notify_admin(visa_payload):
    saved = {"id": 17, **visa_payload, "first_name": "ALI", "last_name": "VALIYEV", "status": "new"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(db, "create_visa_application", return_value=saved) as create_mock, \
             patch("main.bot.send_message", new_callable=AsyncMock) as send_mock:
            response = await ac.post(
                "/api/visa-applications", json=visa_payload, headers=telegram_headers(123456)
            )

    assert response.status_code == 200
    assert response.json()["application_id"] == 17
    stored = create_mock.call_args.args[0]
    assert stored["visa_type"] == "umrah_nusuk"
    assert stored["first_name"] == "ALI"
    assert stored["status"] == "new"
    send_mock.assert_awaited_once()
    assert "Yangi viza arizasi #17" in send_mock.await_args.args[1]


@pytest.mark.asyncio
async def test_visa_application_validation_rejects_bad_passport(visa_payload):
    visa_payload["passport_number"] = "FA 12<script>"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(db, "create_visa_application") as create_mock:
            response = await ac.post(
                "/api/visa-applications", json=visa_payload, headers=telegram_headers(123456)
            )
    assert response.status_code == 400
    create_mock.assert_not_called()


@pytest.mark.asyncio
async def test_user_can_list_own_visa_applications():
    applications = [{"id": 2, "telegram_user_id": 123456, "status": "processing"}]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(db, "get_visa_applications_by_user", return_value=applications):
            response = await ac.get(
                "/api/visa-applications?telegram_user_id=123456",
                headers=telegram_headers(123456),
            )
    assert response.status_code == 200
    assert response.json()["applications"] == applications


@pytest.mark.asyncio
async def test_private_endpoints_require_signed_telegram_user():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        missing = await ac.get("/api/visa-applications?telegram_user_id=123456")
        mismatch = await ac.get(
            "/api/visa-applications?telegram_user_id=123456",
            headers=telegram_headers(999999),
        )
    assert missing.status_code == 401
    assert mismatch.status_code == 403


@pytest.mark.asyncio
async def test_admin_updates_visa_status_and_customer_is_notified():
    application = {"id": 9, "telegram_user_id": 123456, "status": "new"}
    updated = {**application, "status": "approved", "admin_note": "Hujjat tayyor"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(db, "get_visa_application", return_value=application), \
             patch.object(db, "update_visa_application", return_value=updated) as update_mock, \
             patch("main.bot.send_message", new_callable=AsyncMock) as send_mock:
            response = await ac.patch(
                "/api/admin/visa-applications/9",
                headers={"X-Admin-Password": "testpass"},
                json={"status": "approved", "admin_note": "Hujjat tayyor"},
            )
    assert response.status_code == 200
    assert response.json()["application"]["status"] == "approved"
    update_mock.assert_called_once_with(9, {"status": "approved", "admin_note": "Hujjat tayyor"})
    send_mock.assert_awaited_once()
    assert send_mock.await_args.args[0] == 123456


@pytest.mark.asyncio
async def test_create_and_cancel_price_alert():
    start = date.today() + timedelta(days=5)
    payload = {
        "telegram_user_id": 123456,
        "username": "ali",
        "origin": "Toshkent",
        "destination": "Jidda",
        "date_from": start.isoformat(),
        "date_to": (start + timedelta(days=20)).isoformat(),
        "target_price": 299,
    }
    saved = {"id": 31, **payload, "origin": "TAS", "destination": "JED", "is_active": True}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(db, "create_price_alert", return_value=saved) as create_mock:
            created = await ac.post(
                "/api/price-alerts", json=payload, headers=telegram_headers(123456)
            )
        with patch.object(db, "get_price_alert", return_value=saved), \
             patch.object(db, "update_price_alert", return_value={**saved, "is_active": False}) as update_mock:
            cancelled = await ac.delete(
                "/api/price-alerts/31?telegram_user_id=123456",
                headers=telegram_headers(123456),
            )

    assert created.status_code == 200
    assert created.json()["alert_id"] == 31
    stored = create_mock.call_args.args[0]
    assert stored["origin"] == "TAS" and stored["destination"] == "JED"
    assert stored["target_price"] == 299.0
    assert cancelled.status_code == 200
    update_mock.assert_called_once_with(31, {"is_active": False})


@pytest.mark.asyncio
async def test_price_alert_rejects_too_wide_date_range():
    start = date.today() + timedelta(days=1)
    payload = {
        "telegram_user_id": 1,
        "origin": "TAS",
        "destination": "JED",
        "date_from": start.isoformat(),
        "date_to": (start + timedelta(days=60)).isoformat(),
        "target_price": 300,
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/price-alerts", json=payload, headers=telegram_headers(1)
        )
    assert response.status_code == 400
    assert "60 kun" in response.json()["detail"]


@pytest.mark.asyncio
async def test_price_alert_cannot_be_cancelled_by_another_user():
    alert = {"id": 5, "telegram_user_id": 111, "is_active": True}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(db, "get_price_alert", return_value=alert), \
             patch.object(db, "update_price_alert") as update_mock:
            response = await ac.delete(
                "/api/price-alerts/5?telegram_user_id=222", headers=telegram_headers(222)
            )
    assert response.status_code == 404
    update_mock.assert_not_called()


@pytest.mark.asyncio
async def test_price_alert_cron_notifies_and_deactivates_matched_alert():
    start = date.today() + timedelta(days=4)
    alert = {
        "id": 44,
        "telegram_user_id": 123456,
        "origin": "TAS",
        "destination": "JED",
        "date_from": start.isoformat(),
        "date_to": (start + timedelta(days=5)).isoformat(),
        "target_price": 300,
        "is_active": True,
    }
    calendar = [{
        "date": start.isoformat(),
        "price": 280,
        "airline": "Uzbekistan Airways",
        "source": "api",
    }]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(db, "list_price_alerts", return_value=[alert]), \
             patch("travelpayouts.get_calendar_prices", new=AsyncMock(return_value=calendar)), \
             patch.object(db, "list_manual_flights", return_value=[]), \
             patch.object(db, "update_price_alert", return_value={}) as update_mock, \
             patch("main.bot.send_message", new_callable=AsyncMock) as send_mock:
            response = await ac.post("/api/cron/price-alerts?secret=testcron")

    assert response.status_code == 200
    assert response.json()["checked"] == 1
    assert response.json()["matched"] == 1
    assert response.json()["notified"] == 1
    send_mock.assert_awaited_once()
    final_update = update_mock.call_args.args[1]
    assert final_update["last_price"] == 280.0
    assert final_update["is_active"] is False
    assert final_update["last_notified_at"]


@pytest.mark.asyncio
async def test_price_alert_cron_never_notifies_for_estimated_price():
    start = date.today() + timedelta(days=4)
    alert = {
        "id": 45,
        "telegram_user_id": 123456,
        "origin": "TAS",
        "destination": "JED",
        "date_from": start.isoformat(),
        "date_to": (start + timedelta(days=2)).isoformat(),
        "target_price": 500,
        "is_active": True,
    }
    estimate = [{"date": start.isoformat(), "price": 250, "source": "estimate"}]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        with patch.object(db, "list_price_alerts", return_value=[alert]), \
             patch("travelpayouts.get_calendar_prices", new=AsyncMock(return_value=estimate)), \
             patch.object(db, "list_manual_flights", return_value=[]), \
             patch.object(db, "update_price_alert", return_value={}), \
             patch("main.bot.send_message", new_callable=AsyncMock) as send_mock:
            response = await ac.post("/api/cron/price-alerts?secret=testcron")

    assert response.status_code == 200
    assert response.json()["notified"] == 0
    send_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_miniapp_and_admin_controls_are_shipped():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        mini_html = (await ac.get("/")).text
        mini_js = (await ac.get("/app.js")).text
        admin_html = (await ac.get("/admin/")).text
        admin_js = (await ac.get("/admin/admin.js")).text

    # Mini Appda uzun viza forma/tarix va katta obuna formasi bo'lmasligi kerak.
    assert 'id="btn-price-alert"' not in mini_html
    assert 'id="btn-submit-visa"' not in mini_html
    assert 'id="visa-applications-list"' not in mini_html
    assert 'class="price-alert-card"' not in mini_html
    assert "loadPriceAlerts" not in mini_js
    assert "loadVisaApplications" not in mini_js
    assert mini_html.count("visa-choose-btn") == 2
    assert 'data-tab="visa-applications"' in admin_html
    assert 'data-tab="price-alerts"' in admin_html
    assert "loadVisaApplicationsAdmin" in admin_js
    assert "loadPriceAlertsAdmin" in admin_js


def test_supabase_migration_contains_secure_new_tables():
    sql = Path("migrations/20260822_visa_and_price_alerts.sql").read_text(encoding="utf-8").lower()
    assert "create table if not exists public.visa_applications" in sql
    assert "create table if not exists public.price_alerts" in sql
    assert "enable row level security" in sql
    assert "price_alerts_unique_active_idx" in sql

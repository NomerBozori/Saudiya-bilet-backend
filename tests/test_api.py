from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import database as db
from main import app


@pytest.mark.asyncio
async def test_root_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/")
    assert res.status_code == 200
    assert "Saudiya Biletlar" in res.text
    assert "tg-cal-dropdown" in res.text
    assert "card-3d" in res.text
    assert "bp-modal" in res.text


@pytest.mark.asyncio
async def test_health_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_admin_login():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Wrong pass
        res1 = await ac.post("/api/admin/login", json={"password": "wrongpassword"})
        assert res1.status_code == 401
        
        # Correct pass
        res2 = await ac.post("/api/admin/login", json={"password": "testpass"})
        assert res2.status_code == 200
        assert res2.json()["ok"] is True


@pytest.mark.asyncio
async def test_admin_orders_protected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Without header
        res1 = await ac.get("/api/admin/orders")
        assert res1.status_code == 401
        
        # With valid header
        with patch.object(db, "get_orders_with_passport", return_value=[]):
            res2 = await ac.get("/api/admin/orders", headers={"X-Admin-Password": "testpass"})
            assert res2.status_code == 200
            assert res2.json() == {"orders": []}


@pytest.mark.asyncio
async def test_daily_post_cron():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Invalid secret
        res1 = await ac.post("/api/cron/daily-post?secret=wrong")
        assert res1.status_code == 403

        # Valid secret with mocked tp — yaqin (10 kundan keyingi) sana
        soon = (date.today() + timedelta(days=10)).isoformat()
        with patch("travelpayouts.get_daily_cheapest", new=AsyncMock(return_value=[
                 {"origin": "TAS", "destination": "JED", "value": 350, "depart_date": soon}
             ])), \
             patch("main.get_cbu_usd_rate", new=AsyncMock(return_value={"rate": 12500.0})), \
             patch("main.bot.send_message", new_callable=AsyncMock) as mock_send:
            res2 = await ac.post("/api/cron/daily-post?secret=testcron")
            assert res2.status_code == 200
            body = res2.json()
            # Qolgan shaharlar zaxira takliflar bilan to'ldiriladi -> 11 ta aeroport
            assert body["posted"] == 11
            assert soon in body["dates"]
            mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_payment_info_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/payment-info")
    assert res.status_code == 200
    data = res.json()
    assert "card_number" in data
    assert "card_owner" in data


@pytest.mark.asyncio
async def test_create_order_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "telegram_user_id": 123456,
            "origin": "TAS",
            "destination": "JED",
            "depart_date": "2026-09-01",
            "flight_data": {"price": 380, "airline": "Centrum Air"},
            "passport": {
                "first_name": "Ali",
                "last_name": "Valiyev",
                "passport_number": "AA1234567"
            }
        }
        with patch.object(db, "create_order", return_value={"id": 77, "origin": "TAS", "destination": "JED", "depart_date": "2026-09-01", "price": 380}), \
             patch.object(db, "save_passport", return_value=payload["passport"]), \
             patch("main.bot.send_message", new_callable=AsyncMock):
            res = await ac.post("/api/orders", json=payload)
            assert res.status_code == 200
            assert res.json()["order_id"] == 77


@pytest.mark.asyncio
async def test_create_order_admin_message_includes_flight_details():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "telegram_user_id": 123456,
            "origin": "TAS",
            "destination": "JED",
            "depart_date": "2026-09-01",
            "flight_data": {
                "price": 380,
                "airline": "Centrum Air <hack>",
                "flight_number": "HY-123",
                "departure_at": "2026-09-01T09:30:00",
                "link": "https://tp.media/click?marker=1&trs=1",
            },
            "passport": {
                "first_name": "Ali",
                "last_name": "Valiyev",
                "passport_number": "AA1234567",
            },
        }
        with patch.object(db, "create_order", return_value={"id": 78, "origin": "TAS", "destination": "JED", "depart_date": "2026-09-01", "price": 380}), \
             patch.object(db, "save_passport", return_value=payload["passport"]), \
             patch("main.bot.send_message", new_callable=AsyncMock) as mock_send:
            res = await ac.post("/api/orders", json=payload)
            assert res.status_code == 200

        text = mock_send.await_args.args[1]
        assert "🛫 Aviakompaniya: Centrum Air &lt;hack&gt; (HY-123)" in text
        assert "🕐 Jo'nash vaqti: 2026-09-01T09:30:00" in text
        assert "🔗 Chiptani shu havoladan oling: https://tp.media/click?marker=1&amp;trs=1" in text


@pytest.mark.asyncio
async def test_create_order_admin_message_ignores_unsafe_link():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "telegram_user_id": 123456,
            "origin": "TAS",
            "destination": "JED",
            "depart_date": "2026-09-01",
            "flight_data": {
                "price": 380,
                "airline": "Centrum Air",
                "link": "javascript:alert(1)",
            },
            "passport": {
                "first_name": "Ali",
                "last_name": "Valiyev",
                "passport_number": "AA1234567",
            },
        }
        with patch.object(db, "create_order", return_value={"id": 79, "origin": "TAS", "destination": "JED", "depart_date": "2026-09-01", "price": 380}), \
             patch.object(db, "save_passport", return_value=payload["passport"]), \
             patch("main.bot.send_message", new_callable=AsyncMock) as mock_send:
            res = await ac.post("/api/orders", json=payload)
            assert res.status_code == 200

        text = mock_send.await_args.args[1]
        assert "javascript:" not in text
        assert "Chiptani shu havoladan oling" not in text

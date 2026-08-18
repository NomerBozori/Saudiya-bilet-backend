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

        # Valid secret with mocked tp
        with patch("travelpayouts.get_daily_cheapest", return_value=[{"origin": "TAS", "destination": "JED", "value": 350, "depart_date": "2026-09-01"}]), \
             patch("main.bot.send_message", new_callable=AsyncMock) as mock_send:
            res2 = await ac.post("/api/cron/daily-post?secret=testcron")
            assert res2.status_code == 200
            assert res2.json()["posted"] == 1
            mock_send.assert_awaited_once()


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

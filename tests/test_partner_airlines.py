from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import travelpayouts as tp
from main import app


def test_partner_offer_labels_accept_iata_codes_and_keep_real_transfer_data():
    centrum = tp.enrich_partner_offer({"airline": "C6", "transfers": 0})
    arabia = tp.enrich_partner_offer({"airline": "G9", "transfers": 1})

    assert centrum["airline"] == "⭐ Centrum Air (To'g'ridan-to'g'ri)"
    assert centrum["airline_code"] == "C6"
    assert centrum["transfers"] == 0
    assert arabia["airline"] == "💸 Air Arabia (Arzon Tranzit)"
    assert arabia["airline_code"] == "G9"
    assert arabia["transfers"] == 1


@pytest.mark.asyncio
async def test_search_labels_centrum_and_air_arabia_results():
    offers = [
        {"origin": "TAS", "destination": "JED", "price": 400, "airline": "C6", "transfers": 0},
        {"origin": "TAS", "destination": "JED", "price": 300, "airline": "G9", "transfers": 1},
    ]
    transport = ASGITransport(app=app)
    with patch("main.db.list_manual_flights", return_value=[]), \
         patch("main.tp.search_flights", new=AsyncMock(return_value=offers)):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/search?origin=TAS&destination=JED&depart_date=2026-09-15")

    assert response.status_code == 200
    labels = [offer["airline"] for offer in response.json()["results"]]
    assert "⭐ Centrum Air (To'g'ridan-to'g'ri)" in labels
    assert "💸 Air Arabia (Arzon Tranzit)" in labels


@pytest.mark.asyncio
async def test_daily_post_includes_partner_label_and_prioritizes_centrum_offer():
    soon = (date.today() + timedelta(days=7)).isoformat()
    offers = [
        {"origin": "TAS", "destination": "JED", "value": 280, "depart_date": soon, "airline": "Other Air"},
        {"origin": "TAS", "destination": "JED", "value": 400, "depart_date": soon, "airline": "C6", "transfers": 0},
    ]
    transport = ASGITransport(app=app)
    with patch("travelpayouts.get_daily_cheapest", new=AsyncMock(return_value=offers)), \
         patch("main.get_cbu_usd_rate", new=AsyncMock(return_value={"rate": 12500})), \
         patch("main.bot.send_message", new_callable=AsyncMock) as send_message:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/cron/daily-post?secret=testcron&limit=1")

    assert response.status_code == 200
    assert "⭐ Centrum Air (To'g'ridan-to'g'ri)" in send_message.await_args.args[1]

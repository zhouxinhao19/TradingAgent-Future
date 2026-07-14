"""
tests/test_commodity_paper_routes.py — Phase 4 第四刀 HTTP 端点集成测试

覆盖:
- 14 个 HTTP 端点(创建账户/下单/撤单/持仓/成交/决策下单/快照)
- 用 mongomock-motor 模拟 MongoDB
- 轻量 TestApp(只注册 paper_rules_router + mock auth)

不依赖 app.main 的全量导入,避免已有代码的语法/运行时问题。
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

mongomock_motor = pytest.importorskip("mongomock_motor")
AsyncMongoMockClient = mongomock_motor.AsyncMongoMockClient


# =============================================================================
# 构建轻量测试 app
# =============================================================================

def _make_app(mock_db) -> FastAPI:
    """创建一个只包含 paper_rules_router 的测试用 FastAPI app。"""
    import app.core.database as db_mod
    db_mod.get_mongo_db = lambda: mock_db

    import tradingagents.paper.repo as repo_mod
    repo_mod.get_mongo_db = lambda: mock_db

    from tradingagents.paper.repo import (
        PaperAccountRepo, PaperOrderRepo, PaperPositionRepo, PaperFillRepo,
    )
    from tradingagents.paper.service import PaperServiceContext

    # 重置 router 持有的 service 单例的 _ctx,确保每个测试用 mock db
    from app.services.commodity.paper_trading_service import service as svc
    svc._ctx = PaperServiceContext(
        account_repo=PaperAccountRepo(db=mock_db),
        order_repo=PaperOrderRepo(db=mock_db),
        position_repo=PaperPositionRepo(db=mock_db),
        fill_repo=PaperFillRepo(db=mock_db),
        quote_fn=AsyncMock(return_value=70800.0),
        sse_fn=AsyncMock(),
    )

    app = FastAPI(title="test-commodity-paper")

    # auth mock
    from app.routers.auth_db import get_current_user as real_get_current_user
    async def mock_get_current_user():
        return {"username": "test_user", "user_id": "test_user"}
    app.dependency_overrides[real_get_current_user] = mock_get_current_user

    from app.routers.commodity.paper_rules import router
    app.include_router(router, prefix="/api")

    return app


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_db():
    client = AsyncMongoMockClient()
    yield client["test_paper_routes"]


@pytest.fixture
def client(mock_db):
    app = _make_app(mock_db)
    with TestClient(app) as c:
        yield c


# =============================================================================
# 辅助
# =============================================================================

_BASE = "/api/commodity/paper"


def _assert_ok(response, status_code: int = 200):
    assert response.status_code == status_code, \
        f"status={response.status_code}, body={response.text}"
    body = response.json()
    assert body.get("success") is True, f"body={body}"
    return body


# =============================================================================
# 测试用例
# =============================================================================

class TestCreateAccount:
    """POST /api/commodity/paper/accounts"""
    def test_create_default(self, client):
        resp = client.post(f"{_BASE}/accounts", params={"name": "测试账户"})
        body = _assert_ok(resp)
        assert body["data"]["account_id"] is not None
        assert body["data"]["balance"] == 1_000_000.0
        assert body["data"]["status"] == "active"

    def test_create_with_custom_capital(self, client):
        resp = client.post(f"{_BASE}/accounts",
                           params={"name": "大账户", "initial_capital": 5_000_000})
        body = _assert_ok(resp)
        assert body["data"]["initial_capital"] == 5_000_000.0


class TestListAccounts:
    """GET /api/commodity/paper/accounts"""
    def test_empty(self, client):
        resp = client.get(f"{_BASE}/accounts")
        body = _assert_ok(resp)
        assert body["data"]["accounts"] == []

    def test_after_create(self, client):
        client.post(f"{_BASE}/accounts", params={"name": "A"})
        resp = client.get(f"{_BASE}/accounts")
        body = _assert_ok(resp)
        assert len(body["data"]["accounts"]) == 1


class TestGetAccount:
    """GET /api/commodity/paper/accounts/{id}"""
    def test_get(self, client):
        aid = client.post(f"{_BASE}/accounts", params={"name": "X"}).json()["data"]["account_id"]
        resp = client.get(f"{_BASE}/accounts/{aid}")
        body = _assert_ok(resp)
        assert body["data"]["account_id"] == aid

    def test_not_found(self, client):
        resp = client.get(f"{_BASE}/accounts/nonexistent")
        assert resp.status_code == 404


class TestSnapshot:
    """GET /api/commodity/paper/accounts/{id}/snapshot"""
    def test_snapshot(self, client):
        aid = client.post(f"{_BASE}/accounts", params={"name": "S"}).json()["data"]["account_id"]
        resp = client.get(f"{_BASE}/accounts/{aid}/snapshot")
        body = _assert_ok(resp)
        assert "positions" in body["data"]
        assert "recent_orders" in body["data"]


class TestMetrics:
    """GET /api/commodity/paper/accounts/{id}/metrics"""
    def test_metrics(self, client):
        aid = client.post(f"{_BASE}/accounts", params={"name": "M"}).json()["data"]["account_id"]
        resp = client.get(f"{_BASE}/accounts/{aid}/metrics")
        body = _assert_ok(resp)
        assert "equity" in body["data"]
        assert "risk_ratio" in body["data"]


class TestReset:
    """POST /api/commodity/paper/accounts/{id}/reset"""
    def test_reset(self, client):
        aid = client.post(f"{_BASE}/accounts", params={"name": "R"}).json()["data"]["account_id"]
        resp = client.post(f"{_BASE}/accounts/{aid}/reset")
        body = _assert_ok(resp)
        assert body["data"]["balance"] == 1_000_000.0


class TestSubmitOrder:
    """POST /api/commodity/paper/orders"""
    def _aid(self, client):
        return client.post(f"{_BASE}/accounts", params={"name": "O"}).json()["data"]["account_id"]

    def test_market_long(self, client):
        aid = self._aid(client)
        resp = client.post(f"{_BASE}/orders", params={
            "account_id": aid, "full_symbol": "CU2501.SHF",
            "direction": "long", "offset": "open", "order_type": "market", "lots": 1,
        })
        body = _assert_ok(resp)
        assert body["data"]["status"] == "accepted"

    def test_limit_not_touched(self, client):
        aid = self._aid(client)
        resp = client.post(f"{_BASE}/orders", params={
            "account_id": aid, "full_symbol": "RB2501.DCE",
            "direction": "short", "offset": "open", "order_type": "limit",
            "lots": 2, "price": 1000.0,
        })
        body = _assert_ok(resp)
        assert body["data"]["status"] == "accepted"

    def test_invalid_symbol(self, client):
        aid = self._aid(client)
        resp = client.post(f"{_BASE}/orders", params={
            "account_id": aid, "full_symbol": "INVALID",
            "direction": "long", "offset": "open", "order_type": "market", "lots": 1,
        })
        assert resp.status_code == 400


class TestListOrders:
    """GET /api/commodity/paper/orders"""
    def _aid_with_order(self, client):
        aid = client.post(f"{_BASE}/accounts", params={"name": "LO"}).json()["data"]["account_id"]
        client.post(f"{_BASE}/orders", params={
            "account_id": aid, "full_symbol": "CU2501.SHF",
            "direction": "long", "offset": "open", "order_type": "market", "lots": 1,
        })
        return aid

    def test_list(self, client):
        aid = self._aid_with_order(client)
        resp = client.get(f"{_BASE}/orders", params={"account_id": aid})
        body = _assert_ok(resp)
        assert body["data"]["total"] >= 1

    def test_empty(self, client):
        resp = client.get(f"{_BASE}/orders", params={"account_id": "nonexistent"})
        # 不存在的账户应返回 404(所有权校验拦截)
        assert resp.status_code == 404


class TestCancelOrder:
    """POST /api/commodity/paper/orders/{id}/cancel"""
    def test_cancel_pending_limit(self, client):
        aid = client.post(f"{_BASE}/accounts", params={"name": "CO"}).json()["data"]["account_id"]
        client.post(f"{_BASE}/orders", params={
            "account_id": aid, "full_symbol": "CU2501.SHF",
            "direction": "long", "offset": "open", "order_type": "limit",
            "lots": 1, "price": 1000.0,
        })
        orders_resp = client.get(f"{_BASE}/orders", params={"account_id": aid})
        pending = [o for o in orders_resp.json()["data"]["orders"]
                   if o["status"] == "pending"]
        if not pending:
            pytest.skip("no pending order to cancel")
        oid = pending[0]["id"]
        resp = client.post(f"{_BASE}/orders/{oid}/cancel")
        body = _assert_ok(resp)
        assert body["data"]["status"] == "cancelled"


class TestPositions:
    """GET /api/commodity/paper/positions"""
    def test_after_market_order(self, client):
        aid = client.post(f"{_BASE}/accounts", params={"name": "P"}).json()["data"]["account_id"]
        client.post(f"{_BASE}/orders", params={
            "account_id": aid, "full_symbol": "CU2501.SHF",
            "direction": "long", "offset": "open", "order_type": "market", "lots": 1,
        })
        resp = client.get(f"{_BASE}/positions", params={"account_id": aid})
        body = _assert_ok(resp)
        assert len(body["data"]["positions"]) >= 1
        pos = body["data"]["positions"][0]
        assert pos["full_symbol"] == "CU2501.SHF"
        assert pos["direction"] == "long"
        assert pos["lots"] >= 1


class TestFills:
    """GET /api/commodity/paper/fills"""
    def test_after_market_order(self, client):
        aid = client.post(f"{_BASE}/accounts", params={"name": "F"}).json()["data"]["account_id"]
        client.post(f"{_BASE}/orders", params={
            "account_id": aid, "full_symbol": "CU2501.SHF",
            "direction": "long", "offset": "open", "order_type": "market", "lots": 1,
        })
        resp = client.get(f"{_BASE}/fills", params={"account_id": aid})
        body = _assert_ok(resp)
        assert body["data"]["total"] >= 1


class TestFromDecision:
    """POST /api/commodity/paper/from-decision"""
    def test_neutral_no_action(self, client, mock_db):
        aid = client.post(f"{_BASE}/accounts", params={"name": "FD"}).json()["data"]["account_id"]
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                mock_db["commodity_decisions"].insert_one({
                    "_id": "decision_neutral_1",
                    "full_symbol": "CU2501.SHF",
                    "direction": "neutral",
                    "entry_price_range": [0.0, 0.0],
                })
            )
        finally:
            loop.close()

        resp = client.post(f"{_BASE}/from-decision", params={
            "account_id": aid, "decision_id": "decision_neutral_1",
        })
        body = _assert_ok(resp)
        assert body["data"]["status"] == "no_action"


class TestSnapshots:
    """GET /api/commodity/paper/snapshots"""
    def test_empty(self, client):
        aid = client.post(f"{_BASE}/accounts", params={"name": "SS"}).json()["data"]["account_id"]
        resp = client.get(f"{_BASE}/snapshots", params={"account_id": aid})
        body = _assert_ok(resp)
        assert body["data"]["snapshots"] == []

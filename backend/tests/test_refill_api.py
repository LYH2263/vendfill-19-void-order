import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import Lane
from app.services.seed import seed_if_empty


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestSession()
    seed_if_empty(db)

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c, db
    app.dependency_overrides.clear()
    db.close()


def lane_snapshot(db):
    return {l.id: (l.stock, l.in_transit) for l in db.scalars(select(Lane)).all()}


def test_seed_latest_order_is_the_non_voided_one(client):
    c, db = client
    # 种子两张单：#1 缩减补量 15，#2 全量补 32 且已作废
    s = c.get("/api/refills/summary?location_id=1").json()
    assert s["order_id"] == 1
    assert s["status"] == "active"
    assert s["has_order"] is True
    assert s["total_fill"] == 15  # 不引用已作废 #2 的 32

    latest = c.get("/api/refills/latest?location_id=1").json()
    assert latest["id"] == 1

    # 满仓页默认依据同一张有效单
    full = c.get("/api/refills/full?location_id=1").json()
    assert full["order_id"] == 1
    assert {l["slot_no"] for l in full["lanes"]} == {"A2", "B2"}


def test_seed_lane_numbers_unchanged(client):
    c, db = client
    rows = c.get("/api/lanes?location_id=1").json()
    by_slot = {r["slot_no"]: r for r in rows}
    assert (by_slot["A1"]["stock"], by_slot["A1"]["in_transit"]) == (5, 0)
    assert (by_slot["C2"]["stock"], by_slot["C2"]["in_transit"]) == (24, 2)
    assert by_slot["B1"]["in_transit"] == 2
    assert by_slot["B2"]["stock"] == 10


def test_void_latest_falls_back_without_touching_stock(client):
    c, db = client
    before = lane_snapshot(db)

    run = c.post("/api/refills/run?location_id=1").json()
    assert run["status"] == "active"
    new_id = run["id"]
    assert run["total_fill"] == 32
    assert c.get("/api/refills/latest?location_id=1").json()["id"] == new_id

    r = c.post(f"/api/refills/{new_id}/void")
    assert r.status_code == 200
    assert r.json()["status"] == "voided"

    # 有效单指针回退到上一张未作废单
    latest = c.get("/api/refills/latest?location_id=1").json()
    assert latest["id"] == 1
    s = c.get("/api/refills/summary?location_id=1").json()
    assert s["order_id"] == 1
    assert s["total_fill"] == 15

    # 库存与在途逐货道不变，未被清零/改写
    assert lane_snapshot(db) == before


def test_verified_order_cannot_be_voided(client):
    c, db = client
    before = lane_snapshot(db)

    order = c.post("/api/refills/run?location_id=1").json()
    oid = order["id"]
    assert c.post(f"/api/refills/{oid}/verify").json()["status"] == "verified"

    r = c.post(f"/api/refills/{oid}/void")
    assert r.status_code == 409

    db.expire_all()
    # 单据仍是已核销，有效单指针、汇总、库存全部不动
    latest = c.get("/api/refills/latest?location_id=1").json()
    assert latest["id"] == oid
    assert latest["status"] == "verified"
    s = c.get("/api/refills/summary?location_id=1").json()
    assert s["order_id"] == oid
    assert s["total_fill"] == 32
    assert lane_snapshot(db) == before


def test_voided_order_cannot_be_verified(client):
    c, db = client
    oid = c.post("/api/refills/run?location_id=1").json()["id"]
    assert c.post(f"/api/refills/{oid}/void").status_code == 200
    r = c.post(f"/api/refills/{oid}/verify")
    assert r.status_code == 409
    assert c.get("/api/refills/latest?location_id=1").json()["id"] == 1


def test_double_void_fails(client):
    c, db = client
    oid = c.post("/api/refills/run?location_id=1").json()["id"]
    assert c.post(f"/api/refills/{oid}/void").status_code == 200
    assert c.post(f"/api/refills/{oid}/void").status_code == 409


def test_no_effective_order_shows_empty_state(client):
    c, db = client
    # 作废所有未作废单（#2 本就已作废）
    assert c.post("/api/refills/1/void").status_code == 200

    latest = c.get("/api/refills/latest?location_id=1").json()
    assert latest["has_order"] is False
    assert latest["id"] is None
    assert latest["lines"] == []

    full = c.get("/api/refills/full?location_id=1").json()
    assert full["has_order"] is False
    assert full["lanes"] == []

    s = c.get("/api/refills/summary?location_id=1").json()
    assert s["has_order"] is False
    assert s["total_fill"] == 0

    # GET latest 不隐式建单
    assert len(c.get("/api/refills?location_id=1").json()) == 2


def test_void_missing_order_404(client):
    c, db = client
    assert c.post("/api/refills/999/void").status_code == 404

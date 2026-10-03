from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.models.models import Lane, Location, RefillOrder, ORDER_ACTIVE, ORDER_VERIFIED, ORDER_VOID

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(bind=engine)


def _seed_location():
    with TestingSession() as db:
        loc = Location(code="VM-1", name="测试点位")
        db.add(loc); db.flush()
        for slot, sku, cap, stock, transit in [
            ("A1", "水", 20, 5, 0),
            ("A2", "可乐", 18, 18, 0),
            ("B1", "薯片", 12, 3, 2),
        ]:
            db.add(Lane(location_id=loc.id, slot_no=slot, sku_name=sku,
                        capacity=cap, stock=stock, in_transit=transit))
        db.commit()
        return loc.id


def _lane_snapshot(location_id):
    with TestingSession() as db:
        return [(l.slot_no, l.stock, l.in_transit)
                for l in db.scalars(select(Lane).where(Lane.location_id == location_id)
                                    .order_by(Lane.slot_no)).all()]


def _override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app, base_url="http://test/api")


def setup_function(_):
    # 每个用例清空补货单，保留一个干净点位
    with TestingSession() as db:
        db.query(RefillOrder).delete()
        db.query(Lane).delete()
        db.query(Location).delete()
        db.commit()


def _run(lid):
    return client.post("refills/run", params={"location_id": lid}).json()


def test_void_falls_back_to_previous_order_and_keeps_lanes():
    lid = _seed_location()
    first = _run(lid)

    # 两次补货之间 A1 又售出 5 件，最新单的建议总量随之变大
    with TestingSession() as db:
        a1 = db.scalars(select(Lane).where(Lane.location_id == lid, Lane.slot_no == "A1")).first()
        a1.stock = 0
        db.commit()

    second = _run(lid)
    assert second["id"] > first["id"]
    assert second["total_fill"] != first["total_fill"]

    before = _lane_snapshot(lid)
    # 作废最新单
    r = client.post(f"refills/{second['id']}/void")
    assert r.status_code == 200
    assert r.json()["status"] == ORDER_VOID

    # 货道库存与在途保持不变
    assert _lane_snapshot(lid) == before

    # 最新有效单回退到上一张
    latest = client.get("refills/latest", params={"location_id": lid}).json()
    assert latest["id"] == first["id"]
    assert latest["status"] == ORDER_ACTIVE

    # 汇总引用上一张，而不是被作废单
    summary = client.get("refills/summary", params={"location_id": lid}).json()
    assert summary["order_id"] == first["id"]
    assert summary["total_fill"] == first["total_fill"]
    assert summary["total_fill"] != second["total_fill"]

    # 满仓页同样依据上一张
    full = client.get("refills/full", params={"location_id": lid}).json()
    assert full["order_id"] == first["id"]
    assert {l["slot_no"] for l in full["lanes"]} == {"A2"}


def test_verified_order_cannot_be_voided_and_nothing_moves():
    lid = _seed_location()
    order = _run(lid)

    before = _lane_snapshot(lid)
    summary_before = client.get("refills/summary", params={"location_id": lid}).json()

    vr = client.post(f"refills/{order['id']}/verify")
    assert vr.status_code == 200
    assert vr.json()["status"] == ORDER_VERIFIED

    # 已核销单作废必须失败
    r = client.post(f"refills/{order['id']}/void")
    assert r.status_code == 409

    # 单据状态仍是已核销，有效单指针、汇总、库存都不动
    with TestingSession() as db:
        assert db.get(RefillOrder, order["id"]).status == ORDER_VERIFIED
    latest = client.get("refills/latest", params={"location_id": lid}).json()
    assert latest["id"] == order["id"]
    assert latest["status"] == ORDER_VERIFIED
    summary_after = client.get("refills/summary", params={"location_id": lid}).json()
    assert summary_after["order_id"] == order["id"]
    assert summary_after["total_fill"] == summary_before["total_fill"]
    assert _lane_snapshot(lid) == before


def test_void_and_verify_are_mutually_exclusive():
    lid = _seed_location()
    order = _run(lid)
    assert client.post(f"refills/{order['id']}/void").status_code == 200
    # 已作废单不能再核销
    assert client.post(f"refills/{order['id']}/verify").status_code == 409
    with TestingSession() as db:
        assert db.get(RefillOrder, order["id"]).status == ORDER_VOID


def test_all_voided_shows_no_valid_order():
    lid = _seed_location()
    first = _run(lid)
    second = _run(lid)
    client.post(f"refills/{second['id']}/void")
    client.post(f"refills/{first['id']}/void")

    latest = client.get("refills/latest", params={"location_id": lid}).json()
    assert latest["id"] is None
    assert latest["lines"] == []

    summary = client.get("refills/summary", params={"location_id": lid}).json()
    assert summary["has_valid_order"] is False
    assert summary["order_id"] is None
    assert summary["total_fill"] == 0

    full = client.get("refills/full", params={"location_id": lid}).json()
    assert full["order_id"] is None
    assert full["lanes"] == []

    # 货道依旧完好，没有被清零
    assert _lane_snapshot(lid) == [("A1", 5, 0), ("A2", 18, 0), ("B1", 3, 2)]


def test_void_unknown_and_double_void_fail():
    lid = _seed_location()
    order = _run(lid)
    assert client.post("refills/9999/void").status_code == 404

    assert client.post(f"refills/{order['id']}/void").status_code == 200
    assert client.post(f"refills/{order['id']}/void").status_code == 409


def test_verified_order_still_valid_reference():
    # 最新单被核销但未作废：仍是满仓与汇总的默认依据
    lid = _seed_location()
    _run(lid)
    second = _run(lid)
    client.post(f"refills/{second['id']}/verify")
    summary = client.get("refills/summary", params={"location_id": lid}).json()
    assert summary["order_id"] == second["id"]
    assert summary["status"] == ORDER_VERIFIED

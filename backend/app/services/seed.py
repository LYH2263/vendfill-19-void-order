import json
from datetime import datetime, timedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.models import Lane, Location, RefillOrder, Sale
from app.services.fill_engine import build_fill_lines, summarize

def _snapshot_lanes(db: Session, location_id: int) -> list[dict]:
    lanes = db.scalars(select(Lane).where(Lane.location_id == location_id).order_by(Lane.slot_no)).all()
    return [{"id": l.id, "slot_no": l.slot_no, "sku_name": l.sku_name,
             "capacity": l.capacity, "stock": l.stock, "in_transit": l.in_transit} for l in lanes]

def _add_order(db: Session, location_id: int, created_at: datetime, requested: dict[int, int] | None) -> RefillOrder:
    payload = _snapshot_lanes(db, location_id)
    summary = summarize(build_fill_lines(payload, requested=requested))
    order = RefillOrder(location_id=location_id, created_at=created_at, status="active",
                        lines_json=json.dumps(summary, ensure_ascii=False))
    db.add(order); db.flush()
    return order

def seed_if_empty(db: Session) -> None:
    if (db.scalar(select(func.count()).select_from(Location)) or 0) > 0:
        return
    loc = Location(code="VM-01", name="地铁口 A 点位", address="城东地铁 1 号口")
    db.add(loc); db.flush()
    lanes = [
        ("A1", "矿泉水", 20, 5, 0),
        ("A2", "可乐", 18, 18, 0),
        ("B1", "薯片", 12, 3, 2),
        ("B2", "巧克力", 15, 10, 5),
        ("C1", "能量棒", 10, 0, 0),
        ("C2", "口香糖", 24, 24, 2),
    ]
    lane_ids = []
    for slot, sku, cap, stock, transit in lanes:
        lane = Lane(location_id=loc.id, slot_no=slot, sku_name=sku, capacity=cap, stock=stock, in_transit=transit)
        db.add(lane); db.flush()
        lane_ids.append(lane.id)
    now = datetime(2026, 9, 16, 12, 0, 0)
    for i, lid in enumerate(lane_ids):
        db.add(Sale(lane_id=lid, qty=2 + i, sold_at=now - timedelta(hours=i)))
    # 第一张单：缩减版补货请求；第二张单：按缺口全补。第二张开单后即作废，
    # 因此默认展示（最新有效单）回退到第一张；货道库存与在途全程不变。
    first = _add_order(db, loc.id, now - timedelta(days=1),
                       requested={lane_ids[0]: 5, lane_ids[2]: 4, lane_ids[4]: 6})
    second = _add_order(db, loc.id, now, requested=None)
    second.status = "voided"
    db.commit()

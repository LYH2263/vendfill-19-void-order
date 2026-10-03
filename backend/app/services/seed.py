import json
from datetime import datetime, timedelta
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.models import Lane, Location, RefillOrder, Sale, ORDER_ACTIVE, ORDER_VOID
from app.services.fill_engine import build_fill_lines, summarize


def _lane_payload(lanes: list[Lane], transit_delta: dict[int, int] | None = None) -> list[dict]:
    transit_delta = transit_delta or {}
    return [{"id": l.id, "slot_no": l.slot_no, "sku_name": l.sku_name, "capacity": l.capacity,
             "stock": l.stock, "in_transit": l.in_transit + transit_delta.get(l.id, 0)} for l in lanes]


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

    db_lanes = db.scalars(select(Lane).where(Lane.location_id == loc.id).order_by(Lane.slot_no)).all()
    # 上一张有效单：按当前货道缺口生成（总件数 32）
    first = summarize(build_fill_lines(_lane_payload(db_lanes)))
    db.add(RefillOrder(location_id=loc.id, created_at=now - timedelta(days=1),
                       lines_json=json.dumps(first, ensure_ascii=False), status=ORDER_ACTIVE))
    # 最新单：记录时 A1 多算 15 件在途（总件数 17），随后该单被作废。
    # 货道库存与在途从未因此改变；满仓与汇总必须回退引用上一张未作废单。
    latest = summarize(build_fill_lines(_lane_payload(db_lanes, transit_delta={lane_ids[0]: 15})))
    db.add(RefillOrder(location_id=loc.id, created_at=now,
                       lines_json=json.dumps(latest, ensure_ascii=False), status=ORDER_VOID))
    db.commit()

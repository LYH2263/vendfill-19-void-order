import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Lane, Location, RefillOrder
from app.services.fill_engine import build_fill_lines, summarize
router = APIRouter(prefix="/refills", tags=["refills"])

# 有效单 = 未作废单（active 或 verified）；作废单不参与任何默认展示
def _latest_effective_order(db: Session, location_id: int) -> RefillOrder | None:
    return db.scalars(
        select(RefillOrder)
        .where(RefillOrder.location_id == location_id, RefillOrder.status != "voided")
        .order_by(RefillOrder.id.desc())
    ).first()

def _order_payload(order: RefillOrder, location_id: int) -> dict:
    data = json.loads(order.lines_json)
    return {"id": order.id, "location_id": location_id, "status": order.status, **data}

@router.post("/run")
def run_refill(location_id: int = 1, db: Session = Depends(get_db)):
    loc = db.get(Location, location_id)
    if not loc: raise HTTPException(404, "点位不存在")
    lanes = db.scalars(select(Lane).where(Lane.location_id == location_id).order_by(Lane.slot_no)).all()
    payload = [{"id": l.id, "slot_no": l.slot_no, "sku_name": l.sku_name,
                "capacity": l.capacity, "stock": l.stock, "in_transit": l.in_transit} for l in lanes]
    summary = summarize(build_fill_lines(payload))
    order = RefillOrder(location_id=location_id, created_at=datetime.utcnow(), status="active",
                        lines_json=json.dumps(summary, ensure_ascii=False))
    db.add(order); db.commit(); db.refresh(order)
    return _order_payload(order, location_id)

@router.get("")
def list_orders(location_id: int = 1, db: Session = Depends(get_db)):
    rows = db.scalars(
        select(RefillOrder).where(RefillOrder.location_id == location_id).order_by(RefillOrder.id.desc())
    ).all()
    return [{"id": o.id, "location_id": location_id, "status": o.status,
             "created_at": o.created_at.isoformat(), **json.loads(o.lines_json)} for o in rows]

@router.get("/latest")
def latest(location_id: int = 1, db: Session = Depends(get_db)):
    order = _latest_effective_order(db, location_id)
    if not order:
        # 无有效单：显式空态，绝不回退到已作废单，也不隐式新建
        return {"id": None, "location_id": location_id, "status": None, "has_order": False,
                "total_fill": 0, "need_fill_count": 0, "full_count": 0, "overbooked_count": 0,
                "lines": []}
    return {"has_order": True, **_order_payload(order, location_id)}

@router.get("/full")
def full_lanes(location_id: int = 1, db: Session = Depends(get_db)):
    data = latest(location_id=location_id, db=db)
    return {"location_id": location_id, "order_id": data["id"], "has_order": data["has_order"],
            "lanes": [l for l in data["lines"] if l["status"] == "full"]}

@router.get("/summary")
def refill_summary(location_id: int = 1, db: Session = Depends(get_db)):
    data = latest(location_id=location_id, db=db)
    return {
        "location_id": location_id,
        "order_id": data["id"],
        "status": data["status"],
        "has_order": data["has_order"],
        "total_fill": data["total_fill"],
        "need_fill_count": data["need_fill_count"],
        "full_count": data["full_count"],
        "overbooked_count": data["overbooked_count"],
    }

@router.post("/{order_id}/void")
def void_order(order_id: int, db: Session = Depends(get_db)):
    """作废补货单：仅翻转单据状态。已核销/已作废单禁止作废；货道库存与在途永不被改写。"""
    order = db.get(RefillOrder, order_id)
    if not order:
        raise HTTPException(404, "补货单不存在")
    if order.status == "verified":
        raise HTTPException(409, "已核销补货单禁止作废")
    if order.status == "voided":
        raise HTTPException(409, "补货单已作废，不能重复作废")
    order.status = "voided"
    db.commit(); db.refresh(order)
    return {"id": order.id, "status": order.status}

@router.post("/{order_id}/verify")
def verify_order(order_id: int, db: Session = Depends(get_db)):
    """核销补货单：active -> verified。已作废单禁止核销（作废与核销互斥）。"""
    order = db.get(RefillOrder, order_id)
    if not order:
        raise HTTPException(404, "补货单不存在")
    if order.status == "voided":
        raise HTTPException(409, "已作废补货单不能核销")
    if order.status == "verified":
        raise HTTPException(409, "补货单已核销，不能重复核销")
    order.status = "verified"
    db.commit(); db.refresh(order)
    return {"id": order.id, "status": order.status}

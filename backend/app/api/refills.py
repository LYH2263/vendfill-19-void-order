import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Lane, Location, RefillOrder, ORDER_ACTIVE, ORDER_VERIFIED, ORDER_VOID
from app.services.fill_engine import build_fill_lines, summarize
router = APIRouter(prefix="/refills", tags=["refills"])

# 汇总/满仓在“无有效单”时返回的空态计数
_EMPTY_COUNTS = {"total_fill": 0, "need_fill_count": 0, "full_count": 0, "overbooked_count": 0}
_STATUS_LABEL = {ORDER_ACTIVE: "未核销", ORDER_VERIFIED: "已核销", ORDER_VOID: "已作废"}


def _latest_valid_order(db: Session, location_id: int) -> RefillOrder | None:
    """最新有效单 = 该点位最新一张未作废单（active/verified 均算）。"""
    return db.scalars(
        select(RefillOrder)
        .where(RefillOrder.location_id == location_id, RefillOrder.status != ORDER_VOID)
        .order_by(RefillOrder.id.desc())
    ).first()


def _serialize(order: RefillOrder) -> dict:
    data = json.loads(order.lines_json)
    return {
        "id": order.id,
        "location_id": order.location_id,
        "status": order.status,
        "status_label": _STATUS_LABEL.get(order.status, order.status),
        "created_at": order.created_at.isoformat() if order.created_at else None,
        **data,
    }


def _empty_state(location_id: int) -> dict:
    return {"id": None, "location_id": location_id, "status": None, "status_label": "无有效单",
            "created_at": None, **_EMPTY_COUNTS, "lines": []}


@router.post("/run")
def run_refill(location_id: int = 1, db: Session = Depends(get_db)):
    loc = db.get(Location, location_id)
    if not loc: raise HTTPException(404, "点位不存在")
    lanes = db.scalars(select(Lane).where(Lane.location_id == location_id).order_by(Lane.slot_no)).all()
    payload = [{"id": l.id, "slot_no": l.slot_no, "sku_name": l.sku_name,
                "capacity": l.capacity, "stock": l.stock, "in_transit": l.in_transit} for l in lanes]
    summary = summarize(build_fill_lines(payload))
    order = RefillOrder(location_id=location_id, created_at=datetime.utcnow(),
                        lines_json=json.dumps(summary, ensure_ascii=False), status=ORDER_ACTIVE)
    db.add(order); db.commit(); db.refresh(order)
    return _serialize(order)


@router.get("")
def list_orders(location_id: int = 1, db: Session = Depends(get_db)):
    orders = db.scalars(
        select(RefillOrder).where(RefillOrder.location_id == location_id).order_by(RefillOrder.id.desc())
    ).all()
    out = []
    for o in orders:
        data = json.loads(o.lines_json)
        out.append({
            "id": o.id, "location_id": o.location_id, "status": o.status,
            "status_label": _STATUS_LABEL.get(o.status, o.status),
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "total_fill": data.get("total_fill", 0),
            "need_fill_count": data.get("need_fill_count", 0),
            "full_count": data.get("full_count", 0),
            "overbooked_count": data.get("overbooked_count", 0),
        })
    return out


@router.get("/latest")
def latest(location_id: int = 1, db: Session = Depends(get_db)):
    order = _latest_valid_order(db, location_id)
    # 无有效单时不再自动生成：页面显示“无有效单”，避免凭空造出引用单
    return _serialize(order) if order else _empty_state(location_id)


@router.get("/full")
def full_lanes(location_id: int = 1, db: Session = Depends(get_db)):
    order = _latest_valid_order(db, location_id)
    if not order:
        return {"location_id": location_id, "order_id": None, "lanes": []}
    data = json.loads(order.lines_json)
    return {"location_id": location_id, "order_id": order.id,
            "lanes": [l for l in data["lines"] if l["status"] == "full"]}


@router.get("/summary")
def refill_summary(location_id: int = 1, db: Session = Depends(get_db)):
    order = _latest_valid_order(db, location_id)
    base = {"location_id": location_id}
    if not order:
        return {**base, "order_id": None, "status": None, "has_valid_order": False, **_EMPTY_COUNTS}
    data = json.loads(order.lines_json)
    return {
        **base, "order_id": order.id, "status": order.status,
        "status_label": _STATUS_LABEL.get(order.status, order.status), "has_valid_order": True,
        "total_fill": data["total_fill"], "need_fill_count": data["need_fill_count"],
        "full_count": data["full_count"], "overbooked_count": data["overbooked_count"],
    }


@router.post("/{order_id}/verify")
def verify_order(order_id: int, db: Session = Depends(get_db)):
    """核销：作废与核销互斥，已作废单不能核销。核销不动货道库存/在途。"""
    order = db.get(RefillOrder, order_id)
    if not order: raise HTTPException(404, "补货单不存在")
    if order.status == ORDER_VOID:
        raise HTTPException(409, "已作废的补货单不能核销")
    if order.status != ORDER_VERIFIED:
        order.status = ORDER_VERIFIED
        db.commit(); db.refresh(order)
    return _serialize(order)


@router.post("/{order_id}/void")
def void_order(order_id: int, db: Session = Depends(get_db)):
    """作废未核销单。仅翻转单据状态：货道库存与在途保持不变；
    已核销单禁止作废，失败时不写库，有效单指针/汇总/库存均不动。"""
    order = db.get(RefillOrder, order_id)
    if not order: raise HTTPException(404, "补货单不存在")
    if order.status == ORDER_VERIFIED:
        raise HTTPException(409, "已核销的补货单不能作废")
    if order.status == ORDER_VOID:
        raise HTTPException(409, "补货单已作废，不能重复作废")
    order.status = ORDER_VOID
    db.commit(); db.refresh(order)
    return _serialize(order)

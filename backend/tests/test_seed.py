from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.models import Lane, RefillOrder
from app.services.seed import seed_if_empty


def _db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_seed_latest_order_voided_summary_uses_previous_and_lanes_intact():
    db = _db()
    seed_if_empty(db)

    orders = db.scalars(select(RefillOrder).order_by(RefillOrder.id)).all()
    assert len(orders) == 2
    first, latest = orders
    assert latest.status == "void"
    assert first.status == "active"

    import json
    first_total = json.loads(first.lines_json)["total_fill"]
    latest_total = json.loads(latest.lines_json)["total_fill"]
    assert first_total != latest_total

    # 汇总口径：最新有效单是上一张，不用被作废单的总件数
    valid = db.scalars(
        select(RefillOrder).where(RefillOrder.status != "void").order_by(RefillOrder.id.desc())
    ).first()
    assert valid.id == first.id
    assert json.loads(valid.lines_json)["total_fill"] == first_total

    # 货道库存与在途与种子设定完全一致，未因作废被清零或改写
    lanes = db.scalars(select(Lane).order_by(Lane.slot_no)).all()
    assert [(l.slot_no, l.stock, l.in_transit) for l in lanes] == [
        ("A1", 5, 0), ("A2", 18, 0), ("B1", 3, 2),
        ("B2", 10, 5), ("C1", 0, 0), ("C2", 24, 2),
    ]

"""Admin Statistics API router.

Provides endpoints for viewing moderation statistics:
- GET /api/admin/stats/volume       — audit volume trends (by day/week/month)
- GET /api/admin/stats/rule-hits    — rule hit rate statistics
- GET /api/admin/stats/cost         — model invocation cost statistics
- GET /api/admin/stats/text-labels  — text label distribution
- GET /api/admin/stats/image-labels — image label distribution
- GET /api/admin/stats/languages    — language distribution

Validates: Requirements 8.1, 8.2, 8.3, 15.1, 15.2, 15.3, 15.4
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, cast, func, select, String
from sqlalchemy.orm import Session

from backend.app.core.auth import verify_cognito_token
from backend.app.core.database import get_db
from backend.app.models.moderation_logs import ModerationLog
from backend.app.models.label_definitions import LabelDefinition
from backend.app.schemas.stats import (
    CostDataPoint,
    CostStatsResponse,
    LabelDistributionItem,
    LabelDistributionResponse,
    LanguageDistributionItem,
    LanguageDistributionResponse,
    RuleHitItem,
    RuleHitsResponse,
    VolumeDataPoint,
    VolumeStatsResponse,
)

router = APIRouter(
    prefix="/api/admin/stats",
    dependencies=[Depends(verify_cognito_token)],
)

# Default date range: last 30 days
_DEFAULT_DAYS = 30


def _default_start() -> date:
    return date.today() - timedelta(days=_DEFAULT_DAYS)


def _default_end() -> date:
    return date.today()


# ---------------------------------------------------------------------------
# GET /api/admin/stats/volume  (Requirement 8.1)
# ---------------------------------------------------------------------------


@router.get("/volume", response_model=VolumeStatsResponse, summary="审核量趋势")
async def get_volume_stats(
    granularity: str = Query(
        default="day",
        description="粒度: day / week / month",
        pattern="^(day|week|month)$",
    ),
    start_date: date | None = Query(default=None, description="开始日期 (YYYY-MM-DD)"),
    end_date: date | None = Query(default=None, description="结束日期 (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> VolumeStatsResponse:
    """Return audit volume grouped by the requested time granularity."""
    sd = start_date or _default_start()
    ed = end_date or _default_end()

    # Build the period expression based on granularity
    if granularity == "day":
        period_expr = cast(func.date(ModerationLog.created_at), String)
    elif granularity == "week":
        # ISO week start (Monday) — use date_trunc for portability
        period_expr = cast(func.date_trunc("week", ModerationLog.created_at), String)
    else:  # month
        period_expr = cast(func.date_trunc("month", ModerationLog.created_at), String)

    stmt = (
        select(
            period_expr.label("period"),
            func.count().label("total"),
            func.count(case((ModerationLog.result == "pass", 1))).label("pass_count"),
            func.count(case((ModerationLog.result == "reject", 1))).label("reject_count"),
            func.count(case((ModerationLog.result == "review", 1))).label("review_count"),
            func.count(case((ModerationLog.result == "flag", 1))).label("flag_count"),
        )
        .where(ModerationLog.created_at >= datetime(sd.year, sd.month, sd.day, tzinfo=timezone.utc))
        .where(
            ModerationLog.created_at
            < datetime(ed.year, ed.month, ed.day, tzinfo=timezone.utc) + timedelta(days=1)
        )
        .group_by(period_expr)
        .order_by(period_expr)
    )

    rows = db.execute(stmt).all()

    data = [
        VolumeDataPoint(
            period=str(row.period),
            total=row.total,
            pass_count=row.pass_count,
            reject_count=row.reject_count,
            review_count=row.review_count,
            flag_count=row.flag_count,
        )
        for row in rows
    ]

    return VolumeStatsResponse(granularity=granularity, data=data)


# ---------------------------------------------------------------------------
# GET /api/admin/stats/rule-hits  (Requirement 8.2)
# ---------------------------------------------------------------------------


@router.get("/rule-hits", response_model=RuleHitsResponse, summary="规则命中率")
async def get_rule_hits(
    start_date: date | None = Query(default=None, description="开始日期 (YYYY-MM-DD)"),
    end_date: date | None = Query(default=None, description="结束日期 (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> RuleHitsResponse:
    """Aggregate matched_rules from moderation logs and compute hit rates."""
    sd = start_date or _default_start()
    ed = end_date or _default_end()

    start_dt = datetime(sd.year, sd.month, sd.day, tzinfo=timezone.utc)
    end_dt = datetime(ed.year, ed.month, ed.day, tzinfo=timezone.utc) + timedelta(days=1)

    # Total moderation count in range
    total_count: int = (
        db.execute(
            select(func.count(ModerationLog.id))
            .where(ModerationLog.created_at >= start_dt)
            .where(ModerationLog.created_at < end_dt)
        ).scalar_one()
    )

    if total_count == 0:
        return RuleHitsResponse(total_moderation_count=0, rules=[])

    # Fetch logs with non-empty matched_rules
    logs = (
        db.execute(
            select(ModerationLog.matched_rules)
            .where(ModerationLog.created_at >= start_dt)
            .where(ModerationLog.created_at < end_dt)
            .where(ModerationLog.matched_rules.isnot(None))
        )
        .scalars()
        .all()
    )

    # Count hits per rule — use rule_name as key since AI model returns
    # descriptive rule_ids that may not be valid UUIDs
    hit_counts: dict[str, int] = {}
    for matched in logs:
        if not isinstance(matched, list):
            continue
        for entry in matched:
            if isinstance(entry, dict):
                name = str(entry.get("rule_name", entry.get("rule_id", "unknown")))
                if name:
                    hit_counts[name] = hit_counts.get(name, 0) + 1

    items = [
        RuleHitItem(
            rule_id=name,
            rule_name=name,
            hit_count=count,
            hit_rate=round(count / total_count, 4),
        )
        for name, count in sorted(hit_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    return RuleHitsResponse(total_moderation_count=total_count, rules=items)


# ---------------------------------------------------------------------------
# GET /api/admin/stats/cost  (Requirement 8.3)
# ---------------------------------------------------------------------------


@router.get("/cost", response_model=CostStatsResponse, summary="模型调用成本统计")
async def get_cost_stats(
    start_date: date | None = Query(default=None, description="开始日期 (YYYY-MM-DD)"),
    end_date: date | None = Query(default=None, description="结束日期 (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> CostStatsResponse:
    """Aggregate model invocation counts and estimate costs."""
    sd = start_date or _default_start()
    ed = end_date or _default_end()

    start_dt = datetime(sd.year, sd.month, sd.day, tzinfo=timezone.utc)
    end_dt = datetime(ed.year, ed.month, ed.day, tzinfo=timezone.utc) + timedelta(days=1)

    period_expr = cast(func.date(ModerationLog.created_at), String)

    stmt = (
        select(
            period_expr.label("period"),
            ModerationLog.model_id,
            func.count().label("call_count"),
        )
        .where(ModerationLog.created_at >= start_dt)
        .where(ModerationLog.created_at < end_dt)
        .where(ModerationLog.model_id.isnot(None))
        .where(ModerationLog.model_id != "")
        .group_by(period_expr, ModerationLog.model_id)
        .order_by(period_expr)
    )

    rows = db.execute(stmt).all()

    # Build a cost-per-call lookup from model_config table
    from backend.app.models.model_config import ModelConfig

    configs = db.execute(
        select(ModelConfig.model_id, ModelConfig.cost_per_1k_input, ModelConfig.cost_per_1k_output)
    ).all()
    cost_map: dict[str, float] = {}
    for cfg in configs:
        # Rough estimate: assume ~500 input tokens + ~200 output tokens per call
        est = (cfg.cost_per_1k_input * 0.5) + (cfg.cost_per_1k_output * 0.2)
        cost_map[cfg.model_id] = est

    data: list[CostDataPoint] = []
    total_cost = 0.0
    for row in rows:
        per_call = cost_map.get(row.model_id, 0.0)
        estimated = round(per_call * row.call_count, 4)
        total_cost += estimated
        data.append(
            CostDataPoint(
                period=str(row.period),
                model_id=row.model_id,
                call_count=row.call_count,
                estimated_cost=estimated,
            )
        )

    return CostStatsResponse(data=data, total_cost=round(total_cost, 4))


# ---------------------------------------------------------------------------
# GET /api/admin/stats/text-labels  (Requirement 15.1)
# ---------------------------------------------------------------------------


@router.get("/text-labels", response_model=LabelDistributionResponse, summary="文案标签分布")
async def get_text_label_stats(
    start_date: date | None = Query(default=None, description="开始日期 (YYYY-MM-DD)"),
    end_date: date | None = Query(default=None, description="结束日期 (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> LabelDistributionResponse:
    """Return text_label distribution with display names from label_definitions."""
    sd = start_date or _default_start()
    ed = end_date or _default_end()
    start_dt = datetime(sd.year, sd.month, sd.day, tzinfo=timezone.utc)
    end_dt = datetime(ed.year, ed.month, ed.day, tzinfo=timezone.utc) + timedelta(days=1)

    # Group by text_label and count
    stmt = (
        select(
            ModerationLog.text_label.label("label"),
            func.count().label("cnt"),
        )
        .where(ModerationLog.created_at >= start_dt)
        .where(ModerationLog.created_at < end_dt)
        .where(ModerationLog.text_label.isnot(None))
        .where(ModerationLog.text_label != "")
        .group_by(ModerationLog.text_label)
        .order_by(func.count().desc())
    )
    rows = db.execute(stmt).all()

    # Build display_name lookup from label_definitions (type=text)
    label_defs = db.execute(
        select(LabelDefinition.label_key, LabelDefinition.display_name).where(
            LabelDefinition.label_type == "text"
        )
    ).all()
    display_map: dict[str, str] = {ld.label_key: ld.display_name for ld in label_defs}

    total = sum(row.cnt for row in rows)
    items = [
        LabelDistributionItem(
            label=row.label,
            display_name=display_map.get(row.label, row.label),
            count=row.cnt,
        )
        for row in rows
    ]
    return LabelDistributionResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# GET /api/admin/stats/image-labels  (Requirement 15.2)
# ---------------------------------------------------------------------------


@router.get("/image-labels", response_model=LabelDistributionResponse, summary="图片标签分布")
async def get_image_label_stats(
    start_date: date | None = Query(default=None, description="开始日期 (YYYY-MM-DD)"),
    end_date: date | None = Query(default=None, description="结束日期 (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> LabelDistributionResponse:
    """Return image_label distribution with display names from label_definitions."""
    sd = start_date or _default_start()
    ed = end_date or _default_end()
    start_dt = datetime(sd.year, sd.month, sd.day, tzinfo=timezone.utc)
    end_dt = datetime(ed.year, ed.month, ed.day, tzinfo=timezone.utc) + timedelta(days=1)

    stmt = (
        select(
            ModerationLog.image_label.label("label"),
            func.count().label("cnt"),
        )
        .where(ModerationLog.created_at >= start_dt)
        .where(ModerationLog.created_at < end_dt)
        .where(ModerationLog.image_label.isnot(None))
        .where(ModerationLog.image_label != "")
        .group_by(ModerationLog.image_label)
        .order_by(func.count().desc())
    )
    rows = db.execute(stmt).all()

    # Build display_name lookup from label_definitions (type=image)
    label_defs = db.execute(
        select(LabelDefinition.label_key, LabelDefinition.display_name).where(
            LabelDefinition.label_type == "image"
        )
    ).all()
    display_map: dict[str, str] = {ld.label_key: ld.display_name for ld in label_defs}

    total = sum(row.cnt for row in rows)
    items = [
        LabelDistributionItem(
            label=row.label,
            display_name=display_map.get(row.label, row.label),
            count=row.cnt,
        )
        for row in rows
    ]
    return LabelDistributionResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# GET /api/admin/stats/languages  (Requirement 15.3)
# ---------------------------------------------------------------------------


@router.get("/languages", response_model=LanguageDistributionResponse, summary="语言分布")
async def get_language_stats(
    start_date: date | None = Query(default=None, description="开始日期 (YYYY-MM-DD)"),
    end_date: date | None = Query(default=None, description="结束日期 (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> LanguageDistributionResponse:
    """Return language distribution from moderation logs."""
    sd = start_date or _default_start()
    ed = end_date or _default_end()
    start_dt = datetime(sd.year, sd.month, sd.day, tzinfo=timezone.utc)
    end_dt = datetime(ed.year, ed.month, ed.day, tzinfo=timezone.utc) + timedelta(days=1)

    stmt = (
        select(
            ModerationLog.language.label("lang"),
            func.count().label("cnt"),
        )
        .where(ModerationLog.created_at >= start_dt)
        .where(ModerationLog.created_at < end_dt)
        .where(ModerationLog.language.isnot(None))
        .where(ModerationLog.language != "")
        .group_by(ModerationLog.language)
        .order_by(func.count().desc())
    )
    rows = db.execute(stmt).all()

    total = sum(row.cnt for row in rows)
    items = [
        LanguageDistributionItem(language=row.lang, count=row.cnt)
        for row in rows
    ]
    return LanguageDistributionResponse(items=items, total=total)

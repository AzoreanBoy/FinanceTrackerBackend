from datetime import date
from decimal import Decimal

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .analytics import build_expense_analytics, shift_month


def _parse_date(value, fallback):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def expense_analytics(request):
    today = timezone.localdate()
    default_start = shift_month(today.replace(day=1), -5)
    start_date = _parse_date(request.query_params.get("start"), default_start)
    end_date = _parse_date(request.query_params.get("end"), today)
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    data = build_expense_analytics(
        request.user,
        start_date,
        end_date,
        account_id=request.query_params.get("account") or None,
        category_id=request.query_params.get("category") or None,
    )
    data["filters"] = {"start": start_date, "end": end_date}
    return Response(_json_safe(data))
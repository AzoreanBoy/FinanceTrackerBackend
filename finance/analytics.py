from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db.models import Sum
from django.db.models.functions import TruncMonth

from .models import Transaction


def shift_month(value, offset):
    month_index = value.year * 12 + value.month - 1 + offset
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    return date(year, month, 1)


def month_range(start_date, end_date):
    current = start_date.replace(day=1)
    last = end_date.replace(day=1)
    months = []
    while current <= last:
        months.append(current)
        current = shift_month(current, 1)
    return months


def _month_key(value):
    if hasattr(value, "date"):
        value = value.date()
    return value.strftime("%Y-%m")


def _empty_months(months):
    return {month.strftime("%Y-%m"): Decimal("0") for month in months}


def build_expense_analytics(user, start_date, end_date, account_id=None, category_id=None):
    months = month_range(start_date, end_date)
    queryset = Transaction.objects.filter(
        account__owner=user,
        type="expense",
        transaction_date__range=(start_date, end_date),
    )
    if account_id:
        queryset = queryset.filter(account_id=account_id)
    if category_id:
        queryset = queryset.filter(category_id=category_id)

    monthly_rows = (
        queryset.annotate(month=TruncMonth("transaction_date"))
        .values("month")
        .annotate(total=Sum("amount"))
    )
    monthly_totals = _empty_months(months)
    for row in monthly_rows:
        monthly_totals[_month_key(row["month"])] = row["total"] or Decimal("0")

    category_rows = (
        queryset.annotate(month=TruncMonth("transaction_date"))
        .values("category_id", "category__name", "month")
        .annotate(total=Sum("amount"))
    )
    category_data = {}
    for row in category_rows:
        category_key = row["category_id"] or "uncategorised"
        category = category_data.setdefault(
            category_key,
            {
                "name": row["category__name"] or "Uncategorised",
                "total": Decimal("0"),
                "months": _empty_months(months),
            },
        )
        total = row["total"] or Decimal("0")
        category["total"] += total
        category["months"][_month_key(row["month"])] = total

    subcategory_rows = (
        queryset.annotate(month=TruncMonth("transaction_date"))
        .values("subcategory_id", "subcategory__name", "month")
        .annotate(total=Sum("amount"))
    )
    subcategory_data = {}
    for row in subcategory_rows:
        subcategory_key = row["subcategory_id"] or "uncategorised"
        subcategory = subcategory_data.setdefault(
            subcategory_key,
            {
                "name": row["subcategory__name"] or "Uncategorised",
                "total": Decimal("0"),
                "months": _empty_months(months),
            },
        )
        total = row["total"] or Decimal("0")
        subcategory["total"] += total
        subcategory["months"][_month_key(row["month"])] = total

    total_expenses = sum(monthly_totals.values(), Decimal("0"))
    maximum_month = max(monthly_totals.values(), default=Decimal("0"))
    maximum_category = max(
        (category["total"] for category in category_data.values()),
        default=Decimal("0"),
    )

    def decorate(items, maximum):
        result = []
        for item in sorted(items.values(), key=lambda value: value["total"], reverse=True):
            item["share"] = (item["total"] / total_expenses * 100) if total_expenses else Decimal("0")
            item["bar"] = (item["total"] / maximum * 100) if maximum else Decimal("0")
            item["series"] = [
                {
                    "key": month.strftime("%Y-%m"),
                    "value": item["months"][month.strftime("%Y-%m")],
                    "bar": (item["months"][month.strftime("%Y-%m")] / maximum * 100) if maximum else Decimal("0"),
                }
                for month in months
            ]
            result.append(item)
        return result

    return {
        "months": [
            {
                "key": month.strftime("%Y-%m"),
                "label": month.strftime("%b %Y"),
                "total": monthly_totals[month.strftime("%Y-%m")],
                "bar": (monthly_totals[month.strftime("%Y-%m")] / maximum_month * 100) if maximum_month else Decimal("0"),
            }
            for month in months
        ],
        "categories": decorate(category_data, maximum_category),
        "subcategories": decorate(subcategory_data, maximum_category),
        "total_expenses": total_expenses,
        "transaction_count": queryset.count(),
        "average_monthly": total_expenses / len(months) if months else Decimal("0"),
    }
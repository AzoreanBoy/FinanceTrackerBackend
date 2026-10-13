from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q

from .currencies import ExchangeRateBook
from .models import Budget, Transaction, UserFinanceSettings

PIE_COLORS = (
    "#E88B72",
    "#55A98B",
    "#5797B8",
    "#D6A23F",
    "#9473B5",
    "#D36B87",
    "#6176B8",
    "#718B62",
    "#D1844C",
    "#4F8B83",
    "#9B718D",
    "#7F8C9A",
)


def shift_month(value, offset):
    month_index = value.year * 12 + value.month - 1 + offset
    year, month_index = divmod(month_index, 12)
    month = month_index + 1
    return date(year, month, 1)


def _easter_sunday(year):
    """Return Gregorian Easter Sunday using the Meeus/Jones/Butcher algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def portugal_mainland_holidays(year):
    easter = _easter_sunday(year)
    return {
        date(year, 1, 1),
        easter - timedelta(days=2),
        easter,
        date(year, 4, 25),
        date(year, 5, 1),
        easter + timedelta(days=60),
        date(year, 6, 10),
        date(year, 8, 15),
        date(year, 10, 5),
        date(year, 11, 1),
        date(year, 12, 1),
        date(year, 12, 8),
        date(year, 12, 25),
    }


def adjusted_payday(year, month, payday_day=25):
    nominal = date(year, month, min(payday_day, monthrange(year, month)[1]))
    holidays = portugal_mainland_holidays(year)
    while nominal.weekday() >= 5 or nominal in holidays:
        nominal -= timedelta(days=1)
    return nominal


def pay_cycle_for_date(on_date, payday_day=25):
    """Return the adjusted payday starting the cycle containing on_date and its end."""
    month_start = on_date.replace(day=1)
    candidate_dates = [
        adjusted_payday(
            shift_month(month_start, offset).year,
            shift_month(month_start, offset).month,
            payday_day,
        )
        for offset in (-2, -1, 0, 1, 2)
    ]
    previous_payday = max(
        payday for payday in candidate_dates if payday <= on_date
    )
    next_payday = min(
        payday for payday in candidate_dates if payday > previous_payday
    )
    return previous_payday, next_payday - timedelta(days=1), next_payday


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


def _budget_cycle_start(budget, index):
    if budget.period == "weekly":
        return budget.start_date + timedelta(days=index * 7)
    if budget.period == "yearly":
        year = budget.start_date.year + index
        return date(
            year,
            budget.start_date.month,
            min(budget.start_date.day, monthrange(year, budget.start_date.month)[1]),
        )

    month_start = shift_month(budget.start_date.replace(day=1), index)
    return month_start.replace(
        day=min(budget.start_date.day, monthrange(month_start.year, month_start.month)[1])
    )


def _budgeted_amount_for_range(budget, start_date, end_date):
    active_start = max(start_date, budget.start_date)
    active_end = min(end_date, budget.end_date or end_date)
    if active_start > active_end:
        return Decimal("0")

    if budget.period == "custom":
        if not budget.end_date:
            return budget.amount
        total_days = (budget.end_date - budget.start_date).days + 1
        overlap_days = (active_end - active_start).days + 1
        return (budget.amount * overlap_days / total_days).quantize(Decimal("0.01"))

    if budget.period == "weekly":
        cycle_index = (active_start - budget.start_date).days // 7
    elif budget.period == "yearly":
        cycle_index = active_start.year - budget.start_date.year
        if _budget_cycle_start(budget, cycle_index) > active_start:
            cycle_index -= 1
    else:
        cycle_index = (
            (active_start.year - budget.start_date.year) * 12
            + active_start.month
            - budget.start_date.month
        )
        if _budget_cycle_start(budget, cycle_index) > active_start:
            cycle_index -= 1

    budgeted = Decimal("0")
    cycle_start = _budget_cycle_start(budget, cycle_index)
    while cycle_start <= active_end:
        next_cycle = _budget_cycle_start(budget, cycle_index + 1)
        cycle_end = next_cycle - timedelta(days=1)
        overlap_start = max(active_start, cycle_start)
        overlap_end = min(active_end, cycle_end)
        if overlap_start <= overlap_end:
            overlap_days = (overlap_end - overlap_start).days + 1
            cycle_days = (cycle_end - cycle_start).days + 1
            budgeted += budget.amount * overlap_days / cycle_days
        cycle_index += 1
        cycle_start = next_cycle

    return budgeted.quantize(Decimal("0.01"))


def budget_cycle_bounds(budget, on_date):
    if budget.period == "custom":
        period_end = budget.end_date or on_date
        period_start = budget.start_date
    else:
        if budget.period == "weekly":
            cycle_index = max((on_date - budget.start_date).days // 7, 0)
        elif budget.period == "yearly":
            cycle_index = max(on_date.year - budget.start_date.year, 0)
            if _budget_cycle_start(budget, cycle_index) > on_date:
                cycle_index -= 1
        else:
            cycle_index = max(
                (on_date.year - budget.start_date.year) * 12
                + on_date.month
                - budget.start_date.month,
                0,
            )
            if _budget_cycle_start(budget, cycle_index) > on_date:
                cycle_index -= 1
        period_start = _budget_cycle_start(budget, cycle_index)
        period_end = _budget_cycle_start(budget, cycle_index + 1) - timedelta(days=1)
        period_start = max(period_start, budget.start_date)
        if budget.end_date:
            period_end = min(period_end, budget.end_date)

    if period_end < period_start:
        return period_start, period_end, Decimal("0")
    return (
        period_start,
        period_end,
        _budgeted_amount_for_range(budget, period_start, period_end),
    )


def _converted_rows(queryset, rates, reporting_currency):
    rows = []
    missing_currencies = {}
    for transaction in queryset.select_related("account", "category", "subcategory"):
        converted, _, _ = rates.convert(
            transaction.amount,
            transaction.account.currency,
            reporting_currency,
            transaction.transaction_date,
        )
        if converted is None:
            missing_currencies[transaction.account.currency] = (
                missing_currencies.get(transaction.account.currency, 0) + 1
            )
        else:
            rows.append((transaction, converted))
    return rows, missing_currencies


def _build_budget_comparison(
    user, start_date, end_date, account_id, category_id, rates, reporting_currency
):
    budgets = Budget.objects.filter(owner=user).select_related("category")
    if category_id:
        budgets = budgets.filter(
            Q(category_id=category_id) | Q(category__isnull=True)
        )

    results = []
    for budget in budgets:
        active_start = max(start_date, budget.start_date)
        active_end = min(end_date, budget.end_date or end_date)
        if active_start > active_end:
            continue

        expenses = Transaction.objects.filter(
            account__owner=user,
            type="expense",
            transaction_date__range=(active_start, active_end),
        )
        if account_id:
            expenses = expenses.filter(account_id=account_id)
        if budget.category_id:
            expenses = expenses.filter(category_id=budget.category_id)
        if category_id:
            expenses = expenses.filter(category_id=category_id)

        converted_expenses, missing_currencies = _converted_rows(
            expenses, rates, reporting_currency
        )
        spent = sum((amount for _, amount in converted_expenses), Decimal("0"))
        budgeted_native = _budgeted_amount_for_range(budget, start_date, end_date)
        budgeted, _, _ = rates.convert(
            budgeted_native,
            budget.currency,
            reporting_currency,
            active_start,
        )
        budget_conversion_available = budgeted is not None
        if budgeted is None:
            budgeted = Decimal("0")
        progress = spent / budgeted * 100 if budgeted else Decimal("0")
        results.append(
            {
                "name": budget.name,
                "period": budget.get_period_display(),
                "category": budget.category.name if budget.category_id else "All categories",
                "budgeted": budgeted,
                "spent": spent,
                "remaining": budgeted - spent if budget_conversion_available else None,
                "over_amount": (
                    max(spent - budgeted, Decimal("0"))
                    if budget_conversion_available
                    else Decimal("0")
                ),
                "progress": progress,
                "progress_bar": min(max(progress, Decimal("0")), Decimal("100")),
                "over_budget": budget_conversion_available and spent > budgeted,
                "currency": reporting_currency,
                "budget_conversion_available": budget_conversion_available,
                "unconverted_count": sum(missing_currencies.values()),
                "unconverted_currencies": sorted(missing_currencies),
            }
        )
    return sorted(results, key=lambda item: item["progress"], reverse=True)


def build_expense_analytics(user, start_date, end_date, account_id=None, category_id=None):
    months = month_range(start_date, end_date)
    finance_settings = UserFinanceSettings.objects.filter(owner=user).first()
    reporting_currency = (
        finance_settings.reporting_currency if finance_settings else "EUR"
    )
    rates = ExchangeRateBook(user, end_date)
    queryset = Transaction.objects.filter(
        account__owner=user,
        transaction_date__range=(start_date, end_date),
    )
    if account_id:
        queryset = queryset.filter(account_id=account_id)
    if category_id:
        queryset = queryset.filter(category_id=category_id)

    monthly_totals = _empty_months(months)
    monthly_income_totals = _empty_months(months)
    category_data = {}
    subcategory_data = {}
    converted_rows, missing_currencies = _converted_rows(
        queryset, rates, reporting_currency
    )
    income_count = 0
    expense_count = 0
    for transaction, amount in converted_rows:
        month_key = transaction.transaction_date.strftime("%Y-%m")
        if transaction.type == "income":
            income_count += 1
            monthly_income_totals[month_key] += amount
            continue
        if transaction.type != "expense":
            continue
        expense_count += 1
        monthly_totals[month_key] += amount
        category_key = transaction.category_id or "uncategorised"
        category = category_data.setdefault(
            category_key,
            {
                "name": transaction.category.name if transaction.category_id else "Uncategorised",
                "total": Decimal("0"),
                "months": _empty_months(months),
            },
        )
        category["total"] += amount
        category["months"][month_key] += amount

        subcategory_key = transaction.subcategory_id or "uncategorised"
        subcategory = subcategory_data.setdefault(
            subcategory_key,
            {
                "name": (
                    transaction.subcategory.name
                    if transaction.subcategory_id
                    else "Uncategorised"
                ),
                "total": Decimal("0"),
                "months": _empty_months(months),
            },
        )
        subcategory["total"] += amount
        subcategory["months"][month_key] += amount

    total_expenses = sum(monthly_totals.values(), Decimal("0"))
    total_income = sum(monthly_income_totals.values(), Decimal("0"))
    net_cash_flow = total_income - total_expenses
    savings_rate = (
        net_cash_flow / total_income * 100 if total_income else Decimal("0")
    )
    maximum_month = max(monthly_totals.values(), default=Decimal("0"))
    maximum_income_month = max(monthly_income_totals.values(), default=Decimal("0"))
    maximum_flow_month = max(maximum_month, maximum_income_month)
    maximum_category = max(
        (category["total"] for category in category_data.values()),
        default=Decimal("0"),
    )

    def decorate(items, maximum):
        result = []
        pie_total = sum((item["total"] for item in items.values()), Decimal("0"))
        pie_cursor = Decimal("0")
        sorted_items = sorted(
            items.values(), key=lambda value: value["total"], reverse=True
        )
        for index, item in enumerate(sorted_items):
            item["share"] = (item["total"] / total_expenses * 100) if total_expenses else Decimal("0")
            item["bar"] = (item["total"] / maximum * 100) if maximum else Decimal("0")
            item["color"] = PIE_COLORS[index % len(PIE_COLORS)]
            if pie_total:
                pie_end = (
                    Decimal("100")
                    if index == len(sorted_items) - 1
                    else pie_cursor + item["total"] / pie_total * 100
                )
                item["pie_start"] = pie_cursor.quantize(Decimal("0.01"))
                item["pie_end"] = pie_end.quantize(Decimal("0.01"))
                pie_cursor = pie_end
            else:
                item["pie_start"] = Decimal("0")
                item["pie_end"] = Decimal("0")
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

    categories = decorate(category_data, maximum_category)
    subcategories = decorate(subcategory_data, maximum_category)

    def pie_gradient(items):
        visible = [item for item in items if item["total"] > 0]
        if not visible:
            return "conic-gradient(#e2e8f0 0% 100%)"
        return "conic-gradient(" + ", ".join(
            f"{item['color']} {item['pie_start']}% {item['pie_end']}%"
            for item in visible
        ) + ")"

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
        "income_months": [
            {
                "key": month.strftime("%Y-%m"),
                "label": month.strftime("%b %Y"),
                "total": monthly_income_totals[month.strftime("%Y-%m")],
                "bar": (
                    monthly_income_totals[month.strftime("%Y-%m")]
                    / maximum_income_month
                    * 100
                    if maximum_income_month
                    else Decimal("0")
                ),
            }
            for month in months
        ],
        "cash_flow_months": [
            {
                "key": month.strftime("%Y-%m"),
                "label": month.strftime("%b %Y"),
                "income": monthly_income_totals[month.strftime("%Y-%m")],
                "expenses": monthly_totals[month.strftime("%Y-%m")],
                "income_bar": (
                    monthly_income_totals[month.strftime("%Y-%m")]
                    / maximum_flow_month
                    * 100
                    if maximum_flow_month
                    else Decimal("0")
                ),
                "expense_bar": (
                    monthly_totals[month.strftime("%Y-%m")]
                    / maximum_flow_month
                    * 100
                    if maximum_flow_month
                    else Decimal("0")
                ),
                "net": (
                    monthly_income_totals[month.strftime("%Y-%m")]
                    - monthly_totals[month.strftime("%Y-%m")]
                ),
            }
            for month in months
        ],
        "categories": categories,
        "subcategories": subcategories,
        "category_pie_gradient": pie_gradient(categories),
        "subcategory_pie_gradient": pie_gradient(subcategories),
        "total_expenses": total_expenses,
        "total_income": total_income,
        "net_cash_flow": net_cash_flow,
        "savings_rate": savings_rate,
        "transaction_count": expense_count,
        "income_transaction_count": income_count,
        "unconverted_transaction_count": sum(missing_currencies.values()),
        "unconverted_currencies": sorted(missing_currencies),
        "reporting_currency": reporting_currency,
        "average_monthly": total_expenses / len(months) if months else Decimal("0"),
        "period_comparison": _build_period_comparison(
            user,
            account_id,
            category_id,
            start_date,
            end_date,
            total_income,
            total_expenses,
            net_cash_flow,
            rates,
            reporting_currency,
        ),
        "budget_comparison": _build_budget_comparison(
            user,
            start_date,
            end_date,
            account_id,
            category_id,
            rates,
            reporting_currency,
        ),
    }


def _build_period_comparison(
    user,
    account_id,
    category_id,
    start_date,
    end_date,
    total_income,
    total_expenses,
    net_cash_flow,
    rates,
    reporting_currency,
):
    period_length = (end_date - start_date).days + 1
    previous_start = start_date - timedelta(days=period_length)
    previous_end = start_date - timedelta(days=1)
    previous_queryset = Transaction.objects.filter(
        account__owner=user,
        transaction_date__range=(previous_start, previous_end),
    )
    if account_id:
        previous_queryset = previous_queryset.filter(account_id=account_id)
    if category_id:
        previous_queryset = previous_queryset.filter(category_id=category_id)

    previous_rows, missing_currencies = _converted_rows(
        previous_queryset, rates, reporting_currency
    )
    previous_income = sum(
        (amount for transaction, amount in previous_rows if transaction.type == "income"),
        Decimal("0"),
    )
    previous_expenses = sum(
        (amount for transaction, amount in previous_rows if transaction.type == "expense"),
        Decimal("0"),
    )
    previous_net = previous_income - previous_expenses

    def percentage_change(current, previous):
        if not previous:
            return None
        return (current - previous) / abs(previous) * 100

    return {
        "previous_start": previous_start,
        "previous_end": previous_end,
        "previous_income": previous_income,
        "previous_expenses": previous_expenses,
        "previous_net_cash_flow": previous_net,
        "income_change_percent": percentage_change(total_income, previous_income),
        "expense_change_percent": percentage_change(total_expenses, previous_expenses),
        "cash_flow_change_percent": percentage_change(net_cash_flow, previous_net),
        "income_change_available": bool(previous_income),
        "expense_change_available": bool(previous_expenses),
        "cash_flow_change_available": bool(previous_net),
        "unconverted_transaction_count": sum(missing_currencies.values()),
    }
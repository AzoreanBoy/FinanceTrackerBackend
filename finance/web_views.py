import csv
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from io import StringIO
import re
import uuid

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction as db_transaction
from django.db.models import F, Q, Sum
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import (
    ACCOUNT_COLOR_CHOICES,
    ACCOUNT_ICON_CHOICES,
    Account,
    Budget,
    Category,
    Debt,
    DebtRepayment,
    ExchangeRate,
    RecurringTransaction,
    SavingsGoal,
    SubCategory,
    Tag,
    Transaction,
    UserFinanceSettings,
)
from .analytics import (
    budget_cycle_bounds,
    build_expense_analytics,
    pay_cycle_for_date,
    shift_month,
)
from .currencies import ExchangeRateBook
from .importing import preview_transactions_csv
from .recurring import process_due_recurring_transactions


FINANCE_ICON_OPTIONS = (
    ("☕", "Coffee"),
    ("🍽️", "Food"),
    ("🛒", "Groceries"),
    ("🏠", "Home"),
    ("💡", "Utilities"),
    ("🚗", "Car"),
    ("🚌", "Transport"),
    ("🩺", "Health"),
    ("🛍️", "Shopping"),
    ("🎬", "Entertainment"),
    ("✈️", "Travel"),
    ("📚", "Education"),
    ("🐾", "Pets"),
    ("🎁", "Gifts"),
    ("📄", "Bills"),
    ("💼", "Salary"),
    ("🧑‍💻", "Freelance"),
    ("📈", "Investments"),
    ("🏦", "Savings"),
    ("↩️", "Refunds"),
    ("💳", "Other"),
    ("💰", "Income"),
)


def _suggest_finance_icon(name, category_type="expense"):
    normalized = name.casefold()
    suggestions = (
        (("coffee", "cafe", "café"), "☕"),
        (("grocer", "grocery", "supermarket", "mercado", "compras de casa"), "🛒"),
        (("food", "restaurant", "dining", "meal", "comida", "restaurante"), "🍽️"),
        (("home", "rent", "housing", "casa", "renda"), "🏠"),
        (("utilit", "electric", "water", "internet", "utilities", "luz", "água"), "💡"),
        (("transport", "car", "fuel", "gas", "combustível", "transportes"), "🚗"),
        (("health", "medical", "doctor", "saúde", "farmácia"), "🩺"),
        (("shop", "clothing", "shopping", "roupa", "compras"), "🛍️"),
        (("entertain", "movie", "game", "leisure", "lazer", "cinema"), "🎬"),
        (("travel", "holiday", "trip", "viagem", "férias"), "✈️"),
        (("education", "school", "course", "educação", "escola"), "📚"),
        (("pet", "vet", "animal", "animal de estimação"), "🐾"),
        (("gift", "donation", "presente", "doação"), "🎁"),
        (("bill", "insurance", "tax", "conta", "seguro", "imposto"), "📄"),
        (("salary", "wage", "paycheck", "salário", "ordenado"), "💼"),
        (("freelance", "business", "side hustle", "negócio"), "🧑‍💻"),
        (("invest", "dividend", "investment", "investimento"), "📈"),
        (("saving", "savings", "poupança"), "🏦"),
        (("refund", "reimburse", "reembolso"), "↩️"),
    )
    for keywords, icon in suggestions:
        if any(keyword in normalized for keyword in keywords):
            return icon
    return "💰" if category_type == "income" else "💳"


def _is_finance_emoji(icon):
    return any(icon == option[0] for option in FINANCE_ICON_OPTIONS)


def service_worker(request):
    worker_file = settings.BASE_DIR / "static" / "service-worker.js"
    response = HttpResponse(
        worker_file.read_text(encoding="utf-8"),
        content_type="application/javascript",
    )
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


@login_required
def dashboard(request):
    try:
        as_of_date = date.fromisoformat(request.GET.get("as_of", ""))
    except ValueError:
        as_of_date = timezone.localdate()

    finance_settings, _ = UserFinanceSettings.objects.get_or_create(
        owner=request.user
    )
    reporting_currency = finance_settings.reporting_currency
    rates = ExchangeRateBook(request.user, as_of_date)
    accounts = Account.objects.filter(owner=request.user).order_by("name")
    transactions = (
        Transaction.objects.filter(account__owner=request.user)
        .filter(transaction_date__lte=as_of_date)
        .select_related("account", "category")
        .order_by("-transaction_date", "-created_at")
    )
    savings_goals = SavingsGoal.objects.filter(account__owner=request.user).select_related(
        "account"
    )
    category_totals = {}
    subcategory_totals = {}
    income = Decimal("0")
    expenses = Decimal("0")
    unconverted_currencies = set()
    for item in transactions:
        converted, _, _ = rates.convert(
            item.amount,
            item.account.currency,
            reporting_currency,
            item.transaction_date,
        )
        if converted is None:
            unconverted_currencies.add(item.account.currency)
            continue
        if item.type == "income":
            income += converted
        elif item.type == "expense":
            expenses += converted
            category_name = item.category.name if item.category_id else "Uncategorised"
            subcategory_name = (
                item.subcategory.name if item.subcategory_id else "Uncategorised"
            )
            category_totals[category_name] = (
                category_totals.get(category_name, Decimal("0")) + converted
            )
            subcategory_totals[subcategory_name] = (
                subcategory_totals.get(subcategory_name, Decimal("0")) + converted
            )
    category_expenses = [
        {"category_name": name, "total": total}
        for name, total in sorted(
            category_totals.items(), key=lambda pair: pair[1], reverse=True
        )[:6]
    ]
    subcategory_expenses = [
        {"subcategory_name": name, "total": total}
        for name, total in sorted(
            subcategory_totals.items(), key=lambda pair: pair[1], reverse=True
        )[:8]
    ]
    total_flow = income + expenses
    income_share = (income / total_flow * 100) if total_flow else Decimal("0")
    expense_share = (expenses / total_flow * 100) if total_flow else Decimal("0")
    recent_transactions = []
    for item in transactions[:6]:
        category = item.category
        if category:
            icon = category.icon or _suggest_finance_icon(category.name, item.type)
        else:
            icon = _suggest_finance_icon(item.title or "", item.type)
        recent_transactions.append(
            {
                "type": item.type,
                "title": item.title,
                "category": category,
                "account": item.account,
                "transaction_date": item.transaction_date,
                "amount": item.amount,
                "category_display_icon": icon,
                "category_icon_is_emoji": _is_finance_emoji(icon),
            }
        )

    unknown_balance_account_count = 0
    unconverted_account_count = 0
    for account in accounts:
        if as_of_date == timezone.localdate():
            account.display_balance = account.balance
            account.balance_history_available = True
        elif (
            account.opening_balance is not None
            and account.opening_balance_date
            and as_of_date >= account.opening_balance_date
        ):
            event_start = account.opening_balance_date
            transactions_after_open = account.transactions.filter(
                transaction_date__gt=event_start,
                transaction_date__lte=as_of_date,
            )
            transaction_net = sum(
                (
                    item.amount if item.type == "income" else -item.amount
                    for item in transactions_after_open
                ),
                Decimal("0"),
            )
            corrections = account.balance_corrections.filter(
                transaction_date__gt=event_start,
                transaction_date__lte=as_of_date,
            )
            correction_total = sum(
                (item.amount for item in corrections), Decimal("0")
            )
            outgoing = account.outgoing_transfers.filter(
                transaction_date__gt=event_start,
                transaction_date__lte=as_of_date,
            )
            incoming = account.incoming_transfers.filter(
                transaction_date__gt=event_start,
                transaction_date__lte=as_of_date,
            )
            transfer_net = sum(
                (item.destination_amount or item.amount for item in incoming),
                Decimal("0"),
            ) - sum((item.amount for item in outgoing), Decimal("0"))
            account.display_balance = (
                account.opening_balance
                + transaction_net
                + correction_total
                + transfer_net
            )
            account.balance_history_available = True
        else:
            account.display_balance = None
            account.balance_history_available = False
            unknown_balance_account_count += 1
        if account.display_balance is None:
            account.reporting_balance = None
        else:
            account.reporting_balance, _, _ = rates.convert(
                account.display_balance,
                account.currency,
                reporting_currency,
                as_of_date,
            )
            if account.reporting_balance is None:
                unconverted_account_count += 1

    context = {
        "accounts": accounts,
        "recent_transactions": recent_transactions,
        "savings_goals": savings_goals[:3],
        "category_expenses": category_expenses,
        "subcategory_expenses": subcategory_expenses,
        "total_balance": sum(
            (
                account.reporting_balance
                for account in accounts
                if account.reporting_balance is not None
            ),
            Decimal("0"),
        ),
        "reporting_currency": reporting_currency,
        "unconverted_currencies": sorted(unconverted_currencies),
        "unconverted_account_count": unconverted_account_count,
        "unknown_balance_account_count": unknown_balance_account_count,
        "income": income,
        "expenses": expenses,
        "income_share": income_share,
        "expense_share": expense_share,
        "net_position": income - expenses,
        "transaction_count": transactions.count(),
        "as_of_date": as_of_date,
    }
    return render(request, "finance/dashboard.html", context)


def _transaction_queryset(user):
    return Transaction.objects.filter(account__owner=user).select_related(
        "account", "category", "subcategory"
    ).prefetch_related("tags")


def _transaction_form_context(user):
    categories = Category.objects.filter(owner=user).order_by("name")
    for category in categories:
        category.display_icon = category.icon or _suggest_finance_icon(
            category.name, category.type
        )
        category.icon_is_emoji = _is_finance_emoji(category.display_icon)
    subcategories = (
        SubCategory.objects.filter(
            Q(owner=user) | Q(owner__isnull=True, category__owner=user)
        )
        .select_related("category")
        .order_by("category__name", "name")
    )
    for subcategory in subcategories:
        subcategory.display_icon = subcategory.icon or _suggest_finance_icon(
            subcategory.name, subcategory.category.type
        )
        subcategory.icon_is_emoji = _is_finance_emoji(subcategory.display_icon)

    return {
        "accounts": Account.objects.filter(owner=user).order_by("name"),
        "categories": categories,
        "tags": Tag.objects.filter(owner=user),
        "subcategories": subcategories,
    }


@login_required
def transaction_list(request):
    transactions = _transaction_queryset(request.user)
    filters = {
        "start": request.GET.get("start", ""),
        "end": request.GET.get("end", ""),
        "type": request.GET.get("type", ""),
        "account": request.GET.get("account", ""),
        "category": request.GET.get("category", ""),
        "currency": request.GET.get("currency", "").upper(),
        "minimum": request.GET.get("minimum", ""),
        "maximum": request.GET.get("maximum", ""),
        "q": request.GET.get("q", "").strip(),
        "tag": request.GET.get("tag", ""),
    }
    for parameter, lookup in (("start", "transaction_date__gte"), ("end", "transaction_date__lte")):
        if filters[parameter]:
            try:
                transactions = transactions.filter(
                    **{lookup: date.fromisoformat(filters[parameter])}
                )
            except ValueError:
                messages.error(request, f"Enter a valid {parameter} date.")
                filters[parameter] = ""
    if filters["start"] and filters["end"]:
        if date.fromisoformat(filters["start"]) > date.fromisoformat(filters["end"]):
            messages.error(request, "The start date must be on or before the end date.")
            transactions = transactions.none()
    if filters["type"] in {"income", "expense"}:
        transactions = transactions.filter(type=filters["type"])
    if filters["account"]:
        transactions = transactions.filter(
            account__owner=request.user, account_id=filters["account"]
        )
    if filters["category"]:
        transactions = transactions.filter(
            category__owner=request.user, category_id=filters["category"]
        )
    user_currencies = set(
        Account.objects.filter(owner=request.user)
        .values_list("currency", flat=True)
        .distinct()
    )
    if filters["currency"]:
        if filters["currency"] in user_currencies:
            transactions = transactions.filter(account__currency=filters["currency"])
        else:
            messages.error(request, "Choose a currency used by one of your accounts.")
            filters["currency"] = ""
    elif filters["account"]:
        selected_account = Account.objects.filter(
            owner=request.user, pk=filters["account"]
        ).first()
        if selected_account:
            filters["currency"] = selected_account.currency
    if (filters["minimum"] or filters["maximum"]) and not filters["currency"]:
        messages.error(request, "Choose a currency before filtering by amount.")
        filters["minimum"] = ""
        filters["maximum"] = ""
    if filters["tag"]:
        transactions = transactions.filter(
            tags__owner=request.user, tags__pk=filters["tag"]
        ).distinct()
    for parameter, lookup in (("minimum", "amount__gte"), ("maximum", "amount__lte")):
        if filters[parameter]:
            try:
                value = Decimal(filters[parameter])
                if not value.is_finite() or value < 0:
                    raise InvalidOperation
                transactions = transactions.filter(**{lookup: value})
            except InvalidOperation:
                messages.error(request, f"Enter a valid {parameter} amount.")
                filters[parameter] = ""
    if filters["q"]:
        transactions = transactions.filter(
            Q(title__icontains=filters["q"])
            | Q(description__icontains=filters["q"])
            | Q(account__name__icontains=filters["q"])
            | Q(category__name__icontains=filters["q"])
        )

    transactions = transactions.order_by("-transaction_date", "-created_at")
    if request.GET.get("export") == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "transaction_id",
                "date",
                "type",
                "title",
                "description",
                "account",
                "category",
                "subcategory",
                "amount",
                "currency",
            ]
        )
        for item in transactions:
            writer.writerow(
                [
                    item.pk,
                    item.transaction_date.isoformat(),
                    item.type,
                    item.title or "",
                    item.description or "",
                    item.account.name,
                    item.category.name if item.category_id else "",
                    item.subcategory.name if item.subcategory_id else "",
                    item.amount,
                    item.account.currency,
                ]
            )
        response = HttpResponse(output.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="finance-transactions.csv"'
        return response

    transactions = list(transactions)
    for item in transactions:
        if item.category_id:
            icon = item.category.icon or _suggest_finance_icon(
                item.category.name, item.type
            )
        else:
            icon = _suggest_finance_icon(item.title or "", item.type)
        item.category_display_icon = icon
        item.category_icon_is_emoji = _is_finance_emoji(icon)

    income_count = sum(item.type == "income" for item in transactions)
    expense_count = len(transactions) - income_count
    context = _transaction_form_context(request.user)
    context.update(
        {
            "transactions": transactions,
            "transaction_count": len(transactions),
            "income_count": income_count,
            "expense_count": expense_count,
            "filters_applied": any(filters.values()),
            "filters": filters,
            "tags": Tag.objects.filter(owner=request.user),
            "currencies": sorted(user_currencies),
        }
    )
    return render(request, "finance/transactions.html", context)


@login_required
def transaction_create(request):
    return render(
        request,
        "finance/transaction_create.html",
        _transaction_form_context(request.user),
    )


@login_required
def analytics_page(request):
    today = timezone.localdate()
    finance_settings, _ = UserFinanceSettings.objects.get_or_create(
        owner=request.user
    )
    if request.method == "POST" and request.POST.get("action") == "payday":
        try:
            payday_day = int(request.POST.get("payday_day", ""))
            if not 1 <= payday_day <= 31:
                raise ValueError
            finance_settings.payday_day = payday_day
            finance_settings.save(update_fields=["payday_day"])
            messages.success(request, "Payday preference saved.")
        except (TypeError, ValueError):
            messages.error(request, "Choose a payday from 1 to 31.")
        return redirect("finance_web:analytics")

    account_id = request.GET.get("account") or None
    category_id = request.GET.get("category") or None
    period_mode = request.GET.get("period")
    if period_mode not in {"pay_cycle", "custom"}:
        period_mode = (
            "custom" if "start" in request.GET or "end" in request.GET else "pay_cycle"
        )

    cycle_start = cycle_end = previous_cycle_start = next_cycle_start = None
    if period_mode == "pay_cycle":
        current_cycle_start, _, _ = pay_cycle_for_date(
            today, finance_settings.payday_day
        )
        try:
            requested_cycle_start = date.fromisoformat(
                request.GET.get("cycle_start", "")
            )
            requested_start, _, _ = pay_cycle_for_date(
                requested_cycle_start, finance_settings.payday_day
            )
            cycle_start = (
                requested_cycle_start
                if requested_start == requested_cycle_start
                and requested_cycle_start <= today
                else current_cycle_start
            )
        except ValueError:
            cycle_start = current_cycle_start
        cycle_start, cycle_end, next_cycle_start = pay_cycle_for_date(
            cycle_start, finance_settings.payday_day
        )
        previous_cycle_start, _, _ = pay_cycle_for_date(
            cycle_start - timedelta(days=1), finance_settings.payday_day
        )
        start_date = cycle_start
        end_date = min(cycle_end, today) if cycle_start == current_cycle_start else cycle_end
    else:
        default_start = shift_month(today.replace(day=1), -5)
        try:
            start_date = date.fromisoformat(request.GET.get("start", ""))
        except ValueError:
            start_date = default_start
        try:
            end_date = date.fromisoformat(request.GET.get("end", ""))
        except ValueError:
            end_date = today
        if start_date > end_date:
            start_date, end_date = end_date, start_date

    analytics = build_expense_analytics(
        request.user,
        start_date,
        end_date,
        account_id=account_id,
        category_id=category_id,
    )
    return render(
        request,
        "finance/analytics.html",
        {
            **analytics,
            "start_date": start_date,
            "end_date": end_date,
            "accounts": Account.objects.filter(owner=request.user).order_by("name"),
            "category_options": Category.objects.filter(owner=request.user).order_by("name"),
            "selected_account": account_id or "",
            "selected_category": category_id or "",
            "period_mode": period_mode,
            "payday_day": finance_settings.payday_day,
            "cycle_start": cycle_start,
            "cycle_end": cycle_end,
            "previous_cycle_start": previous_cycle_start,
            "next_cycle_start": next_cycle_start,
            "current_cycle_start": (
                pay_cycle_for_date(today, finance_settings.payday_day)[0]
                if period_mode == "pay_cycle"
                else None
            ),
        },
    )


@login_required
def budgets_page(request):
    finance_settings, _ = UserFinanceSettings.objects.get_or_create(
        owner=request.user
    )
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "delete":
            budget = get_object_or_404(
                Budget, pk=request.POST.get("budget_id"), owner=request.user
            )
            budget.delete()
            messages.success(request, "Budget deleted. Transactions were not changed.")
            return redirect("finance_web:budgets")
        try:
            amount = Decimal(request.POST.get("amount", "0"))
            name = request.POST.get("name", "").strip()
            currency = request.POST.get(
                "currency", finance_settings.reporting_currency
            ).upper()
            category_id = request.POST.get("category") or None
            category = Category.objects.filter(owner=request.user, pk=category_id).first()
            period = request.POST.get("period", "monthly")
            start_date = date.fromisoformat(
                request.POST.get("start_date") or timezone.localdate().isoformat()
            )
            end_date = (
                date.fromisoformat(request.POST["end_date"])
                if request.POST.get("end_date")
                else None
            )
            if (
                not name
                or len(name) > 100
                or not amount.is_finite()
                or amount <= 0
                or amount.adjusted() > 9
                or amount.as_tuple().exponent < -2
                or not re.fullmatch(r"[A-Z]{3}", currency)
                or period not in {"custom", "weekly", "monthly", "yearly"}
                or (category_id and category is None)
                or (end_date and end_date < start_date)
            ):
                raise ValueError
            if action == "update":
                budget = get_object_or_404(
                    Budget, pk=request.POST.get("budget_id"), owner=request.user
                )
                budget.name = name
                budget.amount = amount
                budget.currency = currency
                budget.period = period
                budget.start_date = start_date
                budget.end_date = end_date
                budget.category = category
                budget.save(
                    update_fields=[
                        "name",
                        "amount",
                        "currency",
                        "period",
                        "start_date",
                        "end_date",
                        "category",
                    ]
                )
                messages.success(request, "Budget updated.")
            elif action == "create":
                Budget.objects.create(
                    owner=request.user,
                    name=name,
                    amount=amount,
                    currency=currency,
                    period=period,
                    start_date=start_date,
                    end_date=end_date,
                    category=category,
                )
                messages.success(request, "Budget created.")
            else:
                messages.error(request, "Choose a valid budget action.")
        except (InvalidOperation, ValueError):
            messages.error(request, "Enter a valid budget name and amount.")
        return redirect("finance_web:budgets")

    budgets = Budget.objects.filter(owner=request.user).select_related("category")
    today = timezone.localdate()
    rates = ExchangeRateBook(request.user, today)
    for budget in budgets:
        period_start, period_end, cycle_amount = budget_cycle_bounds(budget, today)
        budget.period_start = period_start
        budget.period_end = period_end
        budget.cycle_amount = cycle_amount
        spend_end = min(period_end, today)
        expenses = Transaction.objects.filter(
            account__owner=request.user,
            type="expense",
            transaction_date__range=(period_start, spend_end),
        ).select_related("account")
        if budget.category_id:
            expenses = expenses.filter(category_id=budget.category_id)
        budget.spent = Decimal("0")
        budget.unconverted_currencies = set()
        for expense in expenses:
            converted, _, _ = rates.convert(
                expense.amount,
                expense.account.currency,
                budget.currency,
                expense.transaction_date,
            )
            if converted is None:
                budget.unconverted_currencies.add(expense.account.currency)
            else:
                budget.spent += converted
        budget.remaining = cycle_amount - budget.spent
        budget.progress = (
            min((budget.spent / cycle_amount * 100), Decimal("100"))
            if cycle_amount
            else Decimal("0")
        )
        budget.unconverted_currencies = sorted(budget.unconverted_currencies)
    return render(
        request,
        "finance/budgets.html",
        {
            "budgets": budgets,
            "categories": Category.objects.filter(owner=request.user).order_by("name"),
            "today": today,
            "reporting_currency": finance_settings.reporting_currency,
        },
    )


@login_required
def recurring_page(request):
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "process_due":
            created = process_due_recurring_transactions(
                user=request.user,
                through_date=timezone.localdate(),
            )
            messages.success(
                request,
                f"Created {created} due recurring transaction(s).",
            )
            return redirect("finance_web:recurring")
        if action == "delete":
            item = get_object_or_404(
                RecurringTransaction,
                pk=request.POST.get("recurring_id"),
                account__owner=request.user,
            )
            item.delete()
            messages.success(
                request,
                "Recurring item deleted. Transactions already created were not changed.",
            )
            return redirect("finance_web:recurring")
        try:
            amount = Decimal(request.POST.get("amount", "0"))
            account = Account.objects.get(pk=request.POST.get("account"), owner=request.user)
            frequency = request.POST.get("frequency", "monthly")
            transaction_type = request.POST.get("type", "expense")
            title = request.POST.get("title", "").strip()
            category_id = request.POST.get("category") or None
            category = Category.objects.filter(
                owner=request.user, pk=category_id
            ).first()
            next_date = date.fromisoformat(
                request.POST.get("next_date") or timezone.localdate().isoformat()
            )
            end_date = (
                date.fromisoformat(request.POST["end_date"])
                if request.POST.get("end_date")
                else None
            )
            if (
                not amount.is_finite()
                or amount <= 0
                or amount.adjusted() > 9
                or amount.as_tuple().exponent < -2
                or not title
                or len(title) > 100
                or frequency not in {"weekly", "monthly", "yearly"}
                or transaction_type not in {"income", "expense"}
                or (category_id and category is None)
                or (end_date and end_date < next_date)
            ):
                raise ValueError
            if action == "update":
                item = get_object_or_404(
                    RecurringTransaction,
                    pk=request.POST.get("recurring_id"),
                    account__owner=request.user,
                )
                item.account = account
                item.amount = amount
                item.type = transaction_type
                item.title = title
                category_changed = item.category_id != (
                    category.pk if category else None
                )
                item.category = category
                if category_changed:
                    item.subcategory = None
                item.frequency = frequency
                item.next_date = next_date
                item.end_date = end_date
                item.schedule_day = next_date.day
                item.active = request.POST.get("active") == "on"
                item.save(
                    update_fields=[
                        "account",
                        "amount",
                        "type",
                        "title",
                        "category",
                        "subcategory",
                        "frequency",
                        "next_date",
                        "end_date",
                        "active",
                        "schedule_day",
                    ]
                )
                messages.success(request, "Recurring transaction updated.")
            elif action == "create":
                RecurringTransaction.objects.create(
                    account=account,
                    amount=amount,
                    type=transaction_type,
                    title=title,
                    category=category,
                    frequency=frequency,
                    next_date=next_date,
                )
                messages.success(request, "Recurring transaction created.")
            else:
                messages.error(request, "Choose a valid recurring transaction action.")
        except (Account.DoesNotExist, InvalidOperation, ValueError):
            messages.error(request, "Check the recurring transaction values.")
        return redirect("finance_web:recurring")

    return render(
        request,
        "finance/recurring.html",
        {
            "recurring_transactions": RecurringTransaction.objects.filter(
                account__owner=request.user
            ).select_related("account", "category"),
            "accounts": Account.objects.filter(owner=request.user).order_by("name"),
            "categories": Category.objects.filter(owner=request.user).order_by("name"),
        },
    )


@login_required
def accounts_page(request):
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "delete":
            account_id = request.POST.get("account_id", "")
            if not account_id.isdecimal():
                messages.error(request, "Choose a valid account to delete.")
                return redirect("finance_web:accounts")
            account = get_object_or_404(
                Account, pk=int(account_id), owner=request.user
            )
            if not _account_is_deletable(account):
                messages.error(
                    request,
                    "This account has a balance, history or linked financial records. "
                    "To protect that data, only unused empty accounts can be deleted.",
                )
            else:
                account.delete()
                messages.success(request, "Empty account deleted.")
            return redirect("finance_web:accounts")
        if action == "update":
            account_id = request.POST.get("account_id", "")
            if not account_id.isdecimal():
                messages.error(request, "Choose a valid account to update.")
                return redirect("finance_web:accounts")
            account = get_object_or_404(
                Account, pk=int(account_id), owner=request.user
            )
            name = request.POST.get("name", "").strip()
            currency = request.POST.get("currency", "").upper()
            color = request.POST.get("color", "")
            icon = request.POST.get("icon", "")
            currency_locked = not _account_currency_is_editable(account)
            if (
                not name
                or len(name) > 100
                or not re.fullmatch(r"[A-Z]{3}", currency)
                or color not in dict(ACCOUNT_COLOR_CHOICES)
                or icon not in dict(ACCOUNT_ICON_CHOICES)
            ):
                messages.error(request, "Enter a valid account name, currency, color and icon.")
            elif currency_locked and currency != account.currency:
                messages.error(
                    request,
                    "Currency cannot be changed after this account has a balance or financial activity. "
                    "Existing amounts are never converted automatically.",
                )
            else:
                account.name = name
                account.currency = currency
                account.color = color
                account.icon = icon
                account.save(update_fields=["name", "currency", "color", "icon", "updated_at"])
                messages.success(request, "Account details updated.")
            return redirect("finance_web:accounts")

        name = request.POST.get("name", "").strip()
        try:
            balance = Decimal(request.POST.get("balance", "0"))
            opening_balance_date = request.POST.get("opening_balance_date") or None
            currency = request.POST.get("currency", "EUR").upper()
            color = request.POST.get("color", "#E88B72")
            icon = request.POST.get("icon", "🏦")
            if (
                not name
                or len(name) > 100
                or not balance.is_finite()
                or balance < 0
                or not re.fullmatch(r"[A-Z]{3}", currency)
                or color not in dict(ACCOUNT_COLOR_CHOICES)
                or icon not in dict(ACCOUNT_ICON_CHOICES)
            ):
                raise ValueError
            if opening_balance_date:
                opening_balance_date = date.fromisoformat(opening_balance_date)
                if opening_balance_date > timezone.localdate():
                    raise ValueError
            Account.objects.create(
                owner=request.user,
                name=name,
                balance=balance,
                currency=currency,
                color=color,
                icon=icon,
                opening_balance=balance if opening_balance_date else None,
                opening_balance_date=opening_balance_date,
            )
            messages.success(request, "Account created.")
        except (InvalidOperation, ValueError):
            messages.error(request, "Enter a name and a valid non-negative balance.")
        return redirect("finance_web:accounts")

    accounts = Account.objects.filter(owner=request.user).order_by("name")
    for account in accounts:
        account.currency_editable = _account_currency_is_editable(account)
        account.deletable = _account_is_deletable(account)
    return render(
        request,
        "finance/accounts.html",
        {
            "accounts": accounts,
            "account_colors": ACCOUNT_COLOR_CHOICES,
            "account_icons": ACCOUNT_ICON_CHOICES,
        },
    )


def _account_currency_is_editable(account):
    return not (
        account.balance != 0
        or account.opening_balance is not None
        or account.transactions.exists()
        or account.balance_corrections.exists()
        or account.outgoing_transfers.exists()
        or account.incoming_transfers.exists()
        or account.recurring_transactions.exists()
        or account.savings_goals.exists()
    )


def _account_is_deletable(account):
    return (
        account.balance == 0
        and account.opening_balance is None
        and account.opening_balance_date is None
        and not account.transactions.exists()
        and not account.balance_corrections.exists()
        and not account.outgoing_transfers.exists()
        and not account.incoming_transfers.exists()
        and not account.recurring_transactions.exists()
        and not account.savings_goals.exists()
    )


@login_required
def accounts_details(request, account_id):
    account = get_object_or_404(Account, pk=account_id, owner=request.user)
    if request.method == "POST":
        try:
            opening_balance = Decimal(request.POST.get("opening_balance", ""))
            opening_balance_date = date.fromisoformat(
                request.POST.get("opening_balance_date", "")
            )
            if opening_balance_date > timezone.localdate():
                raise ValueError
            account.opening_balance = opening_balance
            account.opening_balance_date = opening_balance_date
            account.save(update_fields=["opening_balance", "opening_balance_date"])
            messages.success(request, "Dated opening balance saved.")
        except (InvalidOperation, TypeError, ValueError):
            messages.error(request, "Enter a valid opening balance and a date that is not in the future.")
        return redirect("finance_web:accounts_details", account_id=account.pk)

    history = []
    if account.opening_balance is not None and account.opening_balance_date:
        history.append(
            {
                "date": account.opening_balance_date,
                "description": "Opening balance",
                "change": None,
                "balance": account.opening_balance,
            }
        )
        events = []
        for item in account.transactions.filter(
            transaction_date__gt=account.opening_balance_date
        ):
            amount = item.amount if item.type == "income" else -item.amount
            events.append((item.transaction_date, item.created_at, item.title, amount))
        for item in account.balance_corrections.filter(
            transaction_date__gt=account.opening_balance_date
        ):
            events.append(
                (item.transaction_date, item.created_at, item.description or "Balance adjustment", item.amount)
            )
        for item in account.outgoing_transfers.filter(
            transaction_date__gt=account.opening_balance_date
        ):
            events.append(
                (item.transaction_date, item.created_at, f"Transfer to {item.to_account.name}", -item.amount)
            )
        for item in account.incoming_transfers.filter(
            transaction_date__gt=account.opening_balance_date
        ):
            events.append(
                (
                    item.transaction_date,
                    item.created_at,
                    f"Transfer from {item.from_account.name}",
                    item.destination_amount or item.amount,
                )
            )

        balance = account.opening_balance
        events_by_date = {}
        for event_date, created_at, description, amount in sorted(events):
            balance += amount
            events_by_date.setdefault(event_date, []).append(
                {
                    "date": event_date,
                    "description": description,
                    "change": amount,
                    "balance": balance,
                }
            )
        for event_rows in events_by_date.values():
            history.extend(event_rows)

    return render(
        request,
        "finance/account_page.html",
        {
            "account": account,
            "history": history,
            "has_balance_history": bool(history),
        },
    )

@login_required
def categories_page(request):
    from .models import Category, SubCategory

    if request.method == "POST":
        action = request.POST.get("action")
        name = request.POST.get("name", "").strip()
        icon = request.POST.get("icon", "").strip()
        if action in {"delete_category", "delete_subcategory"}:
            if action == "delete_category":
                category = get_object_or_404(
                    Category, pk=request.POST.get("category_id"), owner=request.user
                )
                category.delete()
                messages.success(
                    request,
                    "Category deleted. Its transactions remain, but are now uncategorised; associated subcategories and category budget limits were removed.",
                )
            else:
                subcategory = get_object_or_404(
                    SubCategory.objects.select_related("category"),
                    pk=request.POST.get("subcategory_id"),
                    category__owner=request.user,
                )
                subcategory.delete()
                messages.success(
                    request,
                    "Subcategory deleted. Transactions keep their parent category.",
                )
            return redirect("finance_web:categories")

        if action == "update_category":
            category = get_object_or_404(
                Category, pk=request.POST.get("category_id"), owner=request.user
            )
            category_type = request.POST.get("type", "expense")
            if not name or len(name) > 100:
                messages.error(request, "A category name is required.")
            elif category_type not in {"expense", "income"}:
                messages.error(request, "Choose expense or income for the category.")
            elif icon and not _is_finance_emoji(icon):
                messages.error(request, "Choose an icon from the available list.")
            else:
                category.name = name
                category.type = category_type
                category.icon = icon or _suggest_finance_icon(name, category_type)
                category.save(update_fields=["name", "type", "icon"])
                messages.success(request, "Category updated.")
            return redirect("finance_web:categories")

        if action == "update_subcategory":
            subcategory = get_object_or_404(
                SubCategory.objects.select_related("category"),
                pk=request.POST.get("subcategory_id"),
                category__owner=request.user,
            )
            category = get_object_or_404(
                Category, pk=request.POST.get("category"), owner=request.user
            )
            if not name:
                messages.error(request, "A subcategory name is required.")
            elif icon and not _is_finance_emoji(icon):
                messages.error(request, "Choose an icon from the available list.")
            else:
                with db_transaction.atomic():
                    subcategory.name = name
                    subcategory.category = category
                    subcategory.icon = icon or _suggest_finance_icon(
                        name, category.type
                    )
                    subcategory.owner = request.user
                    subcategory.save(
                        update_fields=["name", "category", "icon", "owner"]
                    )
                    Transaction.objects.filter(subcategory=subcategory).update(
                        category=category
                    )
                    RecurringTransaction.objects.filter(
                        subcategory=subcategory
                    ).update(category=category)
                messages.success(request, "Subcategory updated.")
            return redirect("finance_web:categories")

        if action not in {"category", "subcategory"}:
            messages.error(request, "Choose a valid category management action.")
            return redirect("finance_web:categories")

        if not name:
            messages.error(request, "A name is required.")
        elif icon and not _is_finance_emoji(icon):
            messages.error(request, "Choose an icon from the available list.")
        elif action == "category":
            category_type = request.POST.get("type", "expense")
            if category_type not in {"expense", "income"}:
                messages.error(request, "Choose expense or income for the category.")
                return redirect("finance_web:categories")
            Category.objects.create(
                owner=request.user,
                name=name,
                type=category_type,
                icon=icon or _suggest_finance_icon(name, category_type),
            )
            messages.success(request, "Category created.")
        elif action == "subcategory":
            category = get_object_or_404(
                Category, pk=request.POST.get("category"), owner=request.user
            )
            SubCategory.objects.create(
                owner=request.user,
                name=name,
                category=category,
                icon=icon or _suggest_finance_icon(name, category.type),
            )
            messages.success(request, "Subcategory created.")
        return redirect("finance_web:categories")

    categories = Category.objects.filter(owner=request.user).prefetch_related("subcategories").order_by("name")
    emoji_options = {option[0] for option in FINANCE_ICON_OPTIONS}
    for category in categories:
        category.display_icon = category.icon or _suggest_finance_icon(
            category.name, category.type
        )
        category.icon_is_emoji = category.display_icon in emoji_options
        for subcategory in category.subcategories.all():
            subcategory.display_icon = subcategory.icon or _suggest_finance_icon(
                subcategory.name, category.type
            )
            subcategory.icon_is_emoji = subcategory.display_icon in emoji_options
    return render(
        request,
        "finance/categories.html",
        {
            "categories": categories,
            "icon_options": FINANCE_ICON_OPTIONS,
        },
    )


@login_required
def goals_page(request):
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "delete":
            goal = get_object_or_404(
                SavingsGoal, pk=request.POST.get("goal_id"), account__owner=request.user
            )
            goal.delete()
            messages.success(request, "Savings goal deleted. Account balances were not changed.")
            return redirect("finance_web:goals")
        name = request.POST.get("name", "").strip()
        try:
            target_amount = Decimal(request.POST.get("target_amount", "0"))
            account = get_object_or_404(
                Account, pk=request.POST.get("account"), owner=request.user
            )
            if (
                not name
                or len(name) > 100
                or not target_amount.is_finite()
                or target_amount <= 0
                or target_amount.adjusted() > 9
                or target_amount.as_tuple().exponent < -2
            ):
                raise ValueError
            if action == "update":
                goal = get_object_or_404(
                    SavingsGoal, pk=request.POST.get("goal_id"), account__owner=request.user
                )
                goal.name = name
                goal.target_amount = target_amount
                goal.account = account
                goal.save(update_fields=["name", "target_amount", "account"])
                messages.success(request, "Savings goal updated.")
            elif action == "create":
                SavingsGoal.objects.create(
                    name=name,
                    target_amount=target_amount,
                    account=account,
                )
                messages.success(request, "Savings goal created.")
            else:
                messages.error(request, "Choose a valid savings goal action.")
        except (InvalidOperation, ValueError):
            messages.error(request, "Enter a name and a valid target amount.")
        return redirect("finance_web:goals")

    goals = SavingsGoal.objects.filter(account__owner=request.user).select_related("account")
    accounts = Account.objects.filter(owner=request.user).order_by("name")
    return render(request, "finance/goals.html", {"goals": goals, "accounts": accounts})


@login_required
def tags_page(request):
    if request.method == "POST":
        action = request.POST.get("action", "create")
        if action == "delete":
            tag = get_object_or_404(
                Tag, pk=request.POST.get("tag_id"), owner=request.user
            )
            tag.delete()
            messages.success(
                request,
                "Tag deleted. Transactions remain; only their tag association was removed.",
            )
            return redirect("finance_web:tags")
        name = request.POST.get("name", "").strip()
        color = request.POST.get("color", "#2f8f9d")
        if not name or len(name) > 40:
            messages.error(request, "A tag name is required.")
        elif not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            messages.error(request, "Choose a valid hex color.")
        else:
            try:
                if action == "update":
                    tag = get_object_or_404(
                        Tag, pk=request.POST.get("tag_id"), owner=request.user
                    )
                    tag.name = name
                    tag.color = color
                    tag.save(update_fields=["name", "color"])
                    messages.success(request, "Tag updated.")
                elif action == "create":
                    Tag.objects.create(owner=request.user, name=name, color=color)
                    messages.success(request, "Tag created.")
                else:
                    messages.error(request, "Choose a valid tag action.")
            except IntegrityError:
                messages.error(request, "You already have a tag with that name.")
        return redirect("finance_web:tags")
    return render(
        request,
        "finance/tags.html",
        {"tags": Tag.objects.filter(owner=request.user)},
    )


@login_required
def currencies_page(request):
    settings, _ = UserFinanceSettings.objects.get_or_create(owner=request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete_rate":
            rate = get_object_or_404(
                ExchangeRate, pk=request.POST.get("rate_id"), owner=request.user
            )
            rate.delete()
            messages.success(
                request,
                "Exchange rate deleted. Reports will no longer use this dated rate.",
            )
        elif action == "settings":
            currency = request.POST.get("reporting_currency", "").upper()
            if not re.fullmatch(r"[A-Z]{3}", currency):
                messages.error(request, "Enter a valid three-letter reporting currency code.")
            else:
                settings.reporting_currency = currency
                settings.save(update_fields=["reporting_currency"])
                messages.success(request, "Reporting currency updated.")
        elif action == "rate":
            from_currency = request.POST.get("from_currency", "").upper()
            to_currency = request.POST.get("to_currency", "").upper()
            try:
                rate = Decimal(request.POST.get("rate", ""))
                effective_date = date.fromisoformat(request.POST.get("effective_date", ""))
                source = request.POST.get("source", "User entered").strip()[:100]
                if (
                    not re.fullmatch(r"[A-Z]{3}", from_currency)
                    or not re.fullmatch(r"[A-Z]{3}", to_currency)
                    or from_currency == to_currency
                    or not rate.is_finite()
                    or rate <= 0
                    or rate.adjusted() > 9
                    or rate.as_tuple().exponent < -8
                ):
                    raise ValueError
                ExchangeRate.objects.update_or_create(
                    owner=request.user,
                    from_currency=from_currency,
                    to_currency=to_currency,
                    effective_date=effective_date,
                    defaults={"rate": rate, "source": source or "User entered"},
                )
                messages.success(request, "Dated exchange rate saved.")
            except (InvalidOperation, TypeError, ValueError):
                messages.error(request, "Enter valid currencies, a positive rate and an effective date.")
        return redirect("finance_web:currencies")

    return render(
        request,
        "finance/currencies.html",
        {
            "settings": settings,
            "rates": ExchangeRate.objects.filter(owner=request.user)[:100],
            "accounts": Account.objects.filter(owner=request.user).order_by("name"),
        },
    )


@login_required
def csv_import_page(request):
    session_key = "pending_finance_csv_import"
    preview = request.session.get(session_key)
    if request.method == "POST" and request.POST.get("action") == "preview":
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            messages.error(request, "Choose a CSV file to preview.")
        else:
            try:
                rows = preview_transactions_csv(request.user, uploaded_file)
                batch_id = uuid.uuid4().hex
                request.session[session_key] = {
                    "batch_id": batch_id,
                    "rows": rows,
                    "valid_count": sum(not row["errors"] for row in rows),
                    "rejected_count": sum(bool(row["errors"]) for row in rows),
                }
                request.session.modified = True
                preview = request.session[session_key]
                messages.success(request, "Preview ready. Review valid and rejected rows before confirming.")
            except (ValueError, csv.Error) as exc:
                messages.error(request, str(exc))
                preview = None
    elif request.method == "POST" and request.POST.get("action") == "confirm":
        pending = request.session.get(session_key)
        if not pending or request.POST.get("batch_id") != pending.get("batch_id"):
            messages.error(request, "This import preview has expired. Upload the file again.")
            preview = None
        else:
            valid_rows = [row for row in pending["rows"] if not row["errors"]]
            try:
                with db_transaction.atomic():
                    for row in valid_rows:
                        account = Account.objects.get(
                            owner=request.user, pk=row["account_id"]
                        )
                        category = (
                            Category.objects.filter(
                                owner=request.user, pk=row["category_id"]
                            ).first()
                            if row["category_id"]
                            else None
                        )
                        Transaction.objects.create(
                            account=account,
                            amount=Decimal(row["amount"]),
                            type=row["type"],
                            title=row["title"],
                            category=category,
                            transaction_date=date.fromisoformat(row["date"]),
                            import_fingerprint=row["fingerprint"],
                        )
            except (Account.DoesNotExist, IntegrityError, ValueError) as exc:
                messages.error(request, f"Import was not completed: {exc}")
                preview = pending
            else:
                request.session.pop(session_key, None)
                messages.success(request, f"Imported {len(valid_rows)} transactions.")
                return redirect("finance_web:transactions")
    return render(request, "finance/import_transactions.html", {"preview": preview})


@login_required
def debts_page(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            debt = get_object_or_404(
                Debt, pk=request.POST.get("debt_id"), owner=request.user
            )
            debt.delete()
            messages.success(
                request,
                "Debt record and repayment history deleted. Ledger transactions, if any, remain unchanged.",
            )
        elif action == "create":
            try:
                person = request.POST.get("person", "").strip()
                principal = Decimal(request.POST.get("principal", ""))
                currency = request.POST.get("currency", "").upper()
                opened_on = date.fromisoformat(
                    request.POST.get("opened_on") or timezone.localdate().isoformat()
                )
                due_date = date.fromisoformat(request.POST["due_date"]) if request.POST.get("due_date") else None
                direction = request.POST.get("direction")
                if (
                    not person
                    or len(person) > 100
                    or len(request.POST.get("description", "").strip()) > 200
                    or not principal.is_finite()
                    or principal <= 0
                    or principal.adjusted() > 9
                    or principal.as_tuple().exponent < -2
                    or not re.fullmatch(r"[A-Z]{3}", currency)
                    or direction not in {"lent", "borrowed"}
                    or (due_date and due_date < opened_on)
                ):
                    raise ValueError
                Debt.objects.create(
                    owner=request.user,
                    person=person,
                    description=request.POST.get("description", "").strip(),
                    principal=principal,
                    currency=currency,
                    opened_on=opened_on,
                    due_date=due_date,
                    direction=direction,
                )
                messages.success(request, "Debt record created.")
            except (InvalidOperation, TypeError, ValueError):
                messages.error(request, "Check the person, amount, dates, currency and debt direction.")
        elif action == "update":
            debt = get_object_or_404(
                Debt, pk=request.POST.get("debt_id"), owner=request.user
            )
            try:
                person = request.POST.get("person", "").strip()
                principal = Decimal(request.POST.get("principal", ""))
                currency = request.POST.get("currency", "").upper()
                opened_on = date.fromisoformat(request.POST.get("opened_on", ""))
                due_date = (
                    date.fromisoformat(request.POST["due_date"])
                    if request.POST.get("due_date")
                    else None
                )
                direction = request.POST.get("direction")
                repayments_exist = debt.repayments.exists()
                if (
                    not person
                    or not principal.is_finite()
                    or principal <= 0
                    or principal.adjusted() > 9
                    or principal.as_tuple().exponent < -2
                    or principal < debt.repaid
                    or not re.fullmatch(r"[A-Z]{3}", currency)
                    or direction not in {"lent", "borrowed"}
                    or (due_date and due_date < opened_on)
                    or (
                        repayments_exist
                        and (currency != debt.currency or direction != debt.direction)
                    )
                ):
                    raise ValueError
                debt.person = person
                debt.description = request.POST.get("description", "").strip()
                debt.principal = principal
                debt.currency = currency
                debt.opened_on = opened_on
                debt.due_date = due_date
                debt.direction = direction
                debt.status = "settled" if principal == debt.repaid else "open"
                debt.save(
                    update_fields=[
                        "person",
                        "description",
                        "principal",
                        "currency",
                        "opened_on",
                        "due_date",
                        "direction",
                        "status",
                    ]
                )
                messages.success(request, "Debt record updated.")
            except (InvalidOperation, TypeError, ValueError):
                messages.error(
                    request,
                    "Check the debt details. The principal cannot be below repayments already recorded, "
                    "and currency or direction cannot change after repayments.",
                )
        elif action == "repayment":
            try:
                debt_id = request.POST.get("debt")
                amount = Decimal(request.POST.get("amount", ""))
                repayment_date = date.fromisoformat(
                    request.POST.get("repayment_date") or timezone.localdate().isoformat()
                )
                with db_transaction.atomic():
                    debt = Debt.objects.select_for_update().get(
                        owner=request.user, pk=debt_id
                    )
                    account = None
                    account_id = request.POST.get("account") or None
                    if account_id:
                        account = Account.objects.get(
                            owner=request.user, pk=account_id
                        )
                        if account.currency != debt.currency:
                            raise ValueError(
                                "Repayment account currency must match the debt currency."
                            )
                    outstanding_before = debt.outstanding
                    if (
                        not amount.is_finite()
                        or amount <= 0
                        or amount > outstanding_before
                        or amount.adjusted() > 9
                        or amount.as_tuple().exponent < -2
                    ):
                        raise ValueError(
                            "Repayment must be a valid positive amount no greater than the outstanding balance."
                        )
                    ledger_transaction = None
                    if account:
                        ledger_transaction = Transaction.objects.create(
                            account=account,
                            amount=amount,
                            type="income" if debt.direction == "lent" else "expense",
                            title=f"Debt repayment: {debt.person}",
                            description=request.POST.get("note", "").strip(),
                            transaction_date=repayment_date,
                        )
                    DebtRepayment.objects.create(
                        debt=debt,
                        amount=amount,
                        repayment_date=repayment_date,
                        note=request.POST.get("note", "").strip(),
                        transaction=ledger_transaction,
                    )
                    if amount == outstanding_before:
                        debt.status = "settled"
                        debt.save(update_fields=["status"])
                messages.success(request, "Repayment recorded.")
            except (Debt.DoesNotExist, Account.DoesNotExist, InvalidOperation, TypeError, ValueError) as exc:
                messages.error(request, f"Repayment not recorded: {exc}")
        return redirect("finance_web:debts")

    debts = list(Debt.objects.filter(owner=request.user).prefetch_related("repayments"))
    debt_rows = []
    for debt in debts:
        repaid = sum(
            (repayment.amount for repayment in debt.repayments.all()), Decimal("0")
        )
        outstanding = max(debt.principal - repaid, Decimal("0"))
        debt_rows.append(
            {
                "debt": debt,
                "repaid": repaid,
                "outstanding": outstanding,
                "progress": min(repaid / debt.principal * 100, Decimal("100")),
            }
        )
    return render(
        request,
        "finance/debts.html",
        {
            "debts": debt_rows,
            "open_debts": [debt for debt in debts if debt.status == "open"],
            "accounts": Account.objects.filter(owner=request.user).order_by("name"),
            "today": timezone.localdate(),
        },
    )

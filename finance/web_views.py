from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db.models import F, Q, Sum
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Account, Budget, Category, RecurringTransaction, SavingsGoal, Transaction
from .analytics import build_expense_analytics, shift_month


@login_required
def dashboard(request):
    try:
        as_of_date = date.fromisoformat(request.GET.get("as_of", ""))
    except ValueError:
        as_of_date = timezone.localdate()

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
    expense_transactions = transactions.filter(type="expense")
    category_expenses = list(
        expense_transactions
        .values(category_name=F("category__name"))
        .annotate(total=Sum("amount"))
        .order_by("-total")[:6]
    )
    subcategory_expenses = list(
        expense_transactions
        .values(subcategory_name=F("subcategory__name"))
        .annotate(total=Sum("amount"))
        .order_by("-total")[:8]
    )

    income = sum(
        (transaction.amount for transaction in transactions if transaction.type == "income"),
        Decimal("0"),
    )
    expenses = sum(
        (transaction.amount for transaction in transactions if transaction.type == "expense"),
        Decimal("0"),
    )
    total_flow = income + expenses
    income_share = (income / total_flow * 100) if total_flow else Decimal("0")
    expense_share = (expenses / total_flow * 100) if total_flow else Decimal("0")

    for account in accounts:
        all_transactions = Transaction.objects.filter(account=account)
        dated_transactions = all_transactions.filter(transaction_date__lte=as_of_date)
        all_transaction_net = sum(
            (
                item.amount if item.type == "income" else -item.amount
                for item in all_transactions
            ),
            Decimal("0"),
        )
        dated_transaction_net = sum(
            (
                item.amount if item.type == "income" else -item.amount
                for item in dated_transactions
            ),
            Decimal("0"),
        )
        all_corrections = account.balance_corrections.all()
        dated_corrections = all_corrections.filter(transaction_date__lte=as_of_date)
        all_correction_total = sum((item.amount for item in all_corrections), Decimal("0"))
        dated_correction_total = sum((item.amount for item in dated_corrections), Decimal("0"))
        all_outgoing = account.outgoing_transfers.all()
        all_incoming = account.incoming_transfers.all()
        dated_outgoing = all_outgoing.filter(transaction_date__lte=as_of_date)
        dated_incoming = all_incoming.filter(transaction_date__lte=as_of_date)
        all_transfer_net = sum((item.amount for item in all_incoming), Decimal("0")) - sum(
            (item.amount for item in all_outgoing), Decimal("0")
        )
        dated_transfer_net = sum((item.amount for item in dated_incoming), Decimal("0")) - sum(
            (item.amount for item in dated_outgoing), Decimal("0")
        )
        opening_balance = account.balance - all_transaction_net - all_correction_total - all_transfer_net
        account.display_balance = opening_balance + dated_transaction_net + dated_correction_total + dated_transfer_net

    context = {
        "accounts": accounts,
        "recent_transactions": transactions[:6],
        "savings_goals": savings_goals[:3],
        "category_expenses": category_expenses,
        "subcategory_expenses": subcategory_expenses,
        "total_balance": sum((account.display_balance for account in accounts), Decimal("0")),
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
    )


@login_required
def transaction_list(request):
    transactions = _transaction_queryset(request.user).order_by("-transaction_date", "-created_at")
    accounts = Account.objects.filter(owner=request.user).order_by("name")

    from .models import Category, SubCategory

    context = {
        "transactions": transactions,
        "accounts": accounts,
        "categories": Category.objects.filter(owner=request.user).order_by("name"),
        "subcategories": SubCategory.objects.filter(
            Q(owner=request.user) | Q(owner__isnull=True, category__owner=request.user)
        )
        .select_related("category")
        .order_by("category__name", "name"),
        "transaction_count": transactions.count(),
    }
    return render(request, "finance/transactions.html", context)


@login_required
def analytics_page(request):
    today = timezone.localdate()
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

    account_id = request.GET.get("account") or None
    category_id = request.GET.get("category") or None
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
        },
    )


@login_required
def budgets_page(request):
    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", "0"))
            name = request.POST.get("name", "").strip()
            category_id = request.POST.get("category") or None
            category = Category.objects.filter(owner=request.user, pk=category_id).first()
            if not name or amount <= 0:
                raise ValueError
            Budget.objects.create(
                owner=request.user,
                name=name,
                amount=amount,
                period=request.POST.get("period", "monthly"),
                start_date=request.POST.get("start_date") or timezone.localdate(),
                end_date=request.POST.get("end_date") or None,
                category=category,
            )
            messages.success(request, "Budget created.")
        except (InvalidOperation, ValueError):
            messages.error(request, "Enter a valid budget name and amount.")
        return redirect("finance_web:budgets")

    budgets = Budget.objects.filter(owner=request.user).select_related("category")
    today = timezone.localdate()
    for budget in budgets:
        expenses = Transaction.objects.filter(
            account__owner=request.user,
            type="expense",
            transaction_date__gte=budget.start_date,
        )
        if budget.end_date:
            expenses = expenses.filter(transaction_date__lte=budget.end_date)
        if budget.category_id:
            expenses = expenses.filter(category_id=budget.category_id)
        budget.spent = expenses.aggregate(total=Sum("amount"))["total"] or Decimal("0")
        budget.remaining = budget.amount - budget.spent
        budget.progress = min((budget.spent / budget.amount * 100), Decimal("100"))
    return render(
        request,
        "finance/budgets.html",
        {
            "budgets": budgets,
            "categories": Category.objects.filter(owner=request.user).order_by("name"),
            "today": today,
        },
    )


@login_required
def recurring_page(request):
    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", "0"))
            account = Account.objects.get(pk=request.POST.get("account"), owner=request.user)
            category = Category.objects.filter(owner=request.user, pk=request.POST.get("category")).first()
            if amount <= 0 or not request.POST.get("title", "").strip():
                raise ValueError
            RecurringTransaction.objects.create(
                account=account,
                amount=amount,
                type=request.POST.get("type", "expense"),
                title=request.POST["title"].strip(),
                category=category,
                frequency=request.POST.get("frequency", "monthly"),
                next_date=request.POST.get("next_date") or timezone.localdate(),
            )
            messages.success(request, "Recurring transaction created.")
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
        name = request.POST.get("name", "").strip()
        try:
            balance = Decimal(request.POST.get("balance", "0"))
            if not name or balance < 0:
                raise ValueError
            Account.objects.create(owner=request.user, name=name, balance=balance)
            messages.success(request, "Account created.")
        except (InvalidOperation, ValueError):
            messages.error(request, "Enter a name and a valid non-negative balance.")
        return redirect("finance_web:accounts")

    accounts = Account.objects.filter(owner=request.user).order_by("name")
    return render(request, "finance/accounts.html", {"accounts": accounts})

@login_required
def accounts_details(request, account_id):
    account = get_object_or_404(Account, pk=account_id, owner=request.user)
    return render(request, "finance/account_page.html", {"account": account})

@login_required
def categories_page(request):
    from .models import Category, SubCategory

    if request.method == "POST":
        action = request.POST.get("action")
        name = request.POST.get("name", "").strip()
        if not name:
            messages.error(request, "A name is required.")
        elif action == "category":
            Category.objects.create(
                owner=request.user,
                name=name,
                type=request.POST.get("type", "expense"),
            )
            messages.success(request, "Category created.")
        elif action == "subcategory":
            category = get_object_or_404(
                Category, pk=request.POST.get("category"), owner=request.user
            )
            SubCategory.objects.create(owner=request.user, name=name, category=category)
            messages.success(request, "Subcategory created.")
        return redirect("finance_web:categories")

    categories = Category.objects.filter(owner=request.user).prefetch_related("subcategories").order_by("name")
    return render(request, "finance/categories.html", {"categories": categories})


@login_required
def goals_page(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        try:
            target_amount = Decimal(request.POST.get("target_amount", "0"))
            account = get_object_or_404(
                Account, pk=request.POST.get("account"), owner=request.user
            )
            if not name or target_amount <= 0:
                raise ValueError
            SavingsGoal.objects.create(
                name=name,
                target_amount=target_amount,
                account=account,
            )
            messages.success(request, "Savings goal created.")
        except (InvalidOperation, ValueError):
            messages.error(request, "Enter a name and a valid target amount.")
        return redirect("finance_web:goals")

    goals = SavingsGoal.objects.filter(account__owner=request.user).select_related("account")
    accounts = Account.objects.filter(owner=request.user).order_by("name")
    return render(request, "finance/goals.html", {"goals": goals, "accounts": accounts})

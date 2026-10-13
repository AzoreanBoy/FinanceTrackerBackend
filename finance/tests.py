import csv
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .analytics import budget_cycle_bounds, build_expense_analytics
from .models import (
    Account,
    BalanceCorrection,
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
    Transfer,
)
from .currencies import convert_amount
from .recurring import process_due_recurring_transactions


class TransactionPageTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create(
            username="finance-user",
            password="test-password",
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Everyday account",
            balance=Decimal("100.00"),
        )
        self.client.force_login(self.user)

    def test_new_transaction_page_renders_for_signed_in_user(self):
        response = self.client.get(reverse("finance_web:transaction_create"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "finance/transaction_create.html")
        self.assertContains(response, "Save transaction")
        self.assertContains(response, self.account.name)
        self.assertNotContains(response, "Choose an account")
        self.assertContains(response, f'<option value="{self.account.id}">')

    def test_new_transaction_page_only_lists_the_users_accounts(self):
        other_user = get_user_model().objects.create(
            username="another-user",
            password="test-password",
        )
        Account.objects.create(
            owner=other_user,
            name="Private account",
            balance=Decimal("50.00"),
        )

        response = self.client.get(reverse("finance_web:transaction_create"))

        self.assertContains(response, self.account.name)
        self.assertNotContains(response, "Private account")

    def test_new_transaction_page_renders_visual_category_choices_with_icons(self):
        category = Category.objects.create(
            owner=self.user,
            name="Food",
            type="expense",
            icon="🍽️",
        )
        subcategory = SubCategory.objects.create(
            owner=self.user,
            name="Groceries",
            category=category,
        )

        response = self.client.get(reverse("finance_web:transaction_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-category-option')
        self.assertContains(response, f'data-category-id="{category.id}"')
        self.assertContains(response, "🍽️")
        self.assertContains(response, 'data-subcategory-field')
        self.assertContains(response, 'role="radiogroup" aria-label="Transaction type"')
        self.assertContains(response, 'data-entry-type-choice="expense"')
        self.assertContains(response, 'data-entry-type-choice="income"')
        self.assertContains(response, 'data-subcategory-option')
        self.assertContains(response, f'data-subcategory-id="{subcategory.id}"')
        self.assertContains(response, "🛒")
        self.assertNotContains(response, '<select name="subcategory"')
        self.assertEqual(response.context["categories"][0].display_icon, "🍽️")
        self.assertEqual(response.context["subcategories"][0].display_icon, "🛒")

    def test_transaction_quick_add_and_edit_use_visual_category_controls(self):
        category = Category.objects.create(
            owner=self.user,
            name="Food",
            type="expense",
            icon="🍽️",
        )
        SubCategory.objects.create(
            owner=self.user,
            name="Groceries",
            category=category,
        )

        response = self.client.get(reverse("finance_web:transactions"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-entry-type-choice="income"')
        self.assertContains(response, f'data-category-id="{category.id}"')
        self.assertContains(response, 'data-subcategory-option')
        self.assertNotContains(response, '<select name="category" data-category-select')
        self.assertNotContains(response, '<select name="subcategory" data-subcategory-select')
        self.assertContains(response, 'class="transaction-edit-panel')
        self.assertContains(response, 'class="transaction-edit-content')
        self.assertContains(response, 'class="transaction-edit-actions')
        self.assertContains(response, "Save changes")

    def test_service_worker_is_served_with_root_scope_permission(self):
        response = self.client.get("/service-worker.js")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertContains(response, 'request.mode === "navigate"')
        self.assertNotContains(response, 'const SHELL = ["/"')

    def test_category_page_offers_icon_choices_and_suggests_icons_for_existing_categories(self):
        category = Category.objects.create(
            owner=self.user,
            name="Food",
            type="expense",
        )
        subcategory = SubCategory.objects.create(
            owner=self.user,
            name="Groceries",
            category=category,
        )

        response = self.client.get(reverse("finance_web:categories"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="🍽️"')
        self.assertContains(response, 'value="🛒"')
        self.assertEqual(response.context["categories"][0].display_icon, "🍽️")
        self.assertEqual(
            response.context["categories"][0].subcategories.all()[0].display_icon,
            "🛒",
        )
        self.assertContains(response, 'value="update_category"')
        self.assertContains(response, 'value="update_subcategory"')
        self.assertContains(response, 'value="delete_category"')
        self.assertContains(response, 'value="delete_subcategory"')

    def test_category_and_subcategory_creation_stores_selected_icons(self):
        self.client.post(
            reverse("finance_web:categories"),
            {
                "action": "category",
                "name": "Travel",
                "type": "expense",
                "icon": "✈️",
            },
        )
        category = Category.objects.get(owner=self.user, name="Travel")
        self.assertEqual(category.icon, "✈️")

        self.client.post(
            reverse("finance_web:categories"),
            {
                "action": "subcategory",
                "name": "Coffee",
                "category": category.pk,
                "icon": "☕",
            },
        )
        subcategory = category.subcategories.get(name="Coffee")
        self.assertEqual(subcategory.icon, "☕")

    def test_category_management_edits_categories_and_moves_subcategories(self):
        source = Category.objects.create(
            owner=self.user,
            name="Food",
            type="expense",
            icon="🍽️",
        )
        target = Category.objects.create(
            owner=self.user,
            name="Home",
            type="expense",
            icon="🏠",
        )
        subcategory = SubCategory.objects.create(
            owner=self.user,
            name="Groceries",
            category=source,
            icon="🛒",
        )
        transaction = Transaction.objects.create(
            account=self.account,
            amount=Decimal("12.00"),
            type="expense",
            title="Weekly shop",
            category=source,
            subcategory=subcategory,
        )

        response = self.client.post(
            reverse("finance_web:categories"),
            {
                "action": "update_category",
                "category_id": source.pk,
                "name": "Essentials",
                "type": "income",
                "icon": "💼",
            },
        )
        self.assertRedirects(response, reverse("finance_web:categories"))
        source.refresh_from_db()
        self.assertEqual((source.name, source.type, source.icon), ("Essentials", "income", "💼"))

        response = self.client.post(
            reverse("finance_web:categories"),
            {
                "action": "update_subcategory",
                "subcategory_id": subcategory.pk,
                "name": "Market",
                "category": target.pk,
                "icon": "🛒",
            },
        )
        self.assertRedirects(response, reverse("finance_web:categories"))
        subcategory.refresh_from_db()
        transaction.refresh_from_db()
        self.assertEqual(subcategory.name, "Market")
        self.assertEqual(subcategory.category, target)
        self.assertEqual(transaction.category, target)
        self.assertEqual(transaction.subcategory, subcategory)

    def test_category_deletion_keeps_transactions_uncategorised_and_subcategory_deletion_keeps_parent(self):
        category = Category.objects.create(
            owner=self.user,
            name="Food",
            type="expense",
        )
        subcategory = SubCategory.objects.create(
            owner=self.user,
            name="Groceries",
            category=category,
        )
        transaction = Transaction.objects.create(
            account=self.account,
            amount=Decimal("12.00"),
            type="expense",
            title="Weekly shop",
            category=category,
            subcategory=subcategory,
        )

        response = self.client.post(
            reverse("finance_web:categories"),
            {"action": "delete_subcategory", "subcategory_id": subcategory.pk},
        )
        self.assertRedirects(response, reverse("finance_web:categories"))
        transaction.refresh_from_db()
        self.assertIsNone(transaction.subcategory)
        self.assertEqual(transaction.category, category)

        response = self.client.post(
            reverse("finance_web:categories"),
            {"action": "delete_category", "category_id": category.pk},
        )
        self.assertRedirects(response, reverse("finance_web:categories"))
        transaction.refresh_from_db()
        self.assertIsNone(transaction.category)
        self.assertTrue(Transaction.objects.filter(pk=transaction.pk).exists())

    def test_category_creation_uses_name_based_icon_when_auto_is_selected(self):
        response = self.client.post(
            reverse("finance_web:categories"),
            {
                "action": "category",
                "name": "Salary",
                "type": "income",
                "icon": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Category.objects.get(owner=self.user, name="Salary").icon,
            "💼",
        )

    def test_transaction_activity_is_grouped_by_date(self):
        today = timezone.localdate()
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("12.50"),
            type="expense",
            title="Lunch",
            transaction_date=today,
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("150.00"),
            type="income",
            title="Payday",
            transaction_date=today - timedelta(days=1),
        )
        Tag.objects.create(owner=self.user, name="Planned")

        response = self.client.get(reverse("finance_web:transactions"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A friendly timeline of where your money goes.")
        self.assertContains(response, "Lunch")
        self.assertContains(response, "Payday")
        self.assertEqual(response.context["income_count"], 1)
        self.assertEqual(response.context["expense_count"], 1)
        self.assertFalse(response.context["filters_applied"])
        self.assertEqual(response.content.count(b"data-transaction-group"), 2)
        self.assertContains(response, "More filters")
        self.assertContains(response, 'id="mobile-bottom-nav"')
        self.assertEqual(response.content.count(b'type="checkbox" name="tags"'), 2)
        self.assertNotContains(response, "Ctrl or Command")

    def test_transaction_list_shows_a_clear_empty_state_for_filter_misses(self):
        response = self.client.get(
            reverse("finance_web:transactions"),
            {"q": "not in my activity"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["filters_applied"])
        self.assertContains(response, "No transactions found")
        self.assertContains(response, "Clear filters")
        self.assertNotContains(response, "Your activity starts here")

    def test_transaction_list_filters_by_date_type_category_and_amount(self):
        category = Category.objects.create(
            owner=self.user,
            name="Travel",
            type="expense",
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("45.00"),
            type="expense",
            title="Train",
            category=category,
            transaction_date=date(2025, 4, 10),
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("12.00"),
            type="expense",
            title="Coffee",
            category=category,
            transaction_date=date(2025, 4, 10),
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("80.00"),
            type="income",
            title="Refund",
            category=category,
            transaction_date=date(2025, 4, 11),
        )

        response = self.client.get(
            reverse("finance_web:transactions"),
            {
                "start": "2025-04-10",
                "end": "2025-04-10",
                "type": "expense",
                "category": category.pk,
                "currency": "EUR",
                "minimum": "20",
                "maximum": "50",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["transaction_count"], 1)
        self.assertContains(response, "Train")
        self.assertNotContains(response, "Coffee")
        self.assertNotContains(response, "Refund")

    def test_transaction_list_reports_invalid_date_filter(self):
        response = self.client.get(
            reverse("finance_web:transactions"),
            {"start": "not-a-date"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid start date.")

    def test_budget_page_shows_current_cycle_limit_and_spending(self):
        today = timezone.localdate()
        start_date = today - timedelta(days=3)
        budget = Budget.objects.create(
            owner=self.user,
            name="Weekly essentials",
            amount=Decimal("100.00"),
            period="weekly",
            start_date=start_date,
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("25.00"),
            type="expense",
            title="Groceries",
            transaction_date=today - timedelta(days=1),
        )

        response = self.client.get(reverse("finance_web:budgets"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Weekly essentials")
        self.assertContains(response, "100.00")
        self.assertContains(response, "25.00 spent")
        self.assertEqual(response.context["budgets"][0].cycle_amount, budget.amount)
        self.assertEqual(response.context["budgets"][0].period_start, start_date)
        self.assertEqual(
            response.context["budgets"][0].period_end,
            start_date + timedelta(days=6),
        )

    def test_budget_page_rejects_invalid_dates_and_foreign_categories(self):
        other_user = get_user_model().objects.create_user(username="budget-outsider")
        private_category = Category.objects.create(
            owner=other_user,
            name="Private category",
            type="expense",
        )

        response = self.client.post(
            reverse("finance_web:budgets"),
            {
                "name": "Invalid budget",
                "amount": "100.00",
                "currency": "EUR",
                "period": "custom",
                "start_date": "2025-04-10",
                "end_date": "2025-04-09",
                "category": private_category.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Budget.objects.filter(owner=self.user).exists())
        response = self.client.get(reverse("finance_web:budgets"))
        self.assertContains(response, "Enter a valid budget name and amount.")

    def test_transaction_csv_export_respects_filters_and_user_scope(self):
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("45.00"),
            type="expense",
            title="Filtered, quoted expense",
            description="Test, with comma",
            transaction_date=date(2025, 4, 10),
        )
        other_user = get_user_model().objects.create_user(
            username="csv-private-owner",
            password="temporary-test-password",
        )
        other_account = Account.objects.create(
            owner=other_user,
            name="Private account",
            balance=Decimal("0.00"),
        )
        Transaction.objects.create(
            account=other_account,
            amount=Decimal("99.00"),
            type="expense",
            title="Private transaction",
            transaction_date=date(2025, 4, 10),
        )

        response = self.client.get(
            reverse("finance_web:transactions"),
            {"start": "2025-04-01", "end": "2025-04-30", "export": "csv"},
        )

        rows = list(csv.reader(StringIO(response.content.decode("utf-8"))))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('attachment; filename="finance-transactions.csv"', response["Content-Disposition"])
        self.assertEqual(rows[0][-2:], ["amount", "currency"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][3], "Filtered, quoted expense")
        self.assertEqual(rows[1][4], "Test, with comma")
        self.assertEqual(rows[1][-2:], ["45.00", "EUR"])
        self.assertNotIn("Private transaction", response.content.decode("utf-8"))

    def test_account_creation_records_a_dated_opening_balance_only_when_given(self):
        response = self.client.post(
            reverse("finance_web:accounts"),
            {
                "name": "Dated bank",
                "balance": "250.00",
                "opening_balance_date": "2025-01-01",
                "icon": "💳",
                "color": "#5797B8",
            },
        )

        account = Account.objects.get(owner=self.user, name="Dated bank")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(account.opening_balance, Decimal("250.00"))
        self.assertEqual(account.opening_balance_date, date(2025, 1, 1))
        self.assertEqual(account.icon, "💳")
        self.assertEqual(account.color, "#5797B8")

        self.client.post(
            reverse("finance_web:accounts"),
            {"name": "Undated wallet", "balance": "25.00"},
        )
        undated = Account.objects.get(owner=self.user, name="Undated wallet")
        self.assertIsNone(undated.opening_balance)
        self.assertIsNone(undated.opening_balance_date)

    def test_accounts_page_exposes_visual_account_customization(self):
        response = self.client.get(reverse("finance_web:accounts"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-edit-account')
        self.assertContains(response, 'id="edit-account-modal"')
        self.assertContains(response, 'name="icon"')
        self.assertContains(response, 'name="color"')
        self.assertContains(response, "Edit account")
        self.assertContains(response, "Card color")

    def test_account_can_update_name_icon_and_color_without_changing_its_balance_or_history(self):
        transaction = Transaction.objects.create(
            account=self.account,
            amount=Decimal("15.00"),
            type="expense",
            title="Lunch",
        )
        current_balance = self.account.balance

        response = self.client.post(
            reverse("finance_web:accounts"),
            {
                "action": "update",
                "account_id": self.account.pk,
                "name": "Daily spending",
                "currency": "EUR",
                "icon": "💳",
                "color": "#5797B8",
            },
        )

        self.account.refresh_from_db()
        transaction.refresh_from_db()
        self.assertRedirects(response, reverse("finance_web:accounts"))
        self.assertEqual(self.account.name, "Daily spending")
        self.assertEqual(self.account.icon, "💳")
        self.assertEqual(self.account.color, "#5797B8")
        self.assertEqual(self.account.balance, current_balance)
        self.assertEqual(transaction.account_id, self.account.pk)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_account_currency_can_change_before_any_balance_or_activity(self):
        account = Account.objects.create(
            owner=self.user,
            name="Empty travel wallet",
            balance=Decimal("0.00"),
        )

        response = self.client.post(
            reverse("finance_web:accounts"),
            {
                "action": "update",
                "account_id": account.pk,
                "name": "Travel wallet",
                "currency": "USD",
                "icon": "✈️",
                "color": "#9473B5",
            },
        )

        account.refresh_from_db()
        self.assertRedirects(response, reverse("finance_web:accounts"))
        self.assertEqual(account.currency, "USD")
        self.assertEqual(account.name, "Travel wallet")
        self.assertEqual(account.icon, "✈️")
        self.assertEqual(account.color, "#9473B5")

    def test_account_currency_cannot_be_changed_after_balance_or_activity_exists(self):
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("15.00"),
            type="expense",
            title="Lunch",
        )
        original_balance = self.account.balance

        response = self.client.post(
            reverse("finance_web:accounts"),
            {
                "action": "update",
                "account_id": self.account.pk,
                "name": "Daily spending",
                "currency": "USD",
                "icon": "💳",
                "color": "#5797B8",
            },
            follow=True,
        )

        self.account.refresh_from_db()
        self.assertRedirects(response, reverse("finance_web:accounts"))
        self.assertEqual(self.account.name, "Everyday account")
        self.assertEqual(self.account.currency, "EUR")
        self.assertEqual(self.account.balance, original_balance)
        self.assertContains(response, "Currency cannot be changed", status_code=200)

    def test_account_edit_is_limited_to_the_current_user(self):
        other_user = get_user_model().objects.create_user(
            username="account-edit-other-user",
            password="test-password",
        )
        other_account = Account.objects.create(
            owner=other_user,
            name="Private account",
            balance=Decimal("10.00"),
        )

        response = self.client.post(
            reverse("finance_web:accounts"),
            {
                "action": "update",
                "account_id": other_account.pk,
                "name": "Changed",
                "currency": "EUR",
                "icon": "💳",
                "color": "#5797B8",
            },
        )

        other_account.refresh_from_db()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(other_account.name, "Private account")

    def test_account_balance_history_uses_opening_balance_and_dated_activity(self):
        account = Account.objects.create(
            owner=self.user,
            name="History account",
            balance=Decimal("100.00"),
            opening_balance=Decimal("100.00"),
            opening_balance_date=date(2025, 1, 1),
        )
        destination = Account.objects.create(
            owner=self.user,
            name="Destination",
            balance=Decimal("0.00"),
        )
        Transaction.objects.create(
            account=account,
            amount=Decimal("20.00"),
            type="expense",
            title="Groceries",
            transaction_date=date(2025, 1, 5),
        )
        BalanceCorrection.objects.create(
            account=account,
            amount=Decimal("5.00"),
            description="Cashback",
            transaction_date=date(2025, 1, 7),
        )
        Transfer.objects.create(
            from_account=account,
            to_account=destination,
            amount=Decimal("10.00"),
            transaction_date=date(2025, 1, 8),
        )

        response = self.client.get(
            reverse("finance_web:accounts_details", args=[account.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["history"]), 4)
        self.assertEqual(response.context["history"][-1]["balance"], Decimal("75.00"))
        self.assertContains(response, "Opening balance")
        self.assertContains(response, "Groceries")
        self.assertContains(response, "Cashback")
        self.assertContains(response, "Transfer to Destination")

    def test_account_without_dated_opening_balance_does_not_show_history(self):
        response = self.client.get(
            reverse("finance_web:accounts_details", args=[self.account.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_balance_history"])
        self.assertContains(response, "No reliable balance history yet")
        self.assertNotContains(response, "Balance timeline")

    def test_account_can_record_a_confirmed_historical_opening_balance(self):
        response = self.client.post(
            reverse("finance_web:accounts_details", args=[self.account.pk]),
            {
                "opening_balance": "75.50",
                "opening_balance_date": "2025-01-01",
            },
        )

        self.account.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.account.opening_balance, Decimal("75.50"))
        self.assertEqual(self.account.opening_balance_date, date(2025, 1, 1))
        self.assertEqual(self.account.balance, Decimal("100.00"))

    def test_user_cannot_open_another_users_account_history(self):
        other_user = get_user_model().objects.create_user(
            username="private-account-owner",
            password="temporary-test-password",
        )
        private_account = Account.objects.create(
            owner=other_user,
            name="Private account",
            balance=Decimal("10.00"),
            opening_balance=Decimal("10.00"),
            opening_balance_date=date(2025, 1, 1),
        )

        response = self.client.get(
            reverse("finance_web:accounts_details", args=[private_account.pk])
        )

        self.assertEqual(response.status_code, 404)


class FinanceAnalyticsTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="analytics-user",
            password="test-password",
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Analytics account",
            balance=Decimal("0.00"),
        )
        self.food = Category.objects.create(
            owner=self.user,
            name="Food",
            type="expense",
        )

    def test_monthly_budget_cycle_preserves_month_end_anchor(self):
        budget = Budget.objects.create(
            owner=self.user,
            name="Month-end budget",
            amount=Decimal("250.00"),
            period="monthly",
            start_date=date(2025, 1, 31),
        )

        february_start, february_end, february_amount = budget_cycle_bounds(
            budget, date(2025, 2, 15)
        )
        march_start, march_end, march_amount = budget_cycle_bounds(
            budget, date(2025, 3, 15)
        )

        self.assertEqual(
            (february_start, february_end),
            (date(2025, 1, 31), date(2025, 2, 27)),
        )
        self.assertEqual(
            (march_start, march_end),
            (date(2025, 2, 28), date(2025, 3, 30)),
        )
        self.assertEqual(february_amount, Decimal("250.00"))
        self.assertEqual(march_amount, Decimal("250.00"))

    def test_analytics_reports_income_expenses_cash_flow_and_savings_rate(self):
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("1000.00"),
            type="income",
            title="Salary",
            transaction_date=date(2025, 1, 15),
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("300.00"),
            type="expense",
            title="Groceries",
            category=self.food,
            transaction_date=date(2025, 1, 16),
        )

        analytics = build_expense_analytics(
            self.user,
            date(2025, 1, 1),
            date(2025, 1, 31),
        )

        self.assertEqual(analytics["total_income"], Decimal("1000.00"))
        self.assertEqual(analytics["total_expenses"], Decimal("300.00"))
        self.assertEqual(analytics["net_cash_flow"], Decimal("700.00"))
        self.assertEqual(analytics["savings_rate"], Decimal("70.00"))
        self.assertEqual(analytics["cash_flow_months"][0]["income"], Decimal("1000.00"))
        self.assertEqual(analytics["cash_flow_months"][0]["expenses"], Decimal("300.00"))

    def test_analytics_compares_the_same_length_previous_period(self):
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("100.00"),
            type="income",
            title="Previous income",
            transaction_date=date(2025, 1, 5),
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("50.00"),
            type="expense",
            title="Previous expense",
            transaction_date=date(2025, 1, 6),
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("200.00"),
            type="income",
            title="Current income",
            transaction_date=date(2025, 2, 5),
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("75.00"),
            type="expense",
            title="Current expense",
            transaction_date=date(2025, 2, 6),
        )

        analytics = build_expense_analytics(
            self.user,
            date(2025, 2, 1),
            date(2025, 2, 28),
        )

        self.assertEqual(
            analytics["period_comparison"]["previous_start"],
            date(2025, 1, 4),
        )
        self.assertEqual(
            analytics["period_comparison"]["previous_end"],
            date(2025, 1, 31),
        )
        self.assertEqual(
            analytics["period_comparison"]["income_change_percent"],
            Decimal("100.00"),
        )
        self.assertEqual(
            analytics["period_comparison"]["expense_change_percent"],
            Decimal("50.00"),
        )

    def test_analytics_respects_account_and_category_filters(self):
        other_account = Account.objects.create(
            owner=self.user,
            name="Other account",
            balance=Decimal("0.00"),
        )
        other_user = get_user_model().objects.create_user(
            username="other-analytics-user",
            password="test-password",
        )
        private_account = Account.objects.create(
            owner=other_user,
            name="Private account",
            balance=Decimal("0.00"),
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("40.00"),
            type="expense",
            title="Food",
            category=self.food,
            transaction_date=date(2025, 1, 10),
        )
        Transaction.objects.create(
            account=other_account,
            amount=Decimal("60.00"),
            type="expense",
            title="Other account",
            category=self.food,
            transaction_date=date(2025, 1, 11),
        )
        Transaction.objects.create(
            account=private_account,
            amount=Decimal("90.00"),
            type="expense",
            title="Private",
            transaction_date=date(2025, 1, 12),
        )

        analytics = build_expense_analytics(
            self.user,
            date(2025, 1, 1),
            date(2025, 1, 31),
            account_id=self.account.pk,
            category_id=self.food.pk,
        )

        self.assertEqual(analytics["total_expenses"], Decimal("40.00"))
        self.assertEqual(analytics["transaction_count"], 1)

    def test_analytics_compares_budget_with_filtered_expenses_for_selected_dates(self):
        Budget.objects.create(
            owner=self.user,
            name="Weekly food",
            amount=Decimal("70.00"),
            period="weekly",
            start_date=date(2025, 1, 1),
            category=self.food,
        )
        Budget.objects.create(
            owner=self.user,
            name="Monthly food",
            amount=Decimal("20.00"),
            period="monthly",
            start_date=date(2025, 1, 1),
            category=self.food,
        )
        other_user = get_user_model().objects.create_user(
            username="other-budget-user",
            password="temporary-test-password",
        )
        Budget.objects.create(
            owner=other_user,
            name="Private budget",
            amount=Decimal("100.00"),
            period="monthly",
            start_date=date(2025, 1, 1),
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("30.00"),
            type="expense",
            title="Food in range",
            category=self.food,
            transaction_date=date(2025, 1, 10),
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("300.00"),
            type="expense",
            title="Food outside range",
            category=self.food,
            transaction_date=date(2025, 2, 10),
        )

        analytics = build_expense_analytics(
            self.user,
            date(2025, 1, 1),
            date(2025, 1, 15),
            account_id=self.account.pk,
            category_id=self.food.pk,
        )
        budgets = {item["name"]: item for item in analytics["budget_comparison"]}

        self.assertEqual(set(budgets), {"Weekly food", "Monthly food"})
        self.assertEqual(budgets["Weekly food"]["spent"], Decimal("30.00"))
        self.assertEqual(budgets["Weekly food"]["budgeted"], Decimal("150.00"))
        self.assertEqual(budgets["Monthly food"]["budgeted"], Decimal("9.68"))
        self.assertTrue(budgets["Monthly food"]["over_budget"])
        self.assertEqual(budgets["Monthly food"]["progress"], Decimal("30.00") / Decimal("9.68") * 100)
        self.assertEqual(budgets["Monthly food"]["progress_bar"], Decimal("100"))
        self.assertEqual(budgets["Monthly food"]["remaining"], Decimal("-20.32"))

    def test_analytics_page_displays_cash_flow_metrics(self):
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("1200.00"),
            type="income",
            title="Salary",
            transaction_date=date(2025, 1, 15),
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("450.00"),
            type="expense",
            title="Rent",
            transaction_date=date(2025, 1, 16),
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("finance_web:analytics"),
            {"start": "2025-01-01", "end": "2025-01-31"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Income")
        self.assertContains(response, "Net cash flow")
        self.assertContains(response, "Savings rate")
        self.assertContains(response, "EUR 1200.00")
        self.assertContains(response, "EUR 750.00")

    def test_analytics_page_displays_budget_progress(self):
        Budget.objects.create(
            owner=self.user,
            name="Food plan",
            amount=Decimal("500.00"),
            period="monthly",
            start_date=date(2025, 1, 1),
            category=self.food,
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("125.00"),
            type="expense",
            title="Groceries",
            category=self.food,
            transaction_date=date(2025, 1, 15),
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("finance_web:analytics"),
            {"start": "2025-01-01", "end": "2025-01-31"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Budget vs actual")
        self.assertContains(response, "Food plan")
        self.assertContains(response, "EUR 125.00")
        self.assertContains(response, "spent")
        self.assertContains(response, "EUR 500.00 planned")

    def test_analytics_api_includes_new_metrics_and_keeps_expense_fields(self):
        Budget.objects.create(
            owner=self.user,
            name="Food budget",
            amount=Decimal("200.00"),
            period="monthly",
            start_date=date(2025, 1, 1),
            category=self.food,
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("500.00"),
            type="income",
            title="Income",
            transaction_date=date(2025, 1, 15),
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("125.00"),
            type="expense",
            title="Expense",
            category=self.food,
            transaction_date=date(2025, 1, 16),
        )
        api_client = APIClient()
        api_client.force_authenticate(self.user)

        response = api_client.get(
            "/api/finance/analytics/expenses/",
            {"start": "2025-01-01", "end": "2025-01-31"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_income"], 500.0)
        self.assertEqual(response.data["total_expenses"], 125.0)
        self.assertEqual(response.data["net_cash_flow"], 375.0)
        self.assertIn("months", response.data)
        self.assertIn("categories", response.data)
        self.assertEqual(len(response.data["budget_comparison"]), 1)
        self.assertEqual(response.data["budget_comparison"][0]["name"], "Food budget")
        self.assertEqual(response.data["budget_comparison"][0]["spent"], 125.0)
        self.assertEqual(response.data["budget_comparison"][0]["budgeted"], 200.0)


class ExtendedFinanceFeatureTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="extended-finance-user",
            password="test-password",
        )
        self.account = Account.objects.create(
            owner=self.user,
            name="Everyday",
            balance=Decimal("0.00"),
            currency="EUR",
        )
        self.client.force_login(self.user)

    def test_csv_import_previews_valid_and_rejected_rows_then_imports_only_valid(self):
        csv_content = (
            "date,type,title,amount,account,currency\n"
            "2025-03-03,expense,New purchase,12.50,Everyday,EUR\n"
            "2025-03-03,expense,New purchase,12.50,Everyday,EUR\n"
            "2025-03-04,expense,Wrong currency,8.00,Everyday,USD\n"
        )
        response = self.client.post(
            reverse("finance_web:import"),
            {
                "action": "preview",
                "file": SimpleUploadedFile(
                    "transactions.csv", csv_content.encode("utf-8"), content_type="text/csv"
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        preview = response.context["preview"]
        self.assertEqual(preview["valid_count"], 1)
        self.assertEqual(preview["rejected_count"], 2)
        self.assertContains(response, "Wrong currency")

        response = self.client.post(
            reverse("finance_web:import"),
            {"action": "confirm", "batch_id": preview["batch_id"]},
        )

        self.assertRedirects(response, reverse("finance_web:transactions"))
        self.assertEqual(Transaction.objects.filter(account=self.account).count(), 1)
        self.assertEqual(
            self.account.__class__.objects.get(pk=self.account.pk).balance,
            Decimal("-12.50"),
        )

    def test_debt_repayments_keep_status_open_until_fully_repaid(self):
        debt = Debt.objects.create(
            owner=self.user,
            person="Alex",
            direction="lent",
            principal=Decimal("100.00"),
            currency="EUR",
            opened_on=date(2025, 1, 1),
        )
        url = reverse("finance_web:debts")
        self.client.post(
            url,
            {
                "action": "repayment",
                "debt": debt.pk,
                "amount": "40.00",
                "repayment_date": "2025-01-10",
                "account": self.account.pk,
            },
        )
        debt.refresh_from_db()
        self.assertEqual(debt.status, "open")
        self.assertEqual(debt.outstanding, Decimal("60.00"))
        self.assertEqual(self.account.__class__.objects.get(pk=self.account.pk).balance, Decimal("40.00"))

        self.client.post(
            url,
            {
                "action": "repayment",
                "debt": debt.pk,
                "amount": "60.00",
                "repayment_date": "2025-01-20",
                "account": self.account.pk,
            },
        )
        debt.refresh_from_db()
        self.assertEqual(debt.status, "settled")
        self.assertEqual(debt.outstanding, Decimal("0.00"))
        self.assertEqual(DebtRepayment.objects.filter(debt=debt).count(), 2)
        self.assertEqual(self.account.__class__.objects.get(pk=self.account.pk).balance, Decimal("100.00"))

    def test_debt_page_renders_opening_form_and_outstanding_amount(self):
        Debt.objects.create(
            owner=self.user,
            person="Morgan",
            direction="borrowed",
            principal=Decimal("75.00"),
            currency="EUR",
            opened_on=date(2025, 1, 1),
        )

        response = self.client.get(reverse("finance_web:debts"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "finance/debts.html")
        self.assertContains(response, "Morgan")
        self.assertContains(response, "EUR 75.00 left")
        self.assertContains(response, "Record a repayment")

    def test_exchange_rates_convert_directly_and_by_inverse_on_requested_date(self):
        ExchangeRate.objects.create(
            owner=self.user,
            from_currency="USD",
            to_currency="EUR",
            rate=Decimal("0.90"),
            effective_date=date(2025, 1, 1),
        )
        converted, rate, rate_date = convert_amount(
            self.user,
            Decimal("10.00"),
            "EUR",
            "USD",
            date(2025, 1, 10),
        )

        self.assertEqual(converted, Decimal("11.11"))
        self.assertEqual(rate_date, date(2025, 1, 1))
        self.assertEqual(rate.quantize(Decimal("0.000001")), Decimal("1.111111"))

    def test_analytics_converts_at_transaction_date_and_excludes_missing_rates(self):
        usd_account = Account.objects.create(
            owner=self.user,
            name="USD account",
            balance=Decimal("0.00"),
            currency="USD",
        )
        gbp_account = Account.objects.create(
            owner=self.user,
            name="GBP account",
            balance=Decimal("0.00"),
            currency="GBP",
        )
        ExchangeRate.objects.create(
            owner=self.user,
            from_currency="USD",
            to_currency="EUR",
            rate=Decimal("0.80"),
            effective_date=date(2025, 1, 1),
        )
        Transaction.objects.create(
            account=usd_account,
            amount=Decimal("10.00"),
            type="expense",
            title="Converted purchase",
            transaction_date=date(2025, 1, 10),
        )
        Transaction.objects.create(
            account=gbp_account,
            amount=Decimal("5.00"),
            type="expense",
            title="No rate",
            transaction_date=date(2025, 1, 10),
        )

        analytics = build_expense_analytics(
            self.user,
            date(2025, 1, 1),
            date(2025, 1, 31),
        )

        self.assertEqual(analytics["reporting_currency"], "EUR")
        self.assertEqual(analytics["total_expenses"], Decimal("8.00"))
        self.assertEqual(analytics["transaction_count"], 1)
        self.assertEqual(analytics["unconverted_transaction_count"], 1)
        self.assertEqual(analytics["unconverted_currencies"], ["GBP"])

    def test_dashboard_never_sums_currencies_or_invents_undated_balance_history(self):
        today = timezone.localdate()
        Account.objects.filter(pk=self.account.pk).update(balance=Decimal("50.00"))
        usd_account = Account.objects.create(
            owner=self.user,
            name="Dollar account",
            balance=Decimal("100.00"),
            currency="USD",
        )
        ExchangeRate.objects.create(
            owner=self.user,
            from_currency="USD",
            to_currency="EUR",
            rate=Decimal("0.90"),
            effective_date=today,
        )

        response = self.client.get(reverse("finance_web:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_balance"], Decimal("140.00"))
        self.assertContains(response, "EUR 140.00")

        response = self.client.get(
            reverse("finance_web:dashboard"),
            {"as_of": (today - timedelta(days=1)).isoformat()},
        )
        self.assertEqual(response.context["total_balance"], Decimal("0"))
        self.assertEqual(response.context["unknown_balance_account_count"], 2)
        self.assertContains(response, "Historical balance unavailable")

    def test_dashboard_recent_activity_uses_category_icons(self):
        category = Category.objects.create(
            owner=self.user,
            name="Food",
            type="expense",
            icon="",
        )
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("12.00"),
            type="expense",
            title="Lunch",
            category=category,
            transaction_date=timezone.localdate(),
        )

        response = self.client.get(reverse("finance_web:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["recent_transactions"][0]["category_display_icon"],
            "🍽️",
        )
        self.assertContains(response, "🍽️")

    def test_transaction_api_accepts_own_tags_and_rejects_another_users_tag(self):
        own_tag = Tag.objects.create(owner=self.user, name="Travel")
        other_user = get_user_model().objects.create_user(
            username="other-tag-owner",
            password="test-password",
        )
        private_tag = Tag.objects.create(owner=other_user, name="Private")
        api_client = APIClient()
        api_client.force_authenticate(self.user)
        payload = {
            "account": self.account.pk,
            "amount": "15.00",
            "type": "expense",
            "title": "Train",
            "transaction_date": "2025-03-05",
            "tags": [own_tag.pk],
        }

        response = api_client.post("/api/finance/transactions/", payload, format="json")

        self.assertEqual(response.status_code, 201)
        transaction = Transaction.objects.get(pk=response.data["id"])
        self.assertEqual(list(transaction.tags.values_list("pk", flat=True)), [own_tag.pk])
        payload["tags"] = [private_tag.pk]
        response = api_client.post("/api/finance/transactions/", payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_transaction_type_is_independent_from_category_type(self):
        expense_category = Category.objects.create(
            owner=self.user,
            name="Groceries",
            type="expense",
        )
        api_client = APIClient()
        api_client.force_authenticate(self.user)

        response = api_client.post(
            "/api/finance/transactions/",
            {
                "account": self.account.pk,
                "amount": "15.00",
                "type": "income",
                "title": "Refund for groceries",
                "transaction_date": "2025-03-05",
                "category": expense_category.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        transaction = Transaction.objects.get(pk=response.data["id"])
        self.account.refresh_from_db()
        self.assertEqual(transaction.type, "income")
        self.assertEqual(transaction.category, expense_category)
        self.assertEqual(self.account.balance, Decimal("15.00"))

    def test_cross_currency_transfer_applies_destination_amount_and_edits_by_delta(self):
        source = Account.objects.create(
            owner=self.user,
            name="Dollar account",
            balance=Decimal("100.00"),
            currency="USD",
        )
        destination = Account.objects.create(
            owner=self.user,
            name="Euro account",
            balance=Decimal("0.00"),
            currency="EUR",
        )
        transfer = Transfer.objects.create(
            from_account=source,
            to_account=destination,
            amount=Decimal("10.00"),
            destination_amount=Decimal("9.00"),
            exchange_rate=Decimal("0.90000000"),
            transaction_date=date(2025, 1, 1),
        )
        source.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(source.balance, Decimal("90.00"))
        self.assertEqual(destination.balance, Decimal("9.00"))

        transfer.amount = Decimal("20.00")
        transfer.destination_amount = Decimal("18.00")
        transfer.save()
        source.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(source.balance, Decimal("80.00"))
        self.assertEqual(destination.balance, Decimal("18.00"))

        transfer.delete()
        source.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual(source.balance, Decimal("100.00"))
        self.assertEqual(destination.balance, Decimal("0.00"))

    def test_recurring_transactions_process_due_dates_once_and_keep_month_end_anchor(self):
        recurring = RecurringTransaction.objects.create(
            account=self.account,
            amount=Decimal("10.00"),
            type="expense",
            title="Monthly bill",
            frequency="monthly",
            next_date=date(2025, 1, 31),
        )

        created = process_due_recurring_transactions(
            user=self.user,
            through_date=date(2025, 2, 28),
        )

        recurring.refresh_from_db()
        self.account.refresh_from_db()
        self.assertEqual(created, 2)
        self.assertEqual(
            list(
                Transaction.objects.filter(account=self.account)
                .order_by("transaction_date")
                .values_list("transaction_date", flat=True)
            ),
            [date(2025, 1, 31), date(2025, 2, 28)],
        )
        self.assertEqual(recurring.next_date, date(2025, 3, 31))
        self.assertEqual(recurring.schedule_day, 31)
        self.assertEqual(self.account.balance, Decimal("-20.00"))
        self.assertEqual(
            process_due_recurring_transactions(
                user=self.user,
                through_date=date(2025, 2, 28),
            ),
            0,
        )

    def test_recurring_end_date_stops_after_the_last_allowed_occurrence(self):
        recurring = RecurringTransaction.objects.create(
            account=self.account,
            amount=Decimal("8.00"),
            type="expense",
            title="Final bill",
            frequency="monthly",
            next_date=date(2025, 1, 31),
            end_date=date(2025, 1, 31),
        )

        created = process_due_recurring_transactions(
            user=self.user,
            through_date=date(2025, 3, 1),
        )

        recurring.refresh_from_db()
        self.assertEqual(created, 1)
        self.assertFalse(recurring.active)
        self.assertEqual(Transaction.objects.filter(account=self.account).count(), 1)

    def test_budget_can_be_edited_without_changing_its_owner(self):
        category = Category.objects.create(
            owner=self.user, name="Food", type="expense"
        )
        budget = Budget.objects.create(
            owner=self.user,
            name="Old budget",
            amount=Decimal("100.00"),
            currency="EUR",
        )

        response = self.client.post(
            reverse("finance_web:budgets"),
            {
                "action": "update",
                "budget_id": budget.pk,
                "name": "Groceries",
                "amount": "250.00",
                "currency": "EUR",
                "period": "monthly",
                "start_date": "2025-01-01",
                "category": category.pk,
            },
        )

        budget.refresh_from_db()
        self.assertRedirects(response, reverse("finance_web:budgets"))
        self.assertEqual(budget.name, "Groceries")
        self.assertEqual(budget.amount, Decimal("250.00"))
        self.assertEqual(budget.category_id, category.pk)
        self.assertEqual(budget.owner_id, self.user.pk)

    def test_savings_goal_can_change_target_and_linked_account(self):
        other_account = Account.objects.create(
            owner=self.user, name="Savings", balance=Decimal("50.00")
        )
        goal = SavingsGoal.objects.create(
            name="Trip",
            target_amount=Decimal("500.00"),
            account=self.account,
        )

        response = self.client.post(
            reverse("finance_web:goals"),
            {
                "action": "update",
                "goal_id": goal.pk,
                "name": "Holiday",
                "target_amount": "1200.00",
                "account": other_account.pk,
            },
        )

        goal.refresh_from_db()
        self.assertRedirects(response, reverse("finance_web:goals"))
        self.assertEqual(goal.name, "Holiday")
        self.assertEqual(goal.target_amount, Decimal("1200.00"))
        self.assertEqual(goal.account_id, other_account.pk)

    def test_tag_can_be_edited_without_losing_transaction_links(self):
        tag = Tag.objects.create(owner=self.user, name="Old label")
        transaction = Transaction.objects.create(
            account=self.account,
            amount=Decimal("12.00"),
            type="expense",
            title="Train",
        )
        transaction.tags.add(tag)

        response = self.client.post(
            reverse("finance_web:tags"),
            {
                "action": "update",
                "tag_id": tag.pk,
                "name": "Travel",
                "color": "#5797B8",
            },
        )

        tag.refresh_from_db()
        self.assertRedirects(response, reverse("finance_web:tags"))
        self.assertEqual(tag.name, "Travel")
        self.assertEqual(tag.color, "#5797B8")
        self.assertTrue(transaction.tags.filter(pk=tag.pk).exists())

    def test_recurring_item_can_be_edited_without_rewriting_existing_transactions(self):
        recurring = RecurringTransaction.objects.create(
            account=self.account,
            amount=Decimal("10.00"),
            type="expense",
            title="Old bill",
            frequency="monthly",
            next_date=date(2025, 1, 31),
        )
        existing_transaction = Transaction.objects.create(
            account=self.account,
            amount=Decimal("10.00"),
            type="expense",
            title="Old bill",
            transaction_date=date(2025, 1, 31),
        )

        response = self.client.post(
            reverse("finance_web:recurring"),
            {
                "action": "update",
                "recurring_id": recurring.pk,
                "title": "Updated bill",
                "amount": "20.00",
                "type": "income",
                "frequency": "yearly",
                "next_date": "2025-02-28",
                "account": self.account.pk,
                "category": "",
                "active": "on",
            },
        )

        recurring.refresh_from_db()
        existing_transaction.refresh_from_db()
        self.assertRedirects(response, reverse("finance_web:recurring"))
        self.assertEqual(recurring.title, "Updated bill")
        self.assertEqual(recurring.amount, Decimal("20.00"))
        self.assertEqual(recurring.type, "income")
        self.assertEqual(recurring.schedule_day, 28)
        self.assertTrue(recurring.active)
        self.assertEqual(existing_transaction.title, "Old bill")
        self.assertEqual(existing_transaction.amount, Decimal("10.00"))

    def test_debt_edit_preserves_repayments_and_locks_historical_currency_and_direction(self):
        debt = Debt.objects.create(
            owner=self.user,
            person="Alex",
            direction="lent",
            principal=Decimal("100.00"),
            currency="EUR",
        )
        DebtRepayment.objects.create(
            debt=debt,
            amount=Decimal("25.00"),
            repayment_date=date(2025, 1, 10),
        )

        response = self.client.post(
            reverse("finance_web:debts"),
            {
                "action": "update",
                "debt_id": debt.pk,
                "person": "Alex Smith",
                "description": "Updated note",
                "principal": "150.00",
                "currency": "EUR",
                "opened_on": "2025-01-01",
                "due_date": "",
                "direction": "lent",
            },
        )

        debt.refresh_from_db()
        self.assertRedirects(response, reverse("finance_web:debts"))
        self.assertEqual(debt.person, "Alex Smith")
        self.assertEqual(debt.principal, Decimal("150.00"))
        self.assertEqual(debt.repaid, Decimal("25.00"))
        self.assertEqual(debt.status, "open")

        response = self.client.post(
            reverse("finance_web:debts"),
            {
                "action": "update",
                "debt_id": debt.pk,
                "person": "Alex Smith",
                "description": "Updated note",
                "principal": "150.00",
                "currency": "USD",
                "opened_on": "2025-01-01",
                "direction": "borrowed",
            },
            follow=True,
        )

        debt.refresh_from_db()
        self.assertContains(response, "currency or direction cannot change")
        self.assertEqual(debt.currency, "EUR")
        self.assertEqual(debt.direction, "lent")

    def test_edit_controls_render_for_financial_components(self):
        Budget.objects.create(
            owner=self.user,
            name="Food budget",
            amount=Decimal("250.00"),
            currency="EUR",
        )
        SavingsGoal.objects.create(
            name="Holiday",
            target_amount=Decimal("1000.00"),
            account=self.account,
        )
        Tag.objects.create(owner=self.user, name="Travel")
        RecurringTransaction.objects.create(
            account=self.account,
            amount=Decimal("15.00"),
            type="expense",
            title="Streaming",
            frequency="monthly",
            next_date=date(2025, 1, 31),
        )
        Debt.objects.create(
            owner=self.user,
            person="Alex",
            direction="lent",
            principal=Decimal("100.00"),
            currency="EUR",
        )

        for page in ("budgets", "goals", "tags", "recurring", "debts"):
            with self.subTest(page=page):
                response = self.client.get(reverse(f"finance_web:{page}"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Edit")
                self.assertContains(response, "Delete")
                if page in {"goals", "recurring"}:
                    self.assertNotContains(response, "Choose account")

    def test_transaction_list_shows_a_chip_in_the_linked_accounts_color(self):
        Transaction.objects.create(
            account=self.account,
            amount=Decimal("18.00"),
            type="expense",
            title="Lunch",
        )

        response = self.client.get(reverse("finance_web:transactions"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.account.name)
        self.assertContains(response, "background-color: #E88B7222")
        self.assertContains(response, "border-color: #E88B7266")

    def test_budget_goal_tag_and_recurring_items_can_be_deleted_individually(self):
        budget = Budget.objects.create(
            owner=self.user,
            name="Food budget",
            amount=Decimal("250.00"),
            currency="EUR",
        )
        goal = SavingsGoal.objects.create(
            name="Holiday",
            target_amount=Decimal("1000.00"),
            account=self.account,
        )
        tag = Tag.objects.create(owner=self.user, name="Travel")
        transaction = Transaction.objects.create(
            account=self.account,
            amount=Decimal("15.00"),
            type="expense",
            title="Train",
        )
        transaction.tags.add(tag)
        recurring = RecurringTransaction.objects.create(
            account=self.account,
            amount=Decimal("20.00"),
            type="expense",
            title="Subscription",
            frequency="monthly",
            next_date=date(2025, 1, 31),
        )

        for page, payload, model, pk in (
            ("budgets", {"action": "delete", "budget_id": budget.pk}, Budget, budget.pk),
            ("goals", {"action": "delete", "goal_id": goal.pk}, SavingsGoal, goal.pk),
            ("tags", {"action": "delete", "tag_id": tag.pk}, Tag, tag.pk),
            (
                "recurring",
                {"action": "delete", "recurring_id": recurring.pk},
                RecurringTransaction,
                recurring.pk,
            ),
        ):
            with self.subTest(page=page):
                response = self.client.post(
                    reverse(f"finance_web:{page}"), payload
                )
                self.assertRedirects(response, reverse(f"finance_web:{page}"))
                self.assertFalse(model.objects.filter(pk=pk).exists())

        transaction.refresh_from_db()
        self.assertFalse(transaction.tags.exists())
        self.assertTrue(Transaction.objects.filter(pk=transaction.pk).exists())

    def test_deleting_debt_keeps_linked_ledger_transaction_but_removes_repayment_history(self):
        debt = Debt.objects.create(
            owner=self.user,
            person="Alex",
            direction="lent",
            principal=Decimal("100.00"),
            currency="EUR",
        )
        transaction = Transaction.objects.create(
            account=self.account,
            amount=Decimal("25.00"),
            type="income",
            title="Debt repayment: Alex",
        )
        DebtRepayment.objects.create(
            debt=debt,
            amount=Decimal("25.00"),
            transaction=transaction,
        )
        balance_before_delete = self.account.balance

        response = self.client.post(
            reverse("finance_web:debts"),
            {"action": "delete", "debt_id": debt.pk},
        )

        self.assertRedirects(response, reverse("finance_web:debts"))
        self.assertFalse(Debt.objects.filter(pk=debt.pk).exists())
        self.assertFalse(DebtRepayment.objects.filter(debt_id=debt.pk).exists())
        self.assertTrue(Transaction.objects.filter(pk=transaction.pk).exists())
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, balance_before_delete)

    def test_exchange_rate_can_be_deleted_by_its_owner(self):
        rate = ExchangeRate.objects.create(
            owner=self.user,
            from_currency="USD",
            to_currency="EUR",
            rate=Decimal("0.92"),
            effective_date=date(2025, 1, 1),
        )

        response = self.client.post(
            reverse("finance_web:currencies"),
            {"action": "delete_rate", "rate_id": rate.pk},
        )

        self.assertRedirects(response, reverse("finance_web:currencies"))
        self.assertFalse(ExchangeRate.objects.filter(pk=rate.pk).exists())

    def test_only_empty_accounts_without_financial_history_can_be_deleted(self):
        empty_account = Account.objects.create(
            owner=self.user,
            name="Unused account",
            balance=Decimal("0.00"),
        )
        response = self.client.post(
            reverse("finance_web:accounts"),
            {"action": "delete", "account_id": empty_account.pk},
        )
        self.assertRedirects(response, reverse("finance_web:accounts"))
        self.assertFalse(Account.objects.filter(pk=empty_account.pk).exists())

        Transaction.objects.create(
            account=self.account,
            amount=Decimal("10.00"),
            type="expense",
            title="Coffee",
        )
        response = self.client.post(
            reverse("finance_web:accounts"),
            {"action": "delete", "account_id": self.account.pk},
            follow=True,
        )
        self.assertContains(response, "only unused empty accounts can be deleted")
        self.assertTrue(Account.objects.filter(pk=self.account.pk).exists())

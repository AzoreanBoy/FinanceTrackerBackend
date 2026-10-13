import uuid
from decimal import Decimal

from django.db import models, transaction as db_transaction
from django.utils import timezone


ACCOUNT_COLOR_CHOICES = (
    ("#E88B72", "Coral"),
    ("#55A98B", "Mint"),
    ("#5797B8", "Ocean"),
    ("#D6A23F", "Honey"),
    ("#9473B5", "Lavender"),
    ("#D36B87", "Rose"),
    ("#6176B8", "Indigo"),
    ("#718B62", "Sage"),
)
ACCOUNT_ICON_CHOICES = (
    ("🏦", "Bank"),
    ("💳", "Card"),
    ("👛", "Wallet"),
    ("💰", "Cash"),
    ("💼", "Work"),
    ("🐷", "Savings"),
    ("📈", "Investments"),
    ("✈️", "Travel"),
    ("🏠", "Home"),
    ("🛍️", "Shopping"),
    ("🎓", "Education"),
    ("✨", "Other"),
)


class Account(models.Model):
    """
    This model represents a financial account, such as a bank account or investment account.
    Each account has a name, balance, and is linked to a user (owner).
    The balance is updated automatically when transactions are created or deleted.
    The owner field links the account to a user, allowing for multiple accounts per user.
    The created_at and updated_at fields track when the account was created and last updated, respectively.
    Attributes:
        name (str): The name of the account. You can use this field to identify the account, such as "Checking Account" or "Savings Account".
        balance (Decimal): The current balance of the account. This field is automatically updated when transactions are created or deleted, ensuring that the balance always reflects the current state of the account.
        created_at (datetime): The date and time when the account was created.
        updated_at (datetime): The date and time when the account was last updated.
        owner (ForeignKey): A foreign key linking the account to a user (owner).
    """

    name = models.CharField(max_length=100)
    balance = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    color = models.CharField(
        max_length=7, choices=ACCOUNT_COLOR_CHOICES, default="#E88B72"
    )
    icon = models.CharField(
        max_length=16, choices=ACCOUNT_ICON_CHOICES, default="🏦"
    )
    opening_balance = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    opening_balance_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    owner = models.ForeignKey(
        "accounts.CustomUser", on_delete=models.CASCADE, related_name="user_accounts"
    )

    def __str__(self):
        return self.name


class BalanceCorrection(models.Model):
    """
    This model represents a correction to the balance of an account.
    Each balance correction is linked to an account and has an amount, description, and timestamp.
    The save method is overridden to automatically update the account balance when a balance correction is created. The delete method is also overridden to update the account balance when a balance correction is deleted.
    Attributes:
        id (UUID): A unique identifier for the balance correction.
        account (ForeignKey): A foreign key linking the balance correction to an account, this allows for tracking of balance corrections within specific accounts.
        amount (Decimal): The amount of the balance correction. This field can be positive or negative, depending on whether the correction increases or decreases the account balance.
        description (str): A description of the balance correction. This field can be used to provide additional information about the reason for the correction.
        created_at (DateTime): The date and time when the balance correction was created.

    The save method is overridden to automatically update the account balance when a balance correction is created. The delete method is also overridden to update the account balance when a balance correction is deleted.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="balance_corrections"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=200, blank=True, null=True)
    transaction_date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        with db_transaction.atomic():
            self.account.balance += self.amount
            self.account.save()
            super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        with db_transaction.atomic():
            self.account.balance -= self.amount
            self.account.save()
            super().delete(*args, **kwargs)

    def __str__(self):
        return f"Atualização de Saldo - {self.account} | Saldo Final: {self.account.balance} ({self.amount}) | {self.description}"


class Category(models.Model):
    """
    This model represents a category for financial transactions, such as "Food", "Rent", or "Salary".
    Each category has a name, description, and type (income or expense).
    The type field allows for categorization of transactions, which can be useful for budgeting and financial analysis.
    Attributes:
        name (str): The name of the category. You can use this field to identify the category, such as "Food" or "Rent".
        description (str): A description of the category. This field can be used to provide additional information about the category, such as what types of transactions should be categorized under it.
        type (str): The type of the category, either "income" or "expense". This field allows for categorization of transactions, which can be useful for budgeting and financial analysis.
    """

    id = models.AutoField(primary_key=True)
    owner = models.ForeignKey(
        "accounts.CustomUser", on_delete=models.CASCADE, related_name="user_categories", default=None, blank=True, null=True
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    type = models.CharField(
        max_length=10,
        choices=[("income", "Income"), ("expense", "Expense")],
        blank=True,
        null=True,
    )
    icon = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.name}"


class SubCategory(models.Model):
    """ "
    This model represents a subcategory for financial transactions, which is linked to a parent category.
    Each subcategory has a name, description, and is linked to a parent category.
    Attributes:
        name (str): The name of the subcategory. You can use this field to identify the subcategory, such as "Groceries" or "Utilities" inside the parent category such as "Food" or "Housing".
        description (str): A description of the subcategory. This field can be used to provide additional information about the subcategory, such as what types of transactions should be categorized under it.
        category (ForeignKey): A foreign key linking the subcategory to a parent category. This allows for more detailed categorization of transactions, which can be useful for budgeting and financial analysis.
    """

    id = models.AutoField(primary_key=True)
    owner = models.ForeignKey(
        "accounts.CustomUser", on_delete=models.CASCADE, related_name="user_subcategories", default=None, blank=True, null=True
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="subcategories"
    )
    icon = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.category} | {self.name}"


class Transaction(models.Model):
    """
    This model represents a financial transaction, which can be either income or expense.
    Each transaction is linked to an account and can be categorized under a category or subcategory.
    Attributes:
        id (UUID): A unique identifier for the transaction.
        account (ForeignKey): A foreign key linking the transaction to an account.
        amount (Decimal): The amount of the transaction.
        type (str): The type of the transaction, either "income" or "expense".
        title (str): The title of the transaction.
        description (str): A description of the transaction.
        created_at (DateTime): The date and time when the transaction was created.
        category (ForeignKey): A foreign key linking the transaction to a parent category.
        subcategory (ForeignKey): A foreign key linking the transaction to a subcategory.

    The save method is overridden to automatically set the category based on the subcategory, set the title if not provided, and update the account balance based on the transaction type and amount. The delete method is also overridden to update the account balance when a transaction is deleted.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="transactions"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    type = models.CharField(
        max_length=10,
        choices=[("income", "Income"), ("expense", "Expense")],
        blank=True,
        null=True,
        default="expense",
    )
    title = models.CharField(max_length=50, blank=True, null=True)
    description = models.CharField(max_length=200, blank=True, null=True)
    transaction_date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    subcategory = models.ForeignKey(
        SubCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    tags = models.ManyToManyField("Tag", blank=True, related_name="transactions")
    import_fingerprint = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "import_fingerprint"],
                condition=models.Q(import_fingerprint__isnull=False),
                name="unique_account_import_fingerprint",
            )
        ]

    def save(self, *args, **kwargs):
        # If a subcategory is provided, automatically set the category to the subcategory's category
        if self.subcategory:
            self.category = self.subcategory.category

        # If no title is provided, set the title to the subcategory name
        if not self.title:
            self.title = (
                self.subcategory.name
                if self.subcategory
                else self.category.name if self.category else "No Title"
            )

        if not self.type:
            if self.subcategory:
                self.type = self.subcategory.category.type
            elif self.category:
                self.type = self.category.type
            else:
                raise ValueError(
                    "Transaction type must be specified if no category or subcategory is provided."
                )

        # Update the account balance based on the transaction type and amount
        with db_transaction.atomic():
            previous = None
            if not self._state.adding:
                previous = type(self).objects.select_related("account").get(pk=self.pk)

            def signed_amount(transaction):
                return (
                    transaction.amount
                    if transaction.type == "income"
                    else -transaction.amount
                )

            if previous is None:
                self.account.balance += signed_amount(self)
                self.account.save()
            elif previous.account_id == self.account_id:
                self.account.balance += signed_amount(self) - signed_amount(previous)
                self.account.save()
            else:
                previous.account.balance -= signed_amount(previous)
                previous.account.save()
                self.account.balance += signed_amount(self)
                self.account.save()

            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with db_transaction.atomic():
            self.account.balance -= (
                self.amount if self.type == "income" else -self.amount
            )
            self.account.save()
            super().delete(*args, **kwargs)

    def __str__(self):
        return f"{self.account} | {self.title} | {self.amount}"


class Transfer(models.Model):
    """
    This model represents a transfer of funds between two accounts.
    Each transfer has a unique identifier, a source account, a destination account, an amount, and a timestamp.
    The save method is overridden to automatically update the balances of the source and destination accounts when a transfer is created. The delete method is also overridden to update the account balances when a transfer is deleted.
    Attributes:
        transfer_id (UUID): A unique identifier for the transfer.
        from_account (ForeignKey): A foreign key linking the transfer to the source account.
        to_account (ForeignKey): A foreign key linking the transfer to the destination account.
        amount (Decimal): The amount of the transfer.
        created_at (DateTime): The date and time when the transfer was created.

    The save method is overridden to automatically update the balances of the source and destination accounts when a transfer is created. The delete method is also overridden to update the account balances when a transfer is deleted.
    """

    transfer_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="outgoing_transfers"
    )
    to_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="incoming_transfers"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    destination_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    exchange_rate = models.DecimalField(
        max_digits=18, decimal_places=8, null=True, blank=True
    )
    transaction_date = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        with db_transaction.atomic():
            if self.from_account_id == self.to_account_id:
                raise ValueError("A transfer must use two different accounts.")
            if self.from_account.owner_id != self.to_account.owner_id:
                raise ValueError("A transfer's accounts must have the same owner.")
            currencies_differ = (
                self.from_account.currency != self.to_account.currency
            )
            if currencies_differ:
                if (
                    self.destination_amount is None
                    or self.destination_amount <= 0
                    or self.exchange_rate is None
                    or self.exchange_rate <= 0
                ):
                    raise ValueError(
                        "Cross-currency transfers require a positive destination amount and exchange rate."
                    )
                expected_destination = (
                    self.amount * self.exchange_rate
                ).quantize(Decimal("0.01"))
                if self.destination_amount != expected_destination:
                    raise ValueError(
                        "The destination amount must match the exchange rate."
                    )
            else:
                self.destination_amount = self.amount
                self.exchange_rate = None

            previous = None
            if not self._state.adding:
                previous = type(self).objects.select_for_update().get(
                    pk=self.pk
                )
            account_ids = {
                self.from_account_id,
                self.to_account_id,
            }
            if previous:
                account_ids.update(
                    {previous.from_account_id, previous.to_account_id}
                )
            accounts = {
                account.pk: account
                for account in (
                    Account.objects.select_for_update()
                    .filter(pk__in=account_ids)
                    .order_by("pk")
                )
            }
            if previous:
                accounts[previous.from_account_id].balance += previous.amount
                accounts[previous.to_account_id].balance -= (
                    previous.destination_amount or previous.amount
                )
            accounts[self.from_account_id].balance -= self.amount
            accounts[self.to_account_id].balance += self.destination_amount
            for account in accounts.values():
                account.save(update_fields=["balance"])
            self.from_account = accounts[self.from_account_id]
            self.to_account = accounts[self.to_account_id]
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with db_transaction.atomic():
            previous = type(self).objects.select_for_update().get(pk=self.pk)
            accounts = {
                account.pk: account
                for account in (
                    Account.objects.select_for_update()
                    .filter(pk__in=[previous.from_account_id, previous.to_account_id])
                    .order_by("pk")
                )
            }
            accounts[previous.from_account_id].balance += previous.amount
            accounts[previous.to_account_id].balance -= (
                previous.destination_amount or previous.amount
            )
            for account in accounts.values():
                account.save(update_fields=["balance"])
            super().delete(*args, **kwargs)

    def __str__(self):
        return f"Transfer from {self.from_account} to {self.to_account} | Amount: {self.amount}"


class SavingsGoal(models.Model):
    """
    This model represents a savings goal for a user, which is linked to an account.
    Each savings goal has a name, target amount, current amount, and is linked to an account.
    The current amount is updated automatically when transactions are created or deleted.
    Attributes:
        name (str): The name of the savings goal. You can use this field to identify the savings goal, such as "Vacation Fund" or "Emergency Fund".
        target_amount (Decimal): The target amount for the savings goal. This field represents the total amount that the user wants to save for this goal.
        current_amount (Decimal): The current amount saved towards the savings goal. This field is automatically updated when transactions are created or deleted, ensuring that the current amount always reflects the current state of the savings goal.
        account (ForeignKey): A foreign key linking the savings goal to an account. This allows for tracking of savings goals within specific accounts.
    """

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)
    target_amount = models.DecimalField(max_digits=10, decimal_places=2)
    current_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="savings_goals"
    )

    def __str__(self):
        return self.name


class Budget(models.Model):
    PERIOD_CHOICES = [
        ("custom", "Custom"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("yearly", "Yearly"),
    ]

    owner = models.ForeignKey(
        "accounts.CustomUser", on_delete=models.CASCADE, related_name="budgets"
    )
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    period = models.CharField(max_length=10, choices=PERIOD_CHOICES, default="monthly")
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="budgets",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date", "name"]

    def __str__(self):
        return self.name


class BudgetCategoryLimit(models.Model):
    budget = models.ForeignKey(
        Budget, on_delete=models.CASCADE, related_name="category_limits"
    )
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["budget", "category"], name="unique_budget_category_limit"
            )
        ]


class RecurringTransaction(models.Model):
    FREQUENCY_CHOICES = [
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("yearly", "Yearly"),
    ]

    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="recurring_transactions"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    type = models.CharField(
        max_length=10,
        choices=[("income", "Income"), ("expense", "Expense")],
        default="expense",
    )
    title = models.CharField(max_length=100)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True
    )
    subcategory = models.ForeignKey(
        SubCategory, on_delete=models.SET_NULL, null=True, blank=True
    )
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES)
    next_date = models.DateField(default=timezone.localdate)
    schedule_day = models.PositiveSmallIntegerField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["active", "next_date", "title"]

    def save(self, *args, **kwargs):
        if self.schedule_day is None and self.next_date:
            self.schedule_day = self.next_date.day
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class UserFinanceSettings(models.Model):
    owner = models.OneToOneField(
        "accounts.CustomUser", on_delete=models.CASCADE, related_name="finance_settings"
    )
    reporting_currency = models.CharField(max_length=3, default="EUR")
    payday_day = models.PositiveSmallIntegerField(default=25)

    def __str__(self):
        return f"{self.owner} finance settings"


class ExchangeRate(models.Model):
    owner = models.ForeignKey(
        "accounts.CustomUser", on_delete=models.CASCADE, related_name="exchange_rates"
    )
    from_currency = models.CharField(max_length=3)
    to_currency = models.CharField(max_length=3)
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    effective_date = models.DateField()
    source = models.CharField(max_length=100, default="User entered")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date", "from_currency", "to_currency"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "from_currency", "to_currency", "effective_date"],
                name="unique_user_exchange_rate_day",
            ),
            models.CheckConstraint(condition=models.Q(rate__gt=0), name="exchange_rate_positive"),
        ]

    def __str__(self):
        return f"1 {self.from_currency} = {self.rate} {self.to_currency}"


class Tag(models.Model):
    owner = models.ForeignKey(
        "accounts.CustomUser", on_delete=models.CASCADE, related_name="finance_tags"
    )
    name = models.CharField(max_length=40)
    color = models.CharField(max_length=7, default="#2f8f9d")

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="unique_user_finance_tag")
        ]

    def __str__(self):
        return self.name


class Debt(models.Model):
    DIRECTIONS = [("lent", "Money lent"), ("borrowed", "Money borrowed")]
    STATUSES = [("open", "Open"), ("settled", "Settled")]

    owner = models.ForeignKey(
        "accounts.CustomUser", on_delete=models.CASCADE, related_name="debts"
    )
    person = models.CharField(max_length=100)
    description = models.CharField(max_length=200, blank=True)
    direction = models.CharField(max_length=10, choices=DIRECTIONS)
    principal = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="EUR")
    opened_on = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="open")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["status", "due_date", "person"]
        constraints = [
            models.CheckConstraint(condition=models.Q(principal__gt=0), name="debt_principal_positive")
        ]

    @property
    def repaid(self):
        return self.repayments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

    @property
    def outstanding(self):
        return max(self.principal - self.repaid, Decimal("0.00"))

    def __str__(self):
        return f"{self.get_direction_display()} — {self.person}"


class DebtRepayment(models.Model):
    debt = models.ForeignKey(Debt, on_delete=models.CASCADE, related_name="repayments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    repayment_date = models.DateField(default=timezone.localdate)
    note = models.CharField(max_length=200, blank=True)
    transaction = models.ForeignKey(
        Transaction, on_delete=models.SET_NULL, null=True, blank=True, related_name="debt_repayments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-repayment_date", "-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="debt_repayment_positive")
        ]

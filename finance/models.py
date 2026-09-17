import uuid

from django.db import models, transaction as db_transaction


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

    def __str__(self):
        return self.name


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

    def __str__(self):
        return f"{self.category} | {self.name} | {self.category.type}"


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
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        with db_transaction.atomic():
            self.from_account.balance -= self.amount
            self.from_account.save()
            self.to_account.balance += self.amount
            self.to_account.save()
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with db_transaction.atomic():
            self.from_account.balance += self.amount
            self.from_account.save()
            self.to_account.balance -= self.amount
            self.to_account.save()
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

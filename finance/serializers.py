from decimal import Decimal
import re

from rest_framework import serializers
from django.db import transaction as db_transaction

from .models import *


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "description", "type"]
        read_only_fields = ["id"]

    def validate_name(self, value: str) -> str:
        name = value.strip()
        if len(name) < 3:
            raise serializers.ValidationError(
                "O nome da categoria deve ter pelo menos 3 caracteres."
            )
        return name
    
    def validate_type(self, value: str) -> str:
        if value not in ["income", "expense"]:
            raise serializers.ValidationError(
                "O tipo da categoria deve ser 'income' ou 'expense'."
            )
        return value


class SubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubCategory
        fields = ["id", "name", "category"]
        read_only_fields = ["id"]

    def validate_name(self, value: str) -> str:
        name = value.strip()
        if len(name) < 3:
            raise serializers.ValidationError(
                "O nome da subcategoria deve ter pelo menos 3 caracteres."
            )
        return name


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = [
            "id",
            "name",
            "balance",
            "currency",
            "color",
            "icon",
            "opening_balance",
            "opening_balance_date",
            "owner",
        ]
        read_only_fields = ["id", "owner"]

    def validate_name(self, value: str) -> str:
        name = value.strip()
        if len(name) < 3:
            raise serializers.ValidationError(
                "O nome deve ter pelo menos 3 caracteres."
            )
        return name


class BalanceCorrectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BalanceCorrection
        fields = ["id", "account", "amount", "description", "transaction_date"]
        read_only_fields = ["id"]

    def validate_amount(self, value: float) -> float:
        if value == 0:
            raise serializers.ValidationError(
                "O valor da atualização de saldo não pode ser zero."
            )
        return value

    def validate_account(self, value: Account) -> Account:
        if value.owner_id != self.context["request"].user.id:
            raise serializers.ValidationError("A conta não pertence ao utilizador.")
        return value


class TransactionSerializer(serializers.ModelSerializer):
    tags = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Tag.objects.all(), required=False
    )

    class Meta:
        model = Transaction
        fields = [
            "id",
            "account",
            "amount",
            "type",
            "title",
            "description",
            "transaction_date",
            "created_at",
            "category",
            "subcategory",
            "tags",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_amount(self, value: float) -> float:
        if value <= 0:
            raise serializers.ValidationError(
                "O valor da transação deve ser maior que zero."
            )
        return value

    def validate_account(self, value: Account) -> Account:
        if value.owner_id != self.context["request"].user.id:
            raise serializers.ValidationError("A conta não pertence ao utilizador.")
        return value

    def validate(self, data):
        user = self.context["request"].user
        category = data.get("category")
        subcategory = data.get("subcategory")

        if category and category.owner_id != user.id:
            raise serializers.ValidationError({"category": "A categoria não pertence ao utilizador."})
        if subcategory:
            category_owner_id = subcategory.category.owner_id
            if subcategory.owner_id not in {None, user.id} or category_owner_id != user.id:
                raise serializers.ValidationError({"subcategory": "A subcategoria não pertence ao utilizador."})
            if category and subcategory.category_id != category.id:
                raise serializers.ValidationError({"subcategory": "A subcategoria não pertence à categoria."})
            data["category"] = subcategory.category
        if any(tag.owner_id != user.id for tag in data.get("tags", [])):
            raise serializers.ValidationError({"tags": "A tag does not belong to this user."})
        return data


class TransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transfer
        fields = [
            "transfer_id",
            "from_account",
            "to_account",
            "amount",
            "destination_amount",
            "exchange_rate",
            "transaction_date",
            "created_at",
        ]
        read_only_fields = ["transfer_id", "created_at"]

    def validate_amount(self, value: float) -> float:
        if value <= 0:
            raise serializers.ValidationError(
                "O valor da transferência deve ser maior que zero."
            )
        return value

    def validate(self, data):
        user = self.context["request"].user
        from_account = data.get(
            "from_account",
            self.instance.from_account if self.instance else None,
        )
        to_account = data.get(
            "to_account",
            self.instance.to_account if self.instance else None,
        )
        amount = data.get("amount", self.instance.amount if self.instance else None)
        if (
            from_account is None
            or to_account is None
            or from_account.owner_id != user.id
            or to_account.owner_id != user.id
        ):
            raise serializers.ValidationError("As contas devem pertencer ao utilizador.")
        if from_account == to_account:
            raise serializers.ValidationError(
                "A conta de origem e a conta de destino não podem ser iguais."
            )
        currencies_differ = (
            from_account.currency != to_account.currency
        )
        if currencies_differ:
            destination_amount = data.get(
                "destination_amount",
                self.instance.destination_amount if self.instance else None,
            )
            exchange_rate = data.get(
                "exchange_rate",
                self.instance.exchange_rate if self.instance else None,
            )
            if (
                not destination_amount
                or not exchange_rate
                or destination_amount <= 0
                or exchange_rate <= 0
                or (
                    amount is not None
                    and destination_amount != (amount * exchange_rate).quantize(Decimal("0.01"))
                )
            ):
                raise serializers.ValidationError(
                    "Cross-currency transfers require a destination amount consistent with a positive exchange rate."
                )
        else:
            data["destination_amount"] = amount
            data["exchange_rate"] = None
        return data


class SavingsGoalSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavingsGoal
        fields = ["id", "name", "target_amount", "current_amount", "account"]
        read_only_fields = ["id", "current_amount"]

    def validate_name(self, value: str) -> str:
        name = value.strip()
        if len(name) < 3:
            raise serializers.ValidationError(
                "O nome da meta deve ter pelo menos 3 caracteres."
            )
        return name

    def validate_target_amount(self, value: float) -> float:
        if value <= 0:
            raise serializers.ValidationError(
                "O valor alvo da meta deve ser maior que zero."
            )
        return value


class BudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Budget
        fields = [
            "id",
            "name",
            "amount",
            "currency",
            "period",
            "start_date",
            "end_date",
            "category",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("O orçamento deve ser maior que zero.")
        return value

    def validate(self, data):
        user = self.context["request"].user
        category = data.get("category")
        if category and category.owner_id != user.id:
            raise serializers.ValidationError({"category": "A categoria não pertence ao utilizador."})
        currency = data.get(
            "currency",
            self.instance.currency if self.instance else "EUR",
        ).upper()
        if len(currency) != 3 or not currency.isalpha():
            raise serializers.ValidationError(
                {"currency": "Use a three-letter currency code."}
            )
        data["currency"] = currency
        if data.get("end_date") and data["end_date"] < data.get("start_date"):
            raise serializers.ValidationError({"end_date": "A data final deve ser posterior à inicial."})
        return data


class RecurringTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecurringTransaction
        fields = [
            "id",
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
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, data):
        user = self.context["request"].user
        account = data.get("account")
        category = data.get("category")
        subcategory = data.get("subcategory")
        if account and account.owner_id != user.id:
            raise serializers.ValidationError({"account": "A conta não pertence ao utilizador."})
        if category and category.owner_id != user.id:
            raise serializers.ValidationError({"category": "A categoria não pertence ao utilizador."})
        if subcategory:
            if subcategory.owner_id not in {None, user.id} or subcategory.category.owner_id != user.id:
                raise serializers.ValidationError({"subcategory": "A subcategoria não pertence ao utilizador."})
            if category and subcategory.category_id != category.id:
                raise serializers.ValidationError({"subcategory": "A subcategoria não pertence à categoria."})
            data["category"] = subcategory.category
        if data.get("amount") <= 0:
            raise serializers.ValidationError({"amount": "O valor deve ser maior que zero."})
        if data.get("end_date") and data["end_date"] < data.get("next_date"):
            raise serializers.ValidationError({"end_date": "A data final deve ser posterior à próxima ocorrência."})
        return data


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "color"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Tag name is required.")
        tags = Tag.objects.filter(owner=self.context["request"].user, name=name)
        if self.instance:
            tags = tags.exclude(pk=self.instance.pk)
        if tags.exists():
            raise serializers.ValidationError("A tag with this name already exists.")
        return name

    def validate_color(self, value):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise serializers.ValidationError("Use a six-digit hexadecimal color.")
        return value


class ExchangeRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExchangeRate
        fields = [
            "id",
            "from_currency",
            "to_currency",
            "rate",
            "effective_date",
            "source",
        ]
        read_only_fields = ["id"]

    def validate(self, data):
        from_currency = data.get(
            "from_currency",
            self.instance.from_currency if self.instance else "",
        ).upper()
        to_currency = data.get(
            "to_currency",
            self.instance.to_currency if self.instance else "",
        ).upper()
        rate = data.get("rate", self.instance.rate if self.instance else None)
        effective_date = data.get(
            "effective_date",
            self.instance.effective_date if self.instance else None,
        )
        if (
            len(from_currency) != 3
            or not from_currency.isalpha()
            or len(to_currency) != 3
            or not to_currency.isalpha()
            or from_currency == to_currency
        ):
            raise serializers.ValidationError(
                "Use two different three-letter currency codes."
            )
        if rate is None or rate <= 0:
            raise serializers.ValidationError({"rate": "Exchange rate must be positive."})
        rates = ExchangeRate.objects.filter(
            owner=self.context["request"].user,
            from_currency=from_currency,
            to_currency=to_currency,
            effective_date=effective_date,
        )
        if self.instance:
            rates = rates.exclude(pk=self.instance.pk)
        if rates.exists():
            raise serializers.ValidationError(
                "An exchange rate already exists for this currency pair and date."
            )
        data["from_currency"] = from_currency
        data["to_currency"] = to_currency
        return data


class UserFinanceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserFinanceSettings
        fields = ["reporting_currency"]

    def validate_reporting_currency(self, value):
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Use a three-letter currency code.")
        return value


class DebtSerializer(serializers.ModelSerializer):
    repaid = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    outstanding = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = Debt
        fields = [
            "id",
            "person",
            "description",
            "direction",
            "principal",
            "currency",
            "opened_on",
            "due_date",
            "status",
            "repaid",
            "outstanding",
        ]
        read_only_fields = ["id", "status", "repaid", "outstanding"]

    def validate(self, data):
        currency = data.get(
            "currency",
            self.instance.currency if self.instance else "EUR",
        ).upper()
        if len(currency) != 3 or not currency.isalpha():
            raise serializers.ValidationError(
                {"currency": "Use a three-letter currency code."}
            )
        data["currency"] = currency
        if data.get("principal", 0) <= 0:
            raise serializers.ValidationError({"principal": "Principal must be positive."})
        due_date = data.get("due_date", self.instance.due_date if self.instance else None)
        opened_on = data.get("opened_on", self.instance.opened_on if self.instance else None)
        if due_date and opened_on and due_date < opened_on:
            raise serializers.ValidationError(
                {"due_date": "Due date must not precede the opening date."}
            )
        return data

    def create(self, validated_data):
        return Debt.objects.create(owner=self.context["request"].user, **validated_data)


class DebtRepaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DebtRepayment
        fields = ["id", "debt", "amount", "repayment_date", "note", "transaction"]
        read_only_fields = ["id", "transaction"]

    def validate(self, data):
        debt = data["debt"]
        amount = data.get("amount")
        if debt.owner_id != self.context["request"].user.id:
            raise serializers.ValidationError(
                {"debt": "Debt record does not belong to this user."}
            )
        if amount is None or amount <= 0 or amount > debt.outstanding:
            raise serializers.ValidationError(
                {"amount": "Repayment must be positive and no greater than the outstanding amount."}
            )
        return data

    def create(self, validated_data):
        debt_id = validated_data["debt"].pk
        with db_transaction.atomic():
            debt = Debt.objects.select_for_update().get(
                pk=debt_id, owner=self.context["request"].user
            )
            amount = validated_data["amount"]
            outstanding_before = debt.outstanding
            if amount > outstanding_before:
                raise serializers.ValidationError(
                    {"amount": "Repayment cannot exceed the outstanding amount."}
                )
            repayment = DebtRepayment.objects.create(**validated_data)
            if amount == outstanding_before:
                debt.status = "settled"
                debt.save(update_fields=["status"])
            return repayment

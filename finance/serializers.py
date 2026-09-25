from rest_framework import serializers

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
        fields = ["id", "name", "balance", "owner"]
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
        return data


class TransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transfer
        fields = ["transfer_id", "from_account", "to_account", "amount", "transaction_date", "created_at"]
        read_only_fields = ["transfer_id", "created_at"]

    def validate_amount(self, value: float) -> float:
        if value <= 0:
            raise serializers.ValidationError(
                "O valor da transferência deve ser maior que zero."
            )
        return value

    def validate(self, data):
        user = self.context["request"].user
        if data["from_account"].owner_id != user.id or data["to_account"].owner_id != user.id:
            raise serializers.ValidationError("As contas devem pertencer ao utilizador.")
        if data["from_account"] == data["to_account"]:
            raise serializers.ValidationError(
                "A conta de origem e a conta de destino não podem ser iguais."
            )
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

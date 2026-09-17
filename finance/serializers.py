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


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ["id", "account", "amount", "description", "date"]
        read_only_fields = ["id"]

    def validate_amount(self, value: float) -> float:
        if value <= 0:
            raise serializers.ValidationError(
                "O valor da transação deve ser maior que zero."
            )
        return value

    def validate_account(self, value: Account) -> Account:
        if not value.exists() or not value.is_active:
            raise serializers.ValidationError(
                "A conta selecionada não existe ou está inativa."
            )
        return value


class TransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transfer
        fields = ["id", "from_account", "to_account", "amount", "date"]
        read_only_fields = ["id"]

    def validate_amount(self, value: float) -> float:
        if value <= 0:
            raise serializers.ValidationError(
                "O valor da transferência deve ser maior que zero."
            )
        return value

    def validate(self, data):
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

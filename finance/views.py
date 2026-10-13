from django.shortcuts import render

from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import *
from .serializers import *


class AccountViewSet(viewsets.ModelViewSet):
    serializer_class = AccountSerializer

    def get_queryset(self):
        return Account.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer

    def get_queryset(self):
        return Category.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class BalanceCorrectionViewSet(viewsets.ModelViewSet):
    serializer_class = BalanceCorrectionSerializer

    def get_queryset(self):
        return BalanceCorrection.objects.filter(account__owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save()


class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionSerializer

    def get_queryset(self):
        return Transaction.objects.filter(
            account__owner=self.request.user
        ).select_related("account", "category", "subcategory")


class TransferViewSet(viewsets.ModelViewSet):
    serializer_class = TransferSerializer

    def get_queryset(self):
        return Transfer.objects.filter(
            from_account__owner=self.request.user,
            to_account__owner=self.request.user,
        ).select_related("from_account", "to_account")


class BudgetViewSet(viewsets.ModelViewSet):
    serializer_class = BudgetSerializer

    def get_queryset(self):
        return Budget.objects.filter(owner=self.request.user).select_related("category")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class RecurringTransactionViewSet(viewsets.ModelViewSet):
    serializer_class = RecurringTransactionSerializer

    def get_queryset(self):
        return RecurringTransaction.objects.filter(
            account__owner=self.request.user
        ).select_related("account", "category", "subcategory")


class TagViewSet(viewsets.ModelViewSet):
    serializer_class = TagSerializer

    def get_queryset(self):
        return Tag.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ExchangeRateViewSet(viewsets.ModelViewSet):
    serializer_class = ExchangeRateSerializer

    def get_queryset(self):
        return ExchangeRate.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class DebtViewSet(viewsets.ModelViewSet):
    serializer_class = DebtSerializer

    def get_queryset(self):
        return Debt.objects.filter(owner=self.request.user)


class DebtRepaymentViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = DebtRepaymentSerializer

    def get_queryset(self):
        return DebtRepayment.objects.filter(debt__owner=self.request.user)


class UserFinanceSettingsView(APIView):
    def get(self, request):
        settings, _ = UserFinanceSettings.objects.get_or_create(owner=request.user)
        return Response(UserFinanceSettingsSerializer(settings).data)

    def put(self, request):
        settings, _ = UserFinanceSettings.objects.get_or_create(owner=request.user)
        serializer = UserFinanceSettingsSerializer(
            settings, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
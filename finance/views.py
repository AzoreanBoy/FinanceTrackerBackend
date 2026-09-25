from django.shortcuts import render

from rest_framework import viewsets

from .models import *
from .serializers import *


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
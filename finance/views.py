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
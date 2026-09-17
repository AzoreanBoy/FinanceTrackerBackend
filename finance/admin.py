from django.contrib import admin
from finance.models import *

# admin.site.register(Account)
admin.site.register(Category)
admin.site.register(SubCategory)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "balance", "owner")
    search_fields = ("name", "owner__username")


@admin.register(BalanceCorrection)
class BalanceCorrectionAdmin(admin.ModelAdmin):
    list_display = ("account", "amount", "description", "created_at")
    search_fields = ("account__name", "description")

    def delete_queryset(self, request, queryset):
        for balance_correction in queryset:
            balance_correction.delete()


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    def delete_queryset(self, request, queryset):
        for transaction in queryset:
            transaction.delete()


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = ("from_account", "to_account", "amount")
    search_fields = ("from_account__name", "to_account__name")

    def delete_queryset(self, request, queryset):
        for transfer in queryset:
            transfer.delete()


@admin.register(SavingsGoal)
class SavingsGoalAdmin(admin.ModelAdmin):
    list_display = ("name", "target_amount", "current_amount", "account")
    search_fields = ("name",)

    def delete_queryset(self, request, queryset):
        for goal in queryset:
            goal.delete()

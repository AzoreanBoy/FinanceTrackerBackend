from django.contrib import admin
from finance.models import *

# admin.site.register(Account)
admin.site.register(Category)
admin.site.register(SubCategory)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "balance", "owner")
    search_fields = ("name", "owner__username")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    def delete_queryset(self, request, queryset):
        for transaction in queryset:
            transaction.delete()


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = ("from_account", "to_account", "amount", "date")
    search_fields = ("from_account__name", "to_account__name")


@admin.register(SavingsGoal)
class SavingsGoalAdmin(admin.ModelAdmin):
    list_display = ("name", "target_amount", "current_amount", "deadline")
    search_fields = ("name",)

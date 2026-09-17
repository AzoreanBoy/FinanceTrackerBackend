from django.contrib import admin
from finance.models import *

# admin.site.register(Account)
admin.site.register(Category)
admin.site.register(SubCategory)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    def delete_queryset(self, request, queryset):
        for transaction in queryset:
            transaction.delete()


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "balance", "owner")
    search_fields = ("name", "owner__username")

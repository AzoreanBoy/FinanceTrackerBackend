from django.urls import path

from .web_views import (
    accounts_page,
    analytics_page,
    budgets_page,
    categories_page,
    csv_import_page,
    currencies_page,
    dashboard,
    debts_page,
    goals_page,
    recurring_page,
    tags_page,
    transaction_create,
    transaction_list,
    accounts_details,
)

app_name = "finance_web"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("finance/accounts/", accounts_page, name="accounts"),
    path("finance/analytics/", analytics_page, name="analytics"),
    path("finance/currencies/", currencies_page, name="currencies"),
    path("finance/budgets/", budgets_page, name="budgets"),
    path("finance/debts/", debts_page, name="debts"),
    path("finance/import/", csv_import_page, name="import"),
    path("finance/recurring/", recurring_page, name="recurring"),
    path("finance/categories/", categories_page, name="categories"),
    path("finance/tags/", tags_page, name="tags"),
    path("finance/goals/", goals_page, name="goals"),
    path("finance/transactions/new/", transaction_create, name="transaction_create"),
    path("finance/transactions/", transaction_list, name="transactions"),
    path("finance/accounts/<int:account_id>/", accounts_details, name="accounts_details"),
]
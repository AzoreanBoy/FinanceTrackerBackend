from django.urls import path

from .web_views import (
    accounts_page,
    analytics_page,
    budgets_page,
    categories_page,
    dashboard,
    goals_page,
    recurring_page,
    transaction_list,
)

app_name = "finance_web"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("finance/accounts/", accounts_page, name="accounts"),
    path("finance/analytics/", analytics_page, name="analytics"),
    path("finance/budgets/", budgets_page, name="budgets"),
    path("finance/recurring/", recurring_page, name="recurring"),
    path("finance/categories/", categories_page, name="categories"),
    path("finance/goals/", goals_page, name="goals"),
    path("finance/transactions/", transaction_list, name="transactions"),
]
from django.urls import include, path

from .routers import router
from .analytics_views import expense_analytics
from .views import UserFinanceSettingsView

urlpatterns = [
    path("", include(router.urls)),
    path("analytics/expenses/", expense_analytics, name="expense-analytics"),
    path("settings/", UserFinanceSettingsView.as_view(), name="finance-settings"),
]
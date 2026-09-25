from django.urls import path

from .web_views import settings_page

app_name = "accounts_web"

urlpatterns = [
    path("settings/", settings_page, name="settings"),
]
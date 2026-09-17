from django.urls import include, path
from accounts.routers import router

urlpatterns = [
    path("", include(router.urls)),
]

from rest_framework import routers
from accounts.views import UserViewSet      


router = routers.DefaultRouter()
router.register(r"users", UserViewSet, basename="user")

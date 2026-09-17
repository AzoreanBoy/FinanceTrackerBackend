from rest_framework.routers import DefaultRouter

from .views import BalanceCorrectionViewSet, CategoryViewSet

router = DefaultRouter()
# Register de ModelsViewSet with the router
router.register("categories", CategoryViewSet, basename="category")
router.register("balance-corrections", BalanceCorrectionViewSet, basename="balance-correction")
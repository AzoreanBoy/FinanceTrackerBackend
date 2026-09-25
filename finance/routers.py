from rest_framework.routers import DefaultRouter

from .views import (
	BalanceCorrectionViewSet,
	BudgetViewSet,
	CategoryViewSet,
	RecurringTransactionViewSet,
	TransactionViewSet,
	TransferViewSet,
)

router = DefaultRouter()
# Register de ModelsViewSet with the router
router.register("categories", CategoryViewSet, basename="category")
router.register("balance-corrections", BalanceCorrectionViewSet, basename="balance-correction")
router.register("transactions", TransactionViewSet, basename="transaction")
router.register("transfers", TransferViewSet, basename="transfer")
router.register("budgets", BudgetViewSet, basename="budget")
router.register("recurring-transactions", RecurringTransactionViewSet, basename="recurring-transaction")
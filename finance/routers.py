from rest_framework.routers import DefaultRouter

from .views import (
	AccountViewSet,
	BalanceCorrectionViewSet,
	BudgetViewSet,
	CategoryViewSet,
	DebtRepaymentViewSet,
	DebtViewSet,
	ExchangeRateViewSet,
	RecurringTransactionViewSet,
	TagViewSet,
	TransactionViewSet,
	TransferViewSet,
)

router = DefaultRouter()
# Register de ModelsViewSet with the router
router.register("accounts", AccountViewSet, basename="account")
router.register("categories", CategoryViewSet, basename="category")
router.register("balance-corrections", BalanceCorrectionViewSet, basename="balance-correction")
router.register("transactions", TransactionViewSet, basename="transaction")
router.register("transfers", TransferViewSet, basename="transfer")
router.register("budgets", BudgetViewSet, basename="budget")
router.register("recurring-transactions", RecurringTransactionViewSet, basename="recurring-transaction")
router.register("tags", TagViewSet, basename="tag")
router.register("exchange-rates", ExchangeRateViewSet, basename="exchange-rate")
router.register("debts", DebtViewSet, basename="debt")
router.register("debt-repayments", DebtRepaymentViewSet, basename="debt-repayment")
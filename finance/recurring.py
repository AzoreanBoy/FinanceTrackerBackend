from calendar import monthrange
from datetime import date, timedelta

from django.db import transaction as db_transaction
from django.utils import timezone

from .models import Account, RecurringTransaction, Transaction


def _next_occurrence(current, frequency, schedule_day):
    if frequency == "weekly":
        return current + timedelta(days=7)
    if frequency == "monthly":
        month_index = current.year * 12 + current.month
        year, zero_based_month = divmod(month_index, 12)
        month = zero_based_month + 1
        return date(
            year,
            month,
            min(schedule_day or current.day, monthrange(year, month)[1]),
        )
    if frequency == "yearly":
        year = current.year + 1
        return date(
            year,
            current.month,
            min(schedule_day or current.day, monthrange(year, current.month)[1]),
        )
    raise ValueError(f"Unsupported recurring frequency: {frequency}")


def process_due_recurring_transactions(user=None, through_date=None):
    through_date = through_date or timezone.localdate()
    recurring_items = RecurringTransaction.objects.filter(
        active=True,
        next_date__lte=through_date,
    ).select_related("account")
    if user is not None:
        recurring_items = recurring_items.filter(account__owner=user)

    created_count = 0
    for item in recurring_items.order_by("pk"):
        with db_transaction.atomic():
            item = RecurringTransaction.objects.select_for_update().get(pk=item.pk)
            while item.active and item.next_date <= through_date:
                if item.end_date and item.next_date > item.end_date:
                    item.active = False
                    break

                account = Account.objects.select_for_update().get(
                    pk=item.account_id
                )
                Transaction.objects.create(
                    account=account,
                    amount=item.amount,
                    type=item.type,
                    title=item.title,
                    category=item.category,
                    subcategory=item.subcategory,
                    transaction_date=item.next_date,
                )
                created_count += 1
                following_date = _next_occurrence(
                    item.next_date,
                    item.frequency,
                    item.schedule_day,
                )
                if item.end_date and following_date > item.end_date:
                    item.next_date = following_date
                    item.active = False
                    break
                item.next_date = following_date

            item.save(update_fields=["next_date", "active", "schedule_day"])

    return created_count

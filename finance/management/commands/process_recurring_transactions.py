from django.core.management.base import BaseCommand

from finance.recurring import process_due_recurring_transactions


class Command(BaseCommand):
    help = "Create ledger transactions for recurring items due today or earlier."

    def handle(self, *args, **options):
        created = process_due_recurring_transactions()
        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created} recurring transaction(s)."
            )
        )

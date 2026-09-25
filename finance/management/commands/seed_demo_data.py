from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import CustomUser
from finance.models import Account, Category, SavingsGoal, SubCategory, Transaction


class Command(BaseCommand):
    help = "Create a small, idempotent finance dataset for UI testing."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            user = CustomUser.objects.get(username=options["username"])
        except CustomUser.DoesNotExist as error:
            raise CommandError(f"User '{options['username']}' does not exist.") from error

        bank, _ = Account.objects.get_or_create(
            owner=user, name="Demo · Everyday account", defaults={"balance": Decimal("0")}
        )
        savings, _ = Account.objects.get_or_create(
            owner=user, name="Demo · Future fund", defaults={"balance": Decimal("0")}
        )

        category_data = {
            "Food": ["Groceries", "Coffee"],
            "Transport": ["Metro", "Fuel"],
            "Home": ["Utilities"],
            "Income": ["Salary"],
        }
        categories = {}
        for name, subcategory_names in category_data.items():
            category_type = "income" if name == "Income" else "expense"
            category, _ = Category.objects.get_or_create(
                owner=user,
                name=name,
                defaults={"type": category_type},
            )
            categories[name] = category
            for subcategory_name in subcategory_names:
                SubCategory.objects.get_or_create(
                    owner=user,
                    category=category,
                    name=subcategory_name,
                )

        entries = [
            ("Demo · Salary", Decimal("2450.00"), "income", bank, categories["Income"], "Salary"),
            ("Demo · Weekly groceries", Decimal("86.40"), "expense", bank, categories["Food"], "Groceries"),
            ("Demo · Morning coffee", Decimal("9.80"), "expense", bank, categories["Food"], "Coffee"),
            ("Demo · Metro pass", Decimal("40.00"), "expense", bank, categories["Transport"], "Metro"),
            ("Demo · Home utilities", Decimal("112.35"), "expense", bank, categories["Home"], "Utilities"),
            ("Demo · Fuel", Decimal("55.00"), "expense", bank, categories["Transport"], "Fuel"),
        ]
        for title, amount, transaction_type, account, category, subcategory_name in entries:
            subcategory = SubCategory.objects.get(
                owner=user, category=category, name=subcategory_name
            )
            Transaction.objects.get_or_create(
                account=account,
                title=title,
                defaults={
                    "amount": amount,
                    "type": transaction_type,
                    "category": category,
                    "subcategory": subcategory,
                },
            )

        SavingsGoal.objects.get_or_create(
            account=savings,
            name="Demo · Emergency cushion",
            defaults={
                "target_amount": Decimal("3000.00"),
                "current_amount": Decimal("780.00"),
            },
        )

        self.stdout.write(self.style.SUCCESS(f"Demo data ready for {user.username}."))
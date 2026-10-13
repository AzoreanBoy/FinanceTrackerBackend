import csv
import hashlib
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from .models import Account, Category, Transaction


MAX_IMPORT_BYTES = 2_000_000
MAX_IMPORT_ROWS = 10_000


def transaction_fingerprint(account_id, transaction_date, transaction_type, title, amount, category_id):
    parts = (
        account_id,
        transaction_date.isoformat(),
        transaction_type,
        title.strip().casefold(),
        format(amount, ".2f"),
        category_id or "",
    )
    return hashlib.sha256("\x1f".join(map(str, parts)).encode("utf-8")).hexdigest()


def preview_transactions_csv(user, uploaded_file):
    raw = uploaded_file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise ValueError("The CSV file must be 2 MB or smaller.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("The CSV file must use UTF-8 encoding.") from exc

    reader = csv.DictReader(io.StringIO(text))
    required_columns = {"date", "type", "title", "amount", "account"}
    columns = {column.strip().lower() for column in (reader.fieldnames or [])}
    if not required_columns.issubset(columns):
        missing = ", ".join(sorted(required_columns - columns))
        raise ValueError(f"Missing required CSV columns: {missing}.")

    accounts = {
        account.name.strip().casefold(): account
        for account in Account.objects.filter(owner=user)
    }
    categories = {
        category.name.strip().casefold(): category
        for category in Category.objects.filter(owner=user)
    }
    normalized_rows = []
    seen = set()
    for line_number, source in enumerate(reader, start=2):
        if line_number > MAX_IMPORT_ROWS + 1:
            raise ValueError(f"The CSV file must contain no more than {MAX_IMPORT_ROWS} data rows.")
        row = {
            (key or "").strip().lower(): (value or "").strip()
            for key, value in source.items()
        }
        errors = []
        try:
            transaction_date = date.fromisoformat(row.get("date", ""))
        except ValueError:
            transaction_date = None
            errors.append("Date must use YYYY-MM-DD.")

        transaction_type = row.get("type", "").lower()
        if transaction_type not in {"income", "expense"}:
            errors.append("Type must be income or expense.")

        title = row.get("title", "")
        if not title or len(title) > 50:
            errors.append("Title is required and must be at most 50 characters.")

        try:
            amount = Decimal(row.get("amount", ""))
            if (
                not amount.is_finite()
                or amount <= 0
                or amount.adjusted() > 7
                or amount.as_tuple().exponent < -2
            ):
                raise InvalidOperation
            amount = amount.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            amount = None
            errors.append("Amount must be a positive value with at most two decimals.")

        account = accounts.get(row.get("account", "").casefold())
        if account is None:
            errors.append("Account name does not match one of your accounts.")
        currency = row.get("currency", account.currency if account else "").upper()
        if account and currency != account.currency:
            errors.append(
                f"Currency {currency} does not match this account's {account.currency} currency."
            )

        category_name = row.get("category", "").casefold()
        category = categories.get(category_name) if category_name else None
        if category_name and category is None:
            errors.append("Category name does not match one of your categories.")

        fingerprint = None
        if not errors and transaction_date and amount is not None and account is not None:
            fingerprint = transaction_fingerprint(
                account.pk,
                transaction_date,
                transaction_type,
                title,
                amount,
                category.pk if category else None,
            )
            duplicate = fingerprint in seen or Transaction.objects.filter(
                account=account, import_fingerprint=fingerprint
            ).exists()
            seen.add(fingerprint)
            if duplicate:
                errors.append("Duplicate transaction; it will not be imported.")

        normalized_rows.append(
            {
                "line": line_number,
                "date": transaction_date.isoformat() if transaction_date else row.get("date", ""),
                "type": transaction_type,
                "title": title,
                "amount": str(amount) if amount is not None else row.get("amount", ""),
                "account_id": account.pk if account else None,
                "account_name": account.name if account else row.get("account", ""),
                "currency": currency,
                "category_id": category.pk if category else None,
                "category_name": category.name if category else "",
                "fingerprint": fingerprint,
                "errors": errors,
            }
        )

    return normalized_rows

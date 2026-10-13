from decimal import Decimal

from .models import ExchangeRate


class ExchangeRateBook:
    def __init__(self, user, through_date):
        self.rates = {}
        entries = ExchangeRate.objects.filter(
            owner=user,
            effective_date__lte=through_date,
        ).order_by("from_currency", "to_currency", "-effective_date")
        for entry in entries:
            self.rates.setdefault(
                (entry.from_currency, entry.to_currency), []
            ).append((entry.effective_date, entry.rate))

    def rate_for(self, from_currency, to_currency, on_date):
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()
        if from_currency == to_currency:
            return Decimal("1"), on_date

        direct = self._latest_rate(from_currency, to_currency, on_date)
        inverse = self._latest_rate(to_currency, from_currency, on_date)
        if direct and (not inverse or direct[1] >= inverse[1]):
            return direct[0], direct[1]
        if inverse:
            return Decimal("1") / inverse[0], inverse[1]
        return None, None

    def _latest_rate(self, from_currency, to_currency, on_date):
        for rate_date, rate in self.rates.get((from_currency, to_currency), ()):
            if rate_date <= on_date:
                return rate, rate_date
        return None

    def convert(self, amount, from_currency, to_currency, on_date):
        rate, rate_date = self.rate_for(
            from_currency, to_currency, on_date
        )
        if rate is None:
            return None, None, None
        return (amount * rate).quantize(Decimal("0.01")), rate, rate_date


def exchange_rate_for(user, from_currency, to_currency, on_date):
    book = ExchangeRateBook(user, on_date)
    return book.rate_for(from_currency, to_currency, on_date)


def convert_amount(user, amount, from_currency, to_currency, on_date):
    rate, rate_date = exchange_rate_for(
        user, from_currency, to_currency, on_date
    )
    if rate is None:
        return None, None, None
    converted = (amount * rate).quantize(Decimal("0.01"))
    return converted, rate, rate_date

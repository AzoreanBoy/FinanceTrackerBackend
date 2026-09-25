from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0012_transaction_transaction_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="balancecorrection",
            name="transaction_date",
            field=models.DateField(default=timezone.localdate),
        ),
        migrations.AddField(
            model_name="transfer",
            name="transaction_date",
            field=models.DateField(default=timezone.localdate),
        ),
    ]
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0011_backfill_subcategory_owner"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="transaction_date",
            field=models.DateField(default=timezone.localdate),
        ),
    ]
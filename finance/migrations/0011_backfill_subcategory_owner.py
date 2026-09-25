from django.db import migrations


def assign_category_owners(apps, schema_editor):
    SubCategory = apps.get_model("finance", "SubCategory")

    for subcategory in SubCategory.objects.filter(owner__isnull=True).select_related("category"):
        if subcategory.category.owner_id:
            subcategory.owner_id = subcategory.category.owner_id
            subcategory.save(update_fields=["owner"])


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0010_balancecorrection"),
    ]

    operations = [
        migrations.RunPython(assign_category_owners, migrations.RunPython.noop),
    ]
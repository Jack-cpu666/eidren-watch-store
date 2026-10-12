from django.db import migrations


def hide_demo_products(apps, schema_editor):
    apps.get_model("shop", "Product").objects.filter(is_demo=True).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [("shop", "0004_publish_eidren_catalog")]
    operations = [migrations.RunPython(hide_demo_products, migrations.RunPython.noop)]

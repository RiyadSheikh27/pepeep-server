# Generated migration to fix MenuItem.category foreign key reference

import django.db.models.deletion
from django.db import migrations, models


def clear_invalid_categories(apps, schema_editor):
    """Clear category IDs that don't exist in RestaurantCategory"""
    MenuItem = apps.get_model('food_menus', 'MenuItem')
    # Set all category_id to NULL since they're pointing to wrong table
    MenuItem.objects.all().update(category_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0006_alter_restaurantcategory_options_and_more'),
        ('food_menus', '0003_menuitem_category'),
    ]

    operations = [
        migrations.RunPython(clear_invalid_categories),
        migrations.AlterField(
            model_name='menuitem',
            name='category',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='items', to='restaurants.restaurantcategory'),
        ),
    ]

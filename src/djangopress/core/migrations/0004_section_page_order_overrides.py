# Generated migration for adding page_order_overrides field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_section_is_global'),
    ]

    operations = [
        migrations.AddField(
            model_name='section',
            name='page_order_overrides',
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text='Per-page order overrides for global sections: {"home": 1, "sobre-nos": 2, ...}. Only used when is_global=True.',
                verbose_name='Page Order Overrides'
            ),
        ),
    ]

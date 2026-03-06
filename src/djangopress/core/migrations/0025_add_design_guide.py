from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0024_add_domain_to_sitesettings'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitesettings',
            name='design_guide',
            field=models.TextField(blank=True, default='', help_text='Markdown document describing UI patterns, component styles, and design rules for AI generation.', verbose_name='Design Guide'),
        ),
    ]

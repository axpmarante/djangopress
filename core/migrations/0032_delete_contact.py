from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0031_migrate_contact_to_formsubmission'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Contact',
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0047_pageversion_kind'),
    ]

    operations = [
        migrations.AddField(
            model_name='siteimage',
            name='original_image',
            field=models.CharField(blank=True, default='', help_text='Storage name of the file before the first edit in the image editor, kept for "Restore original".', max_length=255, verbose_name='Original image'),
        ),
    ]

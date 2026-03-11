# Originally created a "Homepage Clone" page — now a no-op.
# Kept as empty migration to preserve migration chain.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0020_rebuild_section_json_first'),
    ]

    operations = []

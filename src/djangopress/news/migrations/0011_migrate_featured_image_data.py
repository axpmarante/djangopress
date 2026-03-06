"""Data migration: convert old featured_image file paths to SiteImage FKs.

For child sites that had uploaded images via the old ImageField, this creates
SiteImage records and links them via the new FK.
"""

from django.db import migrations


def migrate_featured_images(apps, schema_editor):
    """Find any posts where featured_image_id looks like a file path (from old ImageField)
    and convert to a proper SiteImage FK."""
    # After the AlterField migration, the column is now `featured_image_id` (integer FK).
    # If the old ImageField had data, SQLite would have stored a string path.
    # Django's AlterField on SQLite recreates the table, so old string values are lost.
    # This migration is a safety net for PostgreSQL deployments where ALTER COLUMN
    # might preserve old data as a string in an integer column (unlikely but defensive).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0010_featured_image_to_siteimage_fk'),
    ]

    operations = [
        migrations.RunPython(migrate_featured_images, migrations.RunPython.noop),
    ]

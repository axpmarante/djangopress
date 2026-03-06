"""
Management command to migrate media files between GCS folders when the domain changes.

Usage:
    python manage.py migrate_storage_folder                    # from 'default' to current domain
    python manage.py migrate_storage_folder --from old-domain  # from specific folder
    python manage.py migrate_storage_folder --dry-run          # preview without copying
"""

from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Copy media files from one GCS folder to another (e.g. after changing SiteSettings.domain)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--from',
            dest='from_folder',
            default='default',
            help='Source folder name (default: "default")',
        )
        parser.add_argument(
            '--to',
            dest='to_folder',
            default='',
            help='Destination folder name (default: current SiteSettings.domain)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='List files that would be copied without actually copying them',
        )

    def handle(self, *args, **options):
        bucket_name = getattr(settings, 'GS_BUCKET_NAME', None)
        if not bucket_name:
            self.stderr.write(self.style.ERROR(
                'GS_BUCKET_NAME is not configured. This command only works with Google Cloud Storage.'
            ))
            return

        from_folder = options['from_folder']
        to_folder = options['to_folder']
        dry_run = options['dry_run']

        if not to_folder:
            from core.models import SiteSettings
            site_settings = SiteSettings.objects.first()
            if site_settings and site_settings.domain:
                to_folder = site_settings.domain.replace('.', '-').replace(':', '-')
            else:
                self.stderr.write(self.style.ERROR(
                    'No destination folder specified and SiteSettings.domain is empty. '
                    'Use --to <folder> or set the domain in SiteSettings first.'
                ))
                return

        if from_folder == to_folder:
            self.stderr.write(self.style.WARNING(
                f'Source and destination are the same: "{from_folder}". Nothing to do.'
            ))
            return

        self.stdout.write(f'Migrating files from "{from_folder}/" to "{to_folder}/" in bucket "{bucket_name}"')
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no files will be copied'))

        try:
            from google.cloud import storage as gcs_storage
            client = gcs_storage.Client()
            bucket = client.bucket(bucket_name)
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Failed to connect to GCS: {e}'))
            return

        prefix = f'{from_folder}/'
        blobs = list(bucket.list_blobs(prefix=prefix))

        if not blobs:
            self.stdout.write(self.style.WARNING(f'No files found in "{from_folder}/"'))
            return

        self.stdout.write(f'Found {len(blobs)} file(s) to migrate')

        copied = 0
        skipped = 0
        for blob in blobs:
            relative_path = blob.name[len(prefix):]
            if not relative_path:
                continue

            new_name = f'{to_folder}/{relative_path}'

            # Check if destination already exists
            dest_blob = bucket.blob(new_name)
            if dest_blob.exists():
                self.stdout.write(f'  SKIP (exists): {new_name}')
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(f'  WOULD COPY: {blob.name} -> {new_name}')
                copied += 1
            else:
                bucket.copy_blob(blob, bucket, new_name)
                self.stdout.write(f'  COPIED: {blob.name} -> {new_name}')
                copied += 1

        action = 'Would copy' if dry_run else 'Copied'
        self.stdout.write(self.style.SUCCESS(
            f'\n{action} {copied} file(s), skipped {skipped} (already exist)'
        ))

        if not dry_run and copied > 0:
            self.stdout.write(self.style.WARNING(
                f'\nNote: Original files in "{from_folder}/" were NOT deleted. '
                f'Verify the migration, then delete manually if desired.'
            ))

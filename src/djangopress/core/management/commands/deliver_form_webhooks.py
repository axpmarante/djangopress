"""Deliver the form webhooks that are pending and due. Safe to run from a cron every few minutes."""

from django.core.management.base import BaseCommand

from djangopress.core.services import webhooks


class Command(BaseCommand):
    help = "Delivers the pending form webhooks that are due (new ones, and retries whose wait is over)."

    def handle(self, *args, **options):
        delivered = webhooks.deliver_due()
        self.stdout.write(f'{delivered} submissões entregues')

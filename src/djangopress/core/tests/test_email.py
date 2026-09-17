"""Tests for core.email — form notification delivery."""

from django.core import mail
from django.test import TestCase, override_settings
from djangopress.core.email import send_form_notification
from djangopress.core.models import DynamicForm, FormSubmission, SiteSettings


class FormNotificationBccTest(TestCase):

    def setUp(self):
        DynamicForm.objects.all().delete()
        settings_obj = SiteSettings.load()
        settings_obj.contact_email = 'client@example.com'
        settings_obj.save()
        self.form = DynamicForm.objects.create(
            name='Contact', slug='contact',
            fields_schema=[{'name': 'email', 'type': 'email', 'label': 'Email'}],
        )
        self.submission = FormSubmission.objects.create(
            form=self.form, data={'email': 'visitor@example.com'},
        )

    @override_settings(FORM_NOTIFICATION_BCC='agency@example.com')
    def test_agency_copy_is_bcc_when_configured(self):
        self.assertTrue(send_form_notification(self.form, self.submission))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['client@example.com'])
        self.assertEqual(mail.outbox[0].bcc, ['agency@example.com'])

    @override_settings(FORM_NOTIFICATION_BCC='')
    def test_no_bcc_when_not_configured(self):
        self.assertTrue(send_form_notification(self.form, self.submission))
        self.assertEqual(mail.outbox[0].bcc, [])

    @override_settings(FORM_NOTIFICATION_BCC=' agency@example.com , second@example.com ')
    def test_multiple_agency_addresses_are_split_and_trimmed(self):
        self.assertTrue(send_form_notification(self.form, self.submission))
        self.assertEqual(
            mail.outbox[0].bcc, ['agency@example.com', 'second@example.com']
        )

    @override_settings(FORM_NOTIFICATION_BCC='agency@example.com')
    def test_bcc_is_not_sent_without_a_primary_recipient(self):
        settings_obj = SiteSettings.load()
        settings_obj.contact_email = ''
        settings_obj.save()
        self.assertFalse(send_form_notification(self.form, self.submission))
        self.assertEqual(len(mail.outbox), 0)

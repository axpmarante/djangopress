"""Back-office side of the form webhook: the two settings on a form, the Webhook
column on its submissions, and the "Resend" button."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase, override_settings
from django.urls import reverse

from djangopress.core.models import DynamicForm, FormSubmission, SiteSettings
from djangopress.core.services import webhooks

Status = FormSubmission.WebhookStatus

URL = 'https://crm.example.test/api/inbound/forms/0b6e/'
SECRET = 'whsec_0123456789abcdefWXYZ'


class WebhookUITestCase(TestCase):

    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.save()
        User = get_user_model()
        self.staff = User.objects.create_user('sara', 'sara@example.com', 'x', is_staff=True)
        self.visitor = User.objects.create_user('visitor', 'v@example.com', 'x')   # logged in, not staff
        self.form = DynamicForm.objects.create(name='Pedido de proposta', slug='proposta')
        self.client.force_login(self.staff)

    def edit_url(self):
        return reverse('backoffice:form_edit', args=[self.form.pk])

    def post_edit(self, **extra):
        data = {'name': self.form.name, 'slug': self.form.slug, 'is_active': 'on'}
        data.update(extra)
        return self.client.post(self.edit_url(), data)

    def message_texts(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]


class FormEditWebhookTest(WebhookUITestCase):

    def test_staff_can_set_webhook_url_and_secret(self):
        response = self.post_edit(webhook_url=URL, webhook_secret=SECRET)
        self.assertRedirects(response, self.edit_url())
        self.form.refresh_from_db()
        self.assertEqual(self.form.webhook_url, URL)
        self.assertEqual(self.form.webhook_secret, SECRET)

    def test_blank_secret_on_save_keeps_existing(self):
        self.form.webhook_url = URL
        self.form.webhook_secret = SECRET
        self.form.save()
        new_url = 'https://crm.example.test/api/inbound/forms/other/'
        self.post_edit(webhook_url=new_url, webhook_secret='')
        self.form.refresh_from_db()
        self.assertEqual(self.form.webhook_url, new_url)
        self.assertEqual(self.form.webhook_secret, SECRET)

    def test_a_new_secret_replaces_the_old_one(self):
        self.form.webhook_url = URL
        self.form.webhook_secret = SECRET
        self.form.save()
        self.post_edit(webhook_url=URL, webhook_secret='another-secret-9999')
        self.form.refresh_from_db()
        self.assertEqual(self.form.webhook_secret, 'another-secret-9999')

    def test_blank_url_turns_the_webhook_off(self):
        self.form.webhook_url = URL
        self.form.webhook_secret = SECRET
        self.form.save()
        self.post_edit(webhook_url='', webhook_secret='')
        self.form.refresh_from_db()
        self.assertEqual(self.form.webhook_url, '')

    def test_secret_is_masked_in_page(self):
        self.form.webhook_url = URL
        self.form.webhook_secret = SECRET
        self.form.save()
        response = self.client.get(self.edit_url())
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn(SECRET, html)
        self.assertNotIn(SECRET[:-4], html)
        self.assertIn(SECRET[-4:], html)               # last 4 characters stay visible
        self.assertIn(URL, html)
        self.assertEqual(response.context['webhook_secret_masked'][-4:], SECRET[-4:])

    def test_short_secret_is_not_revealed_at_all(self):
        self.form.webhook_secret = 'abc12'
        self.form.save()
        response = self.client.get(self.edit_url())
        self.assertNotContains(response, 'abc12')
        masked = response.context['webhook_secret_masked']
        self.assertTrue(masked)
        self.assertEqual(set(masked), {'\u2022'})            # bullets only, no tail

    def test_page_without_a_secret_says_none_is_set(self):
        response = self.client.get(self.edit_url())
        self.assertEqual(response.context['webhook_secret_masked'], '')
        self.assertContains(response, 'Webhook URL')
        self.assertContains(response, 'Webhook Secret')

    @override_settings(FORM_WEBHOOK_SECRET='from-env-secret')
    def test_page_says_the_environment_secret_is_used_when_the_form_has_none(self):
        response = self.client.get(self.edit_url())
        self.assertTrue(response.context['webhook_secret_from_env'])
        self.assertContains(response, 'FORM_WEBHOOK_SECRET')
        self.assertNotContains(response, 'from-env-secret')

    @override_settings(FORM_WEBHOOK_SECRET='from-env-secret')
    def test_page_does_not_claim_the_environment_secret_when_the_form_has_its_own(self):
        self.form.webhook_secret = 'own-secret-123456'
        self.form.save()
        response = self.client.get(self.edit_url())
        self.assertFalse(response.context['webhook_secret_from_env'])

    def test_invalid_url_is_refused_and_nothing_changes(self):
        self.form.webhook_url = URL
        self.form.webhook_secret = SECRET
        self.form.save()
        for bad in ('not a url', 'javascript:alert(1)', 'ftp://crm.example.test/x', 'http://'):
            with self.subTest(url=bad):
                response = self.post_edit(webhook_url=bad, webhook_secret='changed-secret-0000', name='Renamed')
                self.assertRedirects(response, self.edit_url())
                self.assertTrue(any('Webhook URL' in t for t in self.message_texts(response)))
                self.form.refresh_from_db()
                self.assertEqual(self.form.webhook_url, URL)
                self.assertEqual(self.form.webhook_secret, SECRET)
                self.assertEqual(self.form.name, 'Pedido de proposta')

    def test_secret_longer_than_the_column_is_refused(self):
        response = self.post_edit(webhook_url=URL, webhook_secret='x' * 129)
        self.assertTrue(any('Webhook Secret' in t for t in self.message_texts(response)))
        self.form.refresh_from_db()
        self.assertEqual(self.form.webhook_secret, '')

    def test_non_staff_cannot_change_the_webhook_and_does_not_see_it(self):
        self.form.webhook_url = URL
        self.form.webhook_secret = SECRET
        self.form.save()
        self.client.force_login(self.visitor)

        html = self.client.get(self.edit_url()).content.decode()
        self.assertNotIn('Webhook Secret', html)
        self.assertNotIn(URL, html)
        self.assertNotIn(SECRET[-4:], html)

        self.post_edit(webhook_url='https://evil.example.test/', webhook_secret='stolen-secret-0000', name='Renamed')
        self.form.refresh_from_db()
        self.assertEqual(self.form.name, 'Renamed')            # the rest of the form still saves as before
        self.assertEqual(self.form.webhook_url, URL)
        self.assertEqual(self.form.webhook_secret, SECRET)


class ResendWebhookTest(WebhookUITestCase):

    def setUp(self):
        super().setUp()
        self.form.webhook_url = URL
        self.form.webhook_secret = SECRET
        self.form.save()
        self.submission = FormSubmission.objects.create(
            form=self.form, data={'email': 'ana@example.pt'},
            webhook_status=Status.FAILED, webhook_attempts=6, webhook_last_error='HTTP 500 Server Error',
        )
        self.url = reverse('backoffice:submission_webhook_resend', args=[self.submission.pk])
        self.list_url = reverse('backoffice:form_submissions', args=[self.form.pk])

    def test_resend_requires_staff_and_calls_resend(self):
        with patch.object(webhooks, 'resend', return_value=True) as resend:
            self.client.logout()
            anonymous = self.client.post(self.url)
            self.assertEqual(anonymous.status_code, 302)
            self.assertIn('/login/', anonymous['Location'])

            self.client.force_login(self.visitor)
            self.assertIn(self.client.post(self.url).status_code, (302, 403))
            resend.assert_not_called()

            self.client.force_login(self.staff)
            response = self.client.post(self.url)
            self.assertRedirects(response, self.list_url)
            resend.assert_called_once()
            self.assertEqual(resend.call_args.args[0].pk, self.submission.pk)

    def test_resend_is_post_only(self):
        with patch.object(webhooks, 'resend') as resend:
            self.assertEqual(self.client.get(self.url).status_code, 405)
            resend.assert_not_called()

    def test_delivered_resend_says_so(self):
        with patch.object(webhooks, 'resend', return_value=True):
            response = self.client.post(self.url)
        self.assertTrue(any('delivered' in t.lower() for t in self.message_texts(response)))

    def test_failed_resend_shows_the_error(self):
        def fail(submission):
            submission.webhook_last_error = 'HTTP 503 Service Unavailable'
            return False
        with patch.object(webhooks, 'resend', side_effect=fail):
            response = self.client.post(self.url)
        texts = self.message_texts(response)
        self.assertTrue(any('HTTP 503 Service Unavailable' in t for t in texts))

    def test_resend_really_delivers_through_the_service(self):
        # No patching of the service: only the network is replaced.
        with patch.object(webhooks, '_post', return_value=None):
            self.client.post(self.url)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.webhook_status, Status.DELIVERED)
        self.assertEqual(self.submission.webhook_attempts, 0)

    def test_form_without_a_webhook_url_does_not_call_resend(self):
        self.form.webhook_url = ''
        self.form.save()
        with patch.object(webhooks, 'resend') as resend:
            response = self.client.post(self.url)
        resend.assert_not_called()
        self.assertRedirects(response, self.list_url)
        self.assertTrue(any('no webhook URL' in t for t in self.message_texts(response)))

    def test_unknown_submission_is_a_404(self):
        response = self.client.post(reverse('backoffice:submission_webhook_resend', args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_redirect_keeps_the_list_page(self):
        with patch.object(webhooks, 'resend', return_value=True):
            response = self.client.post(self.url, {'page': '2'})
        self.assertRedirects(response, f'{self.list_url}?page=2', fetch_redirect_response=False)
        with patch.object(webhooks, 'resend', return_value=True):
            response = self.client.post(self.url, {'page': 'x'})
        self.assertRedirects(response, self.list_url, fetch_redirect_response=False)


class SubmissionsListWebhookTest(WebhookUITestCase):

    def setUp(self):
        super().setUp()
        self.form.webhook_url = URL
        self.form.webhook_secret = SECRET
        self.form.save()
        self.list_url = reverse('backoffice:form_submissions', args=[self.form.pk])

    def make(self, **kwargs):
        return FormSubmission.objects.create(form=self.form, data={'email': 'ana@example.pt'}, **kwargs)

    def test_submissions_list_shows_webhook_status(self):
        self.make(webhook_status=Status.DELIVERED)
        self.make(webhook_status=Status.PENDING, webhook_attempts=2, webhook_last_error='URLError: timed out')
        self.make(webhook_status=Status.FAILED, webhook_attempts=6, webhook_last_error='HTTP 500 Server Error')
        self.make()    # no webhook
        response = self.client.get(self.list_url)
        self.assertContains(response, '>Webhook<')
        self.assertContains(response, 'Delivered')
        self.assertContains(response, 'Pending')
        self.assertContains(response, 'Failed')
        self.assertContains(response, 'Failed attempts 2/6')
        self.assertContains(response, 'Failed attempts 6/6')
        self.assertContains(response, 'URLError: timed out')
        self.assertContains(response, 'HTTP 500 Server Error')
        # the secret is not part of this page
        self.assertNotContains(response, SECRET)

    def test_the_error_is_escaped(self):
        self.make(webhook_status=Status.FAILED, webhook_attempts=6, webhook_last_error='<script>alert(1)</script>')
        response = self.client.get(self.list_url)
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')

    def test_resend_button_for_staff_only_and_only_with_a_url(self):
        submission = self.make(webhook_status=Status.FAILED, webhook_attempts=6)
        resend_url = reverse('backoffice:submission_webhook_resend', args=[submission.pk])

        self.assertContains(self.client.get(self.list_url), resend_url)

        self.client.force_login(self.visitor)
        self.assertNotContains(self.client.get(self.list_url), resend_url)

        self.client.force_login(self.staff)
        self.form.webhook_url = ''
        self.form.save()
        self.assertNotContains(self.client.get(self.list_url), resend_url)

    def test_list_without_a_webhook_has_no_noise(self):
        self.form.webhook_url = ''
        self.form.save()
        self.make()
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Failed attempts')

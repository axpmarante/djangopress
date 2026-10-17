"""The Django admin never shows a form's webhook secret (core.admin.DynamicFormAdmin)."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.forms.models import model_to_dict
from django.test import RequestFactory, TestCase
from django.urls import reverse

from djangopress.core.admin import DynamicFormAdmin
from djangopress.core.models import DynamicForm

SECRET = 'whsec-Zx81-never-shown-QpL4'


class DynamicFormAdminSecretTest(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_superuser('admin', 'admin@example.com', 'x')
        self.client.force_login(self.user)
        self.form = DynamicForm.objects.create(
            name='Pedido', slug='pedido', webhook_url='https://crm.example.test/hook/', webhook_secret=SECRET,
        )

    def _admin_form(self, **changes):
        """The admin's form for self.form, bound to what the change page would POST, with `changes`."""
        model_admin = DynamicFormAdmin(DynamicForm, admin.site)
        request = RequestFactory().get('/')
        request.user = self.user
        form_class = model_admin.get_form(request, self.form)
        data = {key: value for key, value in model_to_dict(self.form).items() if value is not None}
        for key in ('fields_schema', 'success_message_i18n', 'confirmation_subject_i18n', 'confirmation_body_i18n'):
            data[key] = '[]' if key == 'fields_schema' else '{}'
        data['webhook_secret'] = ''  # what a browser sends back for an empty password box
        data.update(changes)
        return form_class(data=data, instance=self.form)

    def test_the_change_page_does_not_show_the_secret(self):
        page = self.client.get(reverse('admin:core_dynamicform_change', args=[self.form.pk])).content.decode()

        self.assertNotIn(SECRET, page)
        self.assertIn('type="password" name="webhook_secret"', page)
        self.assertIn('Leave blank to keep', page)

    def test_the_list_does_not_show_the_secret(self):
        page = self.client.get(reverse('admin:core_dynamicform_changelist')).content.decode()
        self.assertNotIn(SECRET, page)

    def test_a_blank_secret_keeps_the_current_one(self):
        form = self._admin_form(name='Pedido de proposta')

        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn('webhook_secret', form.changed_data)  # the admin's history does not say it changed
        form.save()
        self.form.refresh_from_db()
        self.assertEqual((self.form.name, self.form.webhook_secret), ('Pedido de proposta', SECRET))

    def test_a_new_secret_replaces_it(self):
        form = self._admin_form(webhook_secret='  a-new-secret  ')

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIn('webhook_secret', form.changed_data)
        form.save()
        self.form.refresh_from_db()
        self.assertEqual(self.form.webhook_secret, 'a-new-secret')

    def test_saving_through_the_change_page_keeps_the_secret(self):
        url = reverse('admin:core_dynamicform_change', args=[self.form.pk])
        data = {
            'name': 'Pedido', 'slug': 'pedido', 'notification_email': '', 'fields_schema': '[]',
            'success_message_i18n': '{}', 'confirmation_subject_i18n': '{}', 'confirmation_body_i18n': '{}',
            'webhook_url': 'https://crm.example.test/hook/', 'webhook_secret': '', 'is_active': 'on',
        }

        response = self.client.post(url, data)

        self.assertEqual(response.status_code, 302, response.content.decode()[:2000])
        self.form.refresh_from_db()
        self.assertEqual(self.form.webhook_secret, SECRET)

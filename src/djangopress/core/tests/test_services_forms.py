"""Tests for core.services.forms — FormService."""

from django.test import TestCase
from djangopress.core.models import DynamicForm, FormSubmission, SiteSettings
from djangopress.core.services.forms import FormService


class FormServiceListTest(TestCase):

    def setUp(self):
        DynamicForm.objects.all().delete()

    def test_list_empty(self):
        result = FormService.list()
        self.assertTrue(result['success'])
        self.assertEqual(result['forms'], [])

    def test_list_with_forms(self):
        DynamicForm.objects.create(name='Contact', slug='contact')
        DynamicForm.objects.create(name='Quote', slug='quote')
        result = FormService.list()
        self.assertTrue(result['success'])
        self.assertEqual(len(result['forms']), 2)

    def test_list_includes_submission_count(self):
        form = DynamicForm.objects.create(name='Contact', slug='contact')
        FormSubmission.objects.create(form=form, data={'name': 'Test'})
        FormSubmission.objects.create(form=form, data={'name': 'Test2'})
        result = FormService.list()
        self.assertEqual(result['forms'][0]['submission_count'], 2)


class FormServiceCreateTest(TestCase):

    def setUp(self):
        DynamicForm.objects.all().delete()

    def test_create(self):
        result = FormService.create(
            name='Contact',
            slug='contact',
            notification_email='admin@test.com',
        )
        self.assertTrue(result['success'])
        self.assertEqual(result['form'].name, 'Contact')
        self.assertIn('/forms/contact/submit/', result['message'])

    def test_create_missing_name_fails(self):
        result = FormService.create(name='', slug='contact')
        self.assertFalse(result['success'])

    def test_create_duplicate_slug_fails(self):
        DynamicForm.objects.create(name='Contact', slug='contact')
        result = FormService.create(name='Contact 2', slug='contact')
        self.assertFalse(result['success'])
        self.assertIn('already exists', result['error'])


class FormServiceUpdateTest(TestCase):

    def setUp(self):
        DynamicForm.objects.all().delete()
        self.form = DynamicForm.objects.create(name='Contact', slug='contact')

    def test_update_by_id(self):
        result = FormService.update(form_id=self.form.id, name='Updated')
        self.assertTrue(result['success'])
        self.form.refresh_from_db()
        self.assertEqual(self.form.name, 'Updated')

    def test_update_by_slug(self):
        result = FormService.update(slug='contact', name='Updated via Slug')
        self.assertTrue(result['success'])
        self.form.refresh_from_db()
        self.assertEqual(self.form.name, 'Updated via Slug')

    def test_update_not_found(self):
        result = FormService.update(form_id=99999, name='X')
        self.assertFalse(result['success'])

    def test_update_no_params_fails(self):
        result = FormService.update()
        self.assertFalse(result['success'])


class FormServiceDeleteTest(TestCase):

    def setUp(self):
        DynamicForm.objects.all().delete()
        self.form = DynamicForm.objects.create(name='Temp', slug='temp')

    def test_delete_by_id(self):
        result = FormService.delete(form_id=self.form.id)
        self.assertTrue(result['success'])
        self.assertFalse(DynamicForm.objects.filter(pk=self.form.id).exists())

    def test_delete_by_slug(self):
        result = FormService.delete(slug='temp')
        self.assertTrue(result['success'])

    def test_delete_not_found(self):
        result = FormService.delete(form_id=99999)
        self.assertFalse(result['success'])


class FormServiceSubmissionsTest(TestCase):

    def setUp(self):
        DynamicForm.objects.all().delete()
        self.form = DynamicForm.objects.create(name='Contact', slug='contact')
        FormSubmission.objects.create(form=self.form, data={'name': 'Alice'})
        FormSubmission.objects.create(form=self.form, data={'name': 'Bob'})

    def test_list_submissions(self):
        result = FormService.list_submissions()
        self.assertTrue(result['success'])
        self.assertEqual(len(result['submissions']), 2)

    def test_list_submissions_by_slug(self):
        other = DynamicForm.objects.create(name='Quote', slug='quote')
        FormSubmission.objects.create(form=other, data={'msg': 'Hi'})

        result = FormService.list_submissions(form_slug='contact')
        self.assertTrue(result['success'])
        self.assertEqual(len(result['submissions']), 2)

    def test_list_submissions_limit(self):
        result = FormService.list_submissions(limit=1)
        self.assertTrue(result['success'])
        self.assertEqual(len(result['submissions']), 1)

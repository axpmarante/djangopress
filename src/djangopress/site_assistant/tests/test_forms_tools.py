"""Forms: every fields_schema shape is understood, visitors submit as before,
and test_form sends a [TESTE] email to the operator only, then deletes its submission."""
import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings

from djangopress.core.models import DynamicForm, FormSubmission, Page, SiteSettings
from djangopress.site_assistant.tools import ToolRegistry

CLIENT = 'cliente@restaurante.pt'
OPERATOR = 'geral@portugalwebdesign.pt'

LIST_SCHEMA = [{'name': 'name', 'type': 'text', 'label': 'Name', 'required': True},
               {'name': 'email', 'type': 'email', 'label': 'Email', 'required': True},
               {'name': 'message', 'type': 'textarea', 'label': 'Message', 'required': True}]
DICT_SCHEMA = {
    'name': {'type': 'text', 'label': {'pt': 'Nome'}, 'required': True},
    'email': {'type': 'email', 'label': {'pt': 'Email'}, 'required': True},
    'phone': {'type': 'tel', 'label': {'pt': 'Telefone'}, 'required': True},
    'date': {'type': 'date', 'label': {'pt': 'Data'}, 'required': True},
    'time': {'type': 'select', 'label': {'pt': 'Hora'}, 'required': True,
             'choices': [{'value': '12:30', 'label': {'pt': '12:30'}}, {'value': '13:00', 'label': {'pt': '13:00'}}]},
    'people': {'type': 'select', 'required': True, 'options': ['2', '4']},
    'guests': {'type': 'number', 'required': False},
    'consent': {'type': 'checkbox', 'label': {'pt': 'Consentimento'}, 'required': True},
}


def form_html(slug, names):
    fields = ''.join(f'<input name="{n}"/>' for n in names)
    return f'<section data-section="c"><form action="/forms/{slug}/submit/" method="post">{fields}' \
           f'<input name="website_url" class="hidden"/></form></section>'


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', PWD_SUPERADMIN_EMAIL=OPERATOR)
class FormsTestCase(TestCase):
    def setUp(self):
        cache.clear()
        DynamicForm.objects.all().delete()      # a migration seeds a "contact" form
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.contact_email = CLIENT
        s.save()
        self.user = get_user_model().objects.create_superuser('op', 'op@x.com', 'pw')
        self.context = {'session': mock.Mock(), 'user': self.user}


class SchemaShapesTest(FormsTestCase):
    def test_every_shape_normalises(self):
        strings = DynamicForm(slug='a', fields_schema=['name', 'email', 'mensagem'])
        self.assertEqual([(f['name'], f['type']) for f in strings.schema_fields()],
                         [('name', 'text'), ('email', 'email'), ('mensagem', 'textarea')])
        keyed = DynamicForm(slug='b', fields_schema=DICT_SCHEMA)
        fields = {f['name']: f for f in keyed.schema_fields('pt')}
        self.assertEqual(fields['phone']['label'], 'Telefone')
        self.assertEqual(fields['time']['choices'], ['12:30', '13:00'])
        self.assertEqual(fields['people']['choices'], ['2', '4'])
        self.assertTrue(fields['consent']['required'])

    def test_dict_schema_is_validated(self):
        form = DynamicForm(slug='b', fields_schema=DICT_SCHEMA)
        errors = form.validate_submission({'name': 'Ana', 'email': 'nope'})
        self.assertIn('phone', errors)
        self.assertIn('email', errors)
        self.assertEqual(form.get_field_label('phone'), 'Telefone')
        self.assertEqual(form.get_reply_to_field(), 'email')

    def test_validate_forms_with_string_and_dict_schemas(self):
        DynamicForm.objects.create(name='Contacto', slug='contacto', fields_schema=['name', 'email'])
        DynamicForm.objects.create(name='Reserva', slug='reserva', fields_schema=DICT_SCHEMA)
        Page.objects.create(title_i18n={'pt': 'C'}, slug_i18n={'pt': 'c'}, is_active=True,
                            html_content_i18n={'pt': form_html('contacto', ['name', 'email'])
                                               + form_html('reserva', ['name', 'email'])})
        out = ToolRegistry.execute('validate_forms', {}, self.context)
        self.assertTrue(out['success'], out)
        self.assertTrue(any('phone' in i['issue'] for i in out['issues']), out['issues'])


class VisitorSubmissionTest(FormsTestCase):
    def test_visitor_submission_is_saved_and_notified(self):
        DynamicForm.objects.create(name='Contact', slug='contact', fields_schema=LIST_SCHEMA)
        res = self.client.post('/forms/contact/submit/', {'name': 'Ana', 'email': 'ana@x.pt', 'message': 'Olá'},
                               HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()['success'])
        self.assertEqual(FormSubmission.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [CLIENT])
        self.assertEqual(mail.outbox[0].subject, '[Contact] New submission')

    def test_visitor_errors_still_reported(self):
        DynamicForm.objects.create(name='Contact', slug='contact', fields_schema=LIST_SCHEMA)
        res = self.client.post('/forms/contact/submit/', {'name': 'Ana'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(res.status_code, 400)
        self.assertIn('email', res.json()['errors'])


class TestFormToolTest(FormsTestCase):
    def test_test_form_emails_the_operator_only_and_deletes_its_submission(self):
        DynamicForm.objects.create(name='Reserva', slug='reserva', fields_schema=DICT_SCHEMA)
        out = ToolRegistry.execute('test_form', {'slug': 'reserva'}, self.context)
        self.assertTrue(out['success'], out)
        self.assertEqual(FormSubmission.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, [OPERATOR])
        self.assertEqual(sent.bcc, [])
        self.assertTrue(sent.subject.startswith('[TESTE] '))
        self.assertIn('Hora: 12:30', sent.body)
        self.assertIn('Consentimento: Yes', sent.body)
        self.assertIn(datetime.date.today().isoformat()[:4], sent.body)
        report = out['checks'][0]
        self.assertEqual(report['form'], 'reserva')
        self.assertTrue(report['valid'] and report['saved'] and report['notification_sent'])

    def test_confirmation_email_also_goes_to_the_operator(self):
        DynamicForm.objects.create(name='Contact', slug='contact', fields_schema=LIST_SCHEMA,
                                   send_confirmation_email=True,
                                   confirmation_subject_i18n={'pt': 'Obrigado'}, confirmation_body_i18n={'pt': 'Até já'})
        out = ToolRegistry.execute('test_form', {'slug': 'contact'}, self.context)
        self.assertTrue(out['success'], out)
        self.assertEqual([m.to for m in mail.outbox], [[OPERATOR], [OPERATOR]])
        self.assertTrue(all(m.subject.startswith('[TESTE] ') for m in mail.outbox))

    def test_without_slug_tests_the_forms_on_the_pages(self):
        DynamicForm.objects.create(name='Contact', slug='contact', fields_schema=LIST_SCHEMA)
        DynamicForm.objects.create(name='Unused', slug='unused', fields_schema=LIST_SCHEMA)
        Page.objects.create(title_i18n={'pt': 'C'}, slug_i18n={'pt': 'c'}, is_active=True,
                            html_content_i18n={'pt': form_html('contact', ['name', 'email', 'message'])})
        out = ToolRegistry.execute('test_form', {}, self.context)
        self.assertEqual([c['form'] for c in out['checks']], ['contact'])

    def test_a_failing_send_is_reported(self):
        DynamicForm.objects.create(name='Contact', slug='contact', fields_schema=LIST_SCHEMA)
        with mock.patch('django.core.mail.EmailMessage.send', side_effect=OSError('smtp down')):
            out = ToolRegistry.execute('test_form', {'slug': 'contact'}, self.context)
        self.assertFalse(out['checks'][0]['notification_sent'])
        self.assertIn('not sent', out['message'])
        self.assertEqual(FormSubmission.objects.count(), 0)


class UpdateFormToolTest(FormsTestCase):
    def test_fields_not_given_are_left_alone(self):
        form = DynamicForm.objects.create(name='Contact', slug='contact', notification_email=CLIENT,
                                          fields_schema=LIST_SCHEMA)
        out = ToolRegistry.execute('update_form', {'slug': 'contact', 'is_active': False}, self.context)
        self.assertTrue(out['success'], out)
        form.refresh_from_db()
        self.assertEqual((form.name, form.notification_email, form.is_active), ('Contact', CLIENT, False))

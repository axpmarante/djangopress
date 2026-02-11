"""Data migration: copy Contact rows into DynamicForm + FormSubmission."""

from django.db import migrations


def migrate_contacts_forward(apps, schema_editor):
    Contact = apps.get_model('core', 'Contact')
    DynamicForm = apps.get_model('core', 'DynamicForm')
    FormSubmission = apps.get_model('core', 'FormSubmission')
    SiteSettings = apps.get_model('core', 'SiteSettings')

    # Get notification email from SiteSettings
    notification_email = ''
    settings = SiteSettings.objects.first()
    if settings:
        notification_email = settings.contact_email or ''

    # Always create a default contact form so AI can use /forms/contact/submit/ immediately
    form_def, _ = DynamicForm.objects.get_or_create(
        slug='contact',
        defaults={
            'name': 'Contact Form',
            'notification_email': notification_email,
            'fields_schema': [
                {'name': 'name', 'type': 'text', 'label': 'Name', 'required': True},
                {'name': 'email', 'type': 'email', 'label': 'Email', 'required': True},
                {'name': 'subject', 'type': 'text', 'label': 'Subject', 'required': True},
                {'name': 'message', 'type': 'text', 'label': 'Message', 'required': True},
            ],
            'success_message_i18n': {'en': 'Thank you for your message!', 'pt': 'Obrigado pela sua mensagem!'},
            'is_active': True,
        }
    )

    # Migrate old Contact rows if any exist
    contacts = Contact.objects.all()
    for contact in contacts:
        FormSubmission.objects.create(
            form=form_def,
            data={
                'name': contact.name,
                'email': contact.email,
                'subject': contact.subject,
                'message': contact.message,
            },
            is_read=True,
            created_at=contact.created_at,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0030_add_dynamicform_and_formsubmission'),
    ]

    operations = [
        migrations.RunPython(migrate_contacts_forward, migrations.RunPython.noop),
    ]

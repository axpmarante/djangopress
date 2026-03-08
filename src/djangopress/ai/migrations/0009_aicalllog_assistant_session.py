import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai', '0008_add_generic_fk_to_refinement_session'),
        ('site_assistant', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='aicalllog',
            name='assistant_session',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='ai_call_logs',
                to='site_assistant.assistantsession',
            ),
        ),
    ]

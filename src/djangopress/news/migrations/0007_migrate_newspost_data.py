from django.db import migrations


def migrate_data_forward(apps, schema_editor):
    NewsPost = apps.get_model('news', 'NewsPost')
    SiteSettings = apps.get_model('core', 'SiteSettings')

    # Get enabled languages
    try:
        settings = SiteSettings.objects.first()
        if settings and settings.languages:
            enabled_langs = [l['code'] for l in settings.languages if l.get('enabled')]
        else:
            enabled_langs = ['pt', 'en']
    except Exception:
        enabled_langs = ['pt', 'en']

    for post in NewsPost.objects.all():
        changed = False

        # slug -> slug_i18n
        if post.slug and not post.slug_i18n:
            post.slug_i18n = {lang: post.slug for lang in enabled_langs}
            changed = True

        # content_i18n -> html_content_i18n
        if post.content_i18n and not post.html_content_i18n:
            html_i18n = {}
            for lang, text in post.content_i18n.items():
                if text:
                    html_i18n[lang] = (
                        '<section data-section="post-body" id="post-body">'
                        '<div class="max-w-4xl mx-auto px-4 py-12 prose prose-lg">'
                        f'{text}'
                        '</div></section>'
                    )
            if html_i18n:
                post.html_content_i18n = html_i18n
                changed = True

        if changed:
            post.save()


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0006_add_slug_i18n_html_content_i18n_category'),
        ('core', '0038_populate_i18n_html_fields'),
    ]

    operations = [
        migrations.RunPython(migrate_data_forward, migrations.RunPython.noop),
    ]

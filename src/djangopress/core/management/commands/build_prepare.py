"""build_prepare — briefing → SiteSettings, privacy page, inventory images, docs/build-packet.json."""

import json
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from djangopress.core.build.briefing import parse_briefing
from djangopress.core.build.packet import LANG_NAMES, build_packet, download, parse_inventory
from djangopress.core.models import Page, SiteImage, SiteSettings

SOCIAL_FIELDS = {'instagram': 'instagram_url', 'facebook': 'facebook_url', 'linkedin': 'linkedin_url',
                 'youtube': 'youtube_url', 'tiktok': 'tiktok_url', 'twitter': 'twitter_url', 'twitter/x': 'twitter_url', 'x': 'twitter_url'}
PRIVACY = {'pt': ('politica-de-privacidade', 'Política de Privacidade e Cookies'),
           'en': ('privacy-policy', 'Privacy & Cookies Policy')}


class Command(BaseCommand):
    help = 'Prepare a site build from a content-only briefing.'

    def add_arguments(self, parser):
        parser.add_argument('briefing')
        parser.add_argument('--audit', default='')
        parser.add_argument('--no-download', action='store_true')

    def handle(self, *args, **opts):
        root = Path.cwd()
        briefing_path = Path(opts['briefing'])
        briefing = parse_briefing(briefing_path.read_text())
        if briefing.has_open_questions:
            self.stderr.write('Briefing still has ## Open Questions — finish /create-briefing first')
            raise SystemExit(1)
        slug = briefing_path.stem
        lang = briefing.default_language

        s = SiteSettings.load()
        s.default_language = lang
        s.enabled_languages = [{'code': c, 'name': briefing.language_names.get(c, LANG_NAMES.get(c, c))} for c in briefing.languages]
        s.site_name_i18n = {c: briefing.title for c in briefing.languages}
        s.site_description_i18n = {lang: briefing.business.split('\n')[0][:300]}
        s.project_briefing = briefing.business
        if briefing.contact.get('email'):
            s.contact_email = briefing.contact['email']
        s.contact_phone = briefing.contact.get('phone', '')
        for key, url in briefing.social.items():
            if key == 'whatsapp':
                s.whatsapp_number = url.rsplit('/', 1)[-1] if url.startswith('http') else url
            elif key in SOCIAL_FIELDS:
                setattr(s, SOCIAL_FIELDS[key], url)
        s.save()

        if not any('privac' in (p.slug_i18n or {}).get(lang, '') or 'politica' in (p.slug_i18n or {}).get(lang, '')
                   for p in Page.objects.all()):
            pslug, ptitle = PRIVACY.get(lang, PRIVACY['en'])
            Page.objects.create(
                title_i18n={lang: ptitle}, slug_i18n={lang: pslug},
                html_content_i18n={lang: f'<section data-section="privacy" id="privacy"><h1>{ptitle}</h1><p>{briefing.title}</p></section>'},
                meta_title_i18n={lang: ptitle}, meta_description_i18n={lang: ptitle}, is_active=True, sort_order=999)

        image_map = {}
        for img in SiteImage.objects.filter(is_active=True).exclude(key='').exclude(image=''):
            image_map[img.key] = {'url': img.image.url, 'width': None, 'alt': img.get_title(lang) if hasattr(img, 'get_title') else img.key}
        audit_path = Path(opts['audit']) if opts['audit'] else briefing_path.with_name(f'{slug}-audit.md')
        if audit_path.exists() and not opts['no_download']:
            for row in parse_inventory(audit_path.read_text()):
                if row['key'] in image_map:
                    image_map[row['key']]['width'] = row['width']
                    continue
                try:
                    data = download(row['url'])
                except Exception as exc:  # network is best-effort
                    self.stderr.write(f'skip {row["url"]}: {exc}')
                    continue
                img = SiteImage(key=row['key'], title_i18n={lang: row['group']}, alt_text_i18n={lang: row['group']})
                img.image.save(row['url'].rsplit('/', 1)[-1].split('?')[0] or f'{row["key"]}.jpg', ContentFile(data), save=True)
                image_map[row['key']] = {'url': img.image.url, 'width': row['width'], 'alt': row['group']}

        menus = {}
        for items in briefing.content.values():
            for item in items:
                if item.menu_json and (root / item.menu_json).exists():
                    menus[item.menu_json] = json.loads((root / item.menu_json).read_text())

        packet = build_packet(briefing, site_slug=slug, image_map=image_map, menus=menus)
        out = root / 'docs' / 'build-packet.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(packet, ensure_ascii=False, indent=2))
        required = sum(len(v['required']) for v in packet['content'].values())
        self.stdout.write(json.dumps({'packet': str(out), 'required_items': required, 'images': len(image_map),
                                      'languages': briefing.languages, 'vertical': packet['business']['type']}))

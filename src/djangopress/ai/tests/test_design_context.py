"""The site's design context for AI section work: reference sections, the
recurring class combinations (design vocabulary) and library images."""
from django.test import TestCase

from djangopress.ai import design_context as dc
from djangopress.core.models import Page, SiteImage, SiteSettings

EYEBROW = 'text-[11px] font-semibold uppercase tracking-[0.22em] text-[#C42014]'
TITLE = "font-['Fraunces'] font-light text-[46px] leading-tight"
BUTTON = 'inline-flex px-7 py-3 bg-[#C42014] text-white text-sm'
BODY = 'text-[17px] leading-relaxed text-[#3A3A3A]'
LONG = 'Uma cozinha de autor com produtos da época, servida numa sala tranquila junto ao rio, todos os dias.'

HERO = (f'<section data-section="hero" class="relative min-h-[80vh] flex items-center bg-[#111] text-white">'
        f'<div class="max-w-6xl mx-auto px-6"><p class="{EYEBROW}">Lisboa</p><h1 class="text-[64px] font-light">Olá</h1>'
        f'<a class="{BUTTON}" href="/pt/reservas/">Reservar</a></div></section>')
SOBRE = (f'<section data-section="sobre" class="py-24 bg-[#F7F3EE]"><div class="max-w-5xl mx-auto grid md:grid-cols-2 gap-12">'
         f'<p class="{EYEBROW}">Sobre</p><h2 class="{TITLE}">A casa</h2><p class="{BODY}">{LONG}</p></div></section>')
EVENTOS = (f'<section data-section="eventos" class="py-24"><p class="{EYEBROW}">Eventos</p><h2 class="{TITLE}">Eventos</h2>'
           '<div class="grid md:grid-cols-3 gap-8">'
           + ''.join(f'<article class="p-8 rounded-2xl border border-[#E5DED4] bg-white"><h3 class="text-xl">{n}</h3>'
                     f'<p class="{BODY}">{LONG}</p></article>' for n in ('Casamentos', 'Empresas', 'Aniversários'))
           + f'</div><a class="{BUTTON}" href="/pt/eventos/">Saber mais</a><a class="underline text-[#C42014]" href="/pt/carta/">Ver carta</a>'
           '<div class="h-px w-16 bg-[#C42014]"></div></section>')
CONTACTOS = '<section data-section="contactos" class="py-10"><h2>Contactos</h2></section>'


class DesignContextTest(TestCase):
    def setUp(self):
        s = SiteSettings.load()
        s.enabled_languages = [{'code': 'pt', 'name': 'PT'}]
        s.default_language = 'pt'
        s.heading_font = 'Fraunces'
        s.body_font = 'Inter'
        s.design_guide = 'Calm, editorial, lots of white space.'
        Page.objects.all().delete()
        self.home = Page.objects.create(title_i18n={'pt': 'Início'}, slug_i18n={'pt': 'inicio'}, is_active=True,
                                        html_content_i18n={'pt': HERO})
        s.homepage = self.home
        s.save()
        self.page = Page.objects.create(title_i18n={'pt': 'Casa'}, slug_i18n={'pt': 'casa'}, is_active=True,
                                        html_content_i18n={'pt': SOBRE + EVENTOS + CONTACTOS})

    def test_references_put_the_home_hero_first_and_skip_the_target(self):
        ctx = dc.build_design_context(self.page, 'contactos', lang='pt')
        names = [r['name'] for r in ctx['references']]
        self.assertEqual(names[0], 'hero')
        self.assertNotIn('contactos', names)
        self.assertEqual(set(names), {'hero', 'sobre', 'eventos'})
        self.assertEqual([r['label'] for r in ctx['references']][0], 'Hero')

    def test_references_on_the_homepage_do_not_repeat_the_hero(self):
        self.home.html_content_i18n = {'pt': HERO + SOBRE + CONTACTOS}
        self.home.save()
        ctx = dc.build_design_context(self.home, 'contactos', lang='pt')
        self.assertEqual([r['name'] for r in ctx['references']].count('hero'), 1)

    def test_editing_the_hero_itself_does_not_reference_it(self):
        ctx = dc.build_design_context(self.home, 'hero', lang='pt')
        self.assertNotIn('hero', [r['name'] for r in ctx['references']])

    def test_references_are_capped(self):
        big = SOBRE.replace(LONG, LONG * 200)
        self.page.html_content_i18n = {'pt': big + CONTACTOS}
        self.page.save()
        ctx = dc.build_design_context(self.page, 'contactos', lang='pt')
        sobre = next(r for r in ctx['references'] if r['name'] == 'sobre')
        self.assertLessEqual(len(sobre['html']), dc.REFERENCE_CAP + 40)
        self.assertIn('cut', sobre['html'])

    def test_vocabulary_finds_the_recurring_roles(self):
        vocab = {v['role']: v for v in dc.build_design_context(self.page, 'contactos', lang='pt')['vocabulary']}
        self.assertEqual(vocab['eyebrow']['classes'], EYEBROW)
        self.assertEqual(vocab['eyebrow']['count'], 3)
        self.assertEqual(vocab['section title']['classes'], TITLE)
        self.assertEqual(vocab['primary button']['classes'], BUTTON)
        self.assertEqual(vocab['body text']['classes'], BODY)
        self.assertIn('rounded-2xl', vocab['card']['classes'])
        self.assertEqual(vocab['text link']['classes'], 'underline text-[#C42014]')
        self.assertIn('h-px', vocab['divider']['classes'])

    def test_a_text_link_has_a_colour_or_an_underline(self):
        self.page.html_content_i18n = {'pt': SOBRE + EVENTOS + ''.join('<a class="block" href="/x/">x</a>' for _ in range(9))}
        self.page.save()
        vocab = {v['role']: v for v in dc.build_design_context(self.page, 'contactos', lang='pt')['vocabulary']}
        self.assertEqual(vocab['text link']['classes'], 'underline text-[#C42014]')

    def test_tokens_and_guide(self):
        ctx = dc.build_design_context(self.page, 'contactos', lang='pt')
        self.assertIn('#C42014', [c['value'] for c in ctx['colors']])
        self.assertEqual([f['family'] for f in ctx['fonts']][:2], ['Fraunces', 'Inter'])
        self.assertEqual(ctx['design_guide'], 'Calm, editorial, lots of white space.')

    def test_library_images_ranked_by_the_request_words(self):
        for i in range(14):
            SiteImage.objects.create(title_i18n={'pt': f'Foto {i}'}, key=f'f{i}', image=f'site_images/f{i}.jpg', is_active=True)
        SiteImage.objects.create(title_i18n={'pt': 'Mesa de casamento'}, key='casamento', tags='casamentos, eventos',
                                 image='site_images/casamento.jpg', is_active=True)
        SiteImage.objects.create(title_i18n={'pt': 'Off'}, key='off', image='site_images/off.jpg', is_active=False)
        SiteImage.objects.create(title_i18n={'pt': 'PDF'}, key='doc', file='site_files/x.pdf', file_type='document', is_active=True)
        images = dc.build_design_context(self.page, 'eventos', lang='pt', query='cartões para casamentos')['images']
        self.assertEqual(len(images), dc.IMAGE_LIMIT)
        self.assertTrue(images[0]['url'].endswith('casamento.jpg'))
        self.assertNotIn('off.jpg', ' '.join(i['url'] for i in images))
        self.assertNotIn('x.pdf', ' '.join(i['url'] for i in images))

    def test_render_has_references_vocabulary_and_images(self):
        SiteImage.objects.create(title_i18n={'pt': 'Sala'}, key='sala', image='site_images/sala.jpg', is_active=True)
        ctx = dc.build_design_context(self.page, 'contactos', lang='pt')
        block = dc.render_design_context(ctx)
        self.assertTrue(block.startswith('## Site design'))
        self.assertIn('data-section="eventos"', block)
        self.assertIn(f'eyebrow: `{EYEBROW}`', block)
        self.assertIn('sala.jpg', block)
        self.assertIn('Calm, editorial', block)
        self.assertIn('Fraunces', block)

    def test_matches_summary(self):
        ctx = dc.build_design_context(self.page, 'contactos', lang='pt')
        m = dc.matches_summary(ctx)
        self.assertLessEqual(len(m['colors']), 5)
        self.assertIn('#C42014', m['colors'])
        self.assertEqual(m['fonts'], ['Fraunces', 'Inter'])
        self.assertEqual(m['references'][0], 'Hero')
        self.assertLessEqual(len(m['references']), 3)

    def test_object_without_sections_still_works(self):
        class Post:
            html_content_i18n = {'pt': '<div><p>texto</p></div>'}
        ctx = dc.build_design_context(Post(), None, lang='pt')
        self.assertEqual(ctx['references'][0]['name'], 'hero')

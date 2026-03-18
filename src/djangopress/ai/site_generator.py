"""
SiteGenerator — Full site generation pipeline from a briefing document.

Used by both the /generate-site Claude Code skill and the generate_site management command.
Parses a markdown briefing, configures SiteSettings, generates pages, header/footer,
processes images, and creates menu items.
"""

import json
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from djangopress.ai.utils.llm_config import get_ai_model

logger = logging.getLogger(__name__)


class BriefingParser:
    """Parse a markdown site briefing into structured data."""

    SECTION_PATTERN = re.compile(r'^##\s+(.+)$', re.MULTILINE)

    @classmethod
    def parse(cls, text: str) -> Dict:
        """Parse briefing markdown into a dict of sections."""
        sections = {}
        parts = cls.SECTION_PATTERN.split(text)

        # parts[0] is everything before the first ## (the title line)
        title_block = parts[0].strip()
        # Extract business name from # Title line
        title_match = re.match(r'^#\s+(.+?)(?:\s*[-—]\s*Site Briefing)?$', title_block, re.MULTILINE)
        business_name = title_match.group(1).strip() if title_match else ''

        # Pair up section headers and content
        for i in range(1, len(parts), 2):
            header = parts[i].strip()
            content = parts[i + 1].strip() if i + 1 < len(parts) else ''
            sections[header.lower()] = content

        return {
            'business_name': business_name,
            'sections': sections,
            'raw_text': text,
        }

    @classmethod
    def extract_languages(cls, section_text: str) -> Tuple[str, str, List[dict]]:
        """Extract language configuration.

        Returns:
            (default_code, default_name, enabled_languages_list)
        """
        languages = []
        default_code = 'pt'
        default_name = 'Portuguese'

        for line in section_text.split('\n'):
            line = line.strip().lstrip('- ')
            if not line:
                continue

            # Match "Default: pt (Portuguese)" or "Additional: en (English), fr (French)"
            default_match = re.match(r'Default:\s*(\w+)\s*\(([^)]+)\)', line, re.IGNORECASE)
            additional_match = re.match(r'Additional:\s*(.+)', line, re.IGNORECASE)

            if default_match:
                default_code = default_match.group(1).strip()
                default_name = default_match.group(2).strip()
                languages.insert(0, {'code': default_code, 'name': default_name})
            elif additional_match:
                # Parse comma-separated: "en (English), fr (French)"
                for part in additional_match.group(1).split(','):
                    lang_match = re.match(r'\s*(\w+)\s*\(([^)]+)\)', part.strip())
                    if lang_match:
                        languages.append({
                            'code': lang_match.group(1).strip(),
                            'name': lang_match.group(2).strip(),
                        })

        if not languages:
            languages = [{'code': 'pt', 'name': 'Portuguese'}, {'code': 'en', 'name': 'English'}]

        return default_code, default_name, languages

    @classmethod
    def extract_contact(cls, section_text: str) -> Dict:
        """Extract contact info from the Contact section."""
        contact = {}
        current_key = None
        address_lines = []

        for line in section_text.split('\n'):
            line = line.strip().lstrip('- ')
            if not line:
                continue

            if line.lower().startswith('email:'):
                contact['email'] = line.split(':', 1)[1].strip()
                current_key = 'email'
            elif line.lower().startswith('phone:'):
                contact['phone'] = line.split(':', 1)[1].strip()
                current_key = 'phone'
            elif line.lower().startswith('address:'):
                rest = line.split(':', 1)[1].strip()
                current_key = 'address'
                if rest:
                    address_lines.append(rest)
            elif line.lower().startswith('google maps:'):
                contact['google_maps'] = line.split(':', 1)[1].strip()
                # Handle URLs that got split on the colon
                if contact['google_maps'] and not contact['google_maps'].startswith('http'):
                    contact['google_maps'] = line.split('Google Maps:', 1)[1].strip() if 'Google Maps:' in line else line.split('google maps:', 1)[1].strip()
                current_key = 'google_maps'
            elif current_key == 'address':
                # Multi-line address or per-language addresses
                address_lines.append(line)

        # Parse address — could be per-language "pt: Rua..." or single
        if address_lines:
            address_i18n = {}
            for addr_line in address_lines:
                lang_match = re.match(r'(\w{2}):\s*(.+)', addr_line)
                if lang_match:
                    address_i18n[lang_match.group(1)] = lang_match.group(2).strip()
                else:
                    # Single address for all languages
                    address_i18n['_default'] = addr_line
            contact['address_i18n'] = address_i18n

        return contact

    @classmethod
    def extract_social_media(cls, section_text: str) -> Dict:
        """Extract social media URLs."""
        social = {}
        for line in section_text.split('\n'):
            line = line.strip().lstrip('- ')
            if not line:
                continue

            for platform in ['instagram', 'facebook', 'linkedin', 'youtube',
                             'twitter', 'tiktok', 'pinterest', 'whatsapp']:
                if line.lower().startswith(platform + ':'):
                    value = line.split(':', 1)[1].strip()
                    # Handle URLs with colons (https://...)
                    if not value.startswith('http') and ':' in line:
                        # Re-split to get the full URL
                        full_value = ':'.join(line.split(':')[1:]).strip()
                        if full_value:
                            value = full_value
                    if value:
                        social[platform] = value
                    break

        return social

    @classmethod
    def extract_pages(cls, section_text: str) -> List[Dict]:
        """Extract page descriptions from the Pages section.

        Returns list of dicts with 'name' and 'description'.
        """
        pages = []
        # Match "- **Name**: description" or "- **Name** — description"
        pattern = re.compile(
            r'-\s+\*\*([^*]+)\*\*\s*[:—-]\s*(.+?)(?=\n-\s+\*\*|\Z)',
            re.DOTALL
        )

        for match in pattern.finditer(section_text):
            name = match.group(1).strip()
            description = match.group(2).strip()
            # Clean up multi-line descriptions
            description = re.sub(r'\n\s*', ' ', description)
            pages.append({'name': name, 'description': description})

        return pages

    @classmethod
    def extract_domain(cls, section_text: str) -> str:
        """Extract domain identifier."""
        return section_text.strip().split('\n')[0].strip()

    @classmethod
    def extract_image_strategy(cls, section_text: str) -> str:
        """Determine image strategy from the Images section."""
        text = section_text.lower()
        if 'skip' in text:
            return 'skip'
        elif 'unsplash' in text and ('ai' in text or 'mix' in text or 'both' in text):
            return 'mixed'
        elif 'unsplash' in text:
            return 'unsplash_preferred'
        else:
            return 'ai_generated'


class SiteGenerator:
    """Full site generation pipeline from a briefing document."""

    def __init__(self, briefing_path: str, stdout=None, **options):
        self.briefing_path = Path(briefing_path)
        if not self.briefing_path.exists():
            raise FileNotFoundError(f"Briefing file not found: {briefing_path}")

        self.briefing_text = self.briefing_path.read_text()
        self.briefing = BriefingParser.parse(self.briefing_text)
        self.sections = self.briefing['sections']
        self.stdout = stdout
        self.dry_run = options.get('dry_run', False)
        self.skip_images = options.get('skip_images', False)
        self.skip_design_guide = options.get('skip_design_guide', False)
        self.model = options.get('model') or get_ai_model('generation')
        self.image_strategy = options.get('image_strategy', None)
        self.delay = options.get('delay', 2)
        self.generated_pages = []
        self.errors = []
        self._overall_start = None

    def log(self, message: str):
        if self.stdout:
            self.stdout.write(message)
        else:
            print(message)

    def _elapsed(self):
        """Return formatted elapsed time since pipeline start."""
        if self._overall_start is None:
            return ""
        secs = time.time() - self._overall_start
        mins = int(secs // 60)
        secs_rem = int(secs % 60)
        if mins:
            return f"({mins}m {secs_rem:02d}s)"
        return f"({secs_rem}s)"

    def _make_page_progress_callback(self, label):
        """Create an on_progress callback for terminal display during generation."""
        start = time.time()
        def on_progress(event):
            status = event.get('status', '')
            chars = event.get('chars', 0)
            step = event.get('step', '')
            elapsed = time.time() - start
            if status == 'streaming' and chars:
                sys.stderr.write(f"\r    {label}: {chars:,} chars ({elapsed:.0f}s)")
                sys.stderr.flush()
            elif status == 'done' and step in ('html_generation', 'refine_html'):
                sys.stderr.write(f"\r    {label}: done ({elapsed:.0f}s)          \n")
                sys.stderr.flush()
        return on_progress

    def run(self):
        """Execute the full pipeline."""
        self._overall_start = time.time()
        self.log(f"\n{'='*60}")
        self.log(f"Site Generator: {self.briefing['business_name']}")
        self.log(f"{'='*60}\n")

        plan = self.plan()

        if self.dry_run:
            self._print_plan(plan)
            return plan

        self.configure_settings(plan)

        # Generate design guide BEFORE pages so all pages benefit from it
        if not self.skip_design_guide:
            self.generate_design_guide(plan)

        # Generate pages with header/footer in parallel after home
        self.generate_pages(plan)

        self.create_menu_items()

        # Translate pages to all enabled languages
        self.translate_all_content(plan)

        if not self.skip_images:
            self.process_all_images()

        self.ensure_contact_form()

        # Post-generation validation
        self.validate_generation()

        return self.print_summary()

    def plan(self) -> Dict:
        """Parse the briefing and build a generation plan."""
        sections = self.sections

        # Languages
        lang_text = sections.get('languages', '')
        default_code, default_name, enabled_languages = BriefingParser.extract_languages(lang_text)

        # Contact
        contact = BriefingParser.extract_contact(sections.get('contact', ''))

        # Social media
        social = BriefingParser.extract_social_media(sections.get('social media', ''))

        # Pages
        pages = BriefingParser.extract_pages(sections.get('pages', ''))

        # Domain
        domain = BriefingParser.extract_domain(sections.get('domain', ''))

        # Image strategy
        if self.image_strategy:
            image_strategy = self.image_strategy
        elif 'images' in sections:
            image_strategy = BriefingParser.extract_image_strategy(sections['images'])
        else:
            image_strategy = 'ai_generated'

        # Language codes
        language_codes = [lang['code'] for lang in enabled_languages]

        return {
            'business_name': self.briefing['business_name'],
            'default_language': default_code,
            'default_language_name': default_name,
            'enabled_languages': enabled_languages,
            'language_codes': language_codes,
            'contact': contact,
            'social_media': social,
            'pages': pages,
            'header_instructions': sections.get('header', ''),
            'footer_instructions': sections.get('footer', ''),
            'design_preferences': sections.get('design preferences', ''),
            'domain': domain,
            'image_strategy': image_strategy,
            'business_description': sections.get('business', ''),
            'additional_notes': sections.get('additional notes', ''),
        }

    def _print_plan(self, plan: Dict):
        """Print the parsed plan for dry-run mode."""
        self.log(f"\n--- DRY RUN: Parsed Plan ---\n")
        self.log(f"Business: {plan['business_name']}")
        self.log(f"Domain: {plan['domain']}")
        self.log(f"Default language: {plan['default_language']}")
        self.log(f"Languages: {', '.join(l['code'] + ' (' + l['name'] + ')' for l in plan['enabled_languages'])}")
        self.log(f"Image strategy: {plan['image_strategy']}")

        self.log(f"\nContact:")
        for key, val in plan['contact'].items():
            self.log(f"  {key}: {val}")

        self.log(f"\nSocial media:")
        for key, val in plan['social_media'].items():
            self.log(f"  {key}: {val}")

        self.log(f"\nPages to generate ({len(plan['pages'])}):")
        for i, page in enumerate(plan['pages'], 1):
            self.log(f"  {i}. {page['name']}: {page['description'][:100]}...")

        if plan['header_instructions']:
            self.log(f"\nHeader: {plan['header_instructions'][:100]}...")
        if plan['footer_instructions']:
            self.log(f"\nFooter: {plan['footer_instructions'][:100]}...")
        if plan['design_preferences']:
            self.log(f"\nDesign: {plan['design_preferences'][:100]}...")

    def configure_settings(self, plan: Dict):
        """Configure SiteSettings from the parsed plan."""
        import django
        django.setup()
        from djangopress.core.models import SiteSettings

        self.log(f"\n--- Configuring SiteSettings --- {self._elapsed()}")

        settings, _ = SiteSettings.objects.get_or_create(pk=1)

        # Domain (production URL)
        if plan['domain']:
            settings.domain = plan['domain']

        # GCS folder (set once from project slug, never changed)
        if not settings.gcs_folder:
            import os
            settings.gcs_folder = os.path.basename(os.getcwd())

        # Languages
        settings.enabled_languages = plan['enabled_languages']
        settings.default_language = plan['default_language']

        # Site name — brand name, same in all languages
        name_i18n = {lang: plan['business_name'] for lang in plan['language_codes']}
        settings.site_name_i18n = name_i18n

        # Site description — use business description first paragraph as description
        desc_text = plan['business_description'].split('\n\n')[0] if plan['business_description'] else ''
        if desc_text:
            desc_i18n = {plan['default_language']: desc_text}
            settings.site_description_i18n = desc_i18n

        # Project briefing — store the full briefing file for AI context
        settings.project_briefing = self.briefing_text

        # Contact info
        contact = plan['contact']
        if contact.get('email'):
            settings.contact_email = contact['email']
        if contact.get('phone'):
            settings.contact_phone = contact['phone']
        if contact.get('google_maps'):
            settings.google_maps_embed_url = contact['google_maps']

        # Address
        if contact.get('address_i18n'):
            addr = contact['address_i18n']
            if '_default' in addr:
                # Same address for all languages
                settings.contact_address_i18n = {
                    lang: addr['_default'] for lang in plan['language_codes']
                }
            else:
                settings.contact_address_i18n = addr

        # Social media
        social = plan['social_media']
        social_field_map = {
            'facebook': 'facebook_url',
            'instagram': 'instagram_url',
            'linkedin': 'linkedin_url',
            'youtube': 'youtube_url',
            'twitter': 'twitter_url',
            'tiktok': 'tiktok_url',
            'pinterest': 'pinterest_url',
            'whatsapp': 'whatsapp_number',
        }
        for platform, field in social_field_map.items():
            if social.get(platform):
                setattr(settings, field, social[platform])

        # Design system — let the LLM choose fonts, colors, layout from the briefing
        try:
            self.configure_design_system(plan, settings)
        except Exception as e:
            self.log(f"  Design system configuration failed (using defaults): {e}")
            self.errors.append({'page': 'design_system', 'error': str(e)})

        settings.save()
        self.log(f"SiteSettings configured: {plan['business_name']}")
        self.log(f"  Domain: {settings.domain}")
        self.log(f"  Languages: {settings.get_language_codes()}")
        self.log(f"  Default: {settings.get_default_language()}")

    def configure_design_system(self, plan: Dict, settings):
        """Use an LLM to choose design system values based on the briefing."""
        from djangopress.ai.utils.llm_config import LLMBase
        from djangopress.core.models import GOOGLE_FONTS_CHOICES

        self.log("  Configuring design system via LLM...")

        font_list = self._format_font_list(GOOGLE_FONTS_CHOICES)
        valid_fonts = {name for name, _ in GOOGLE_FONTS_CHOICES}

        # Valid choices for enum fields
        valid_choices = {
            'container_width': ['full', 'xs', 'sm', 'md', 'lg', 'xl', '2xl', '3xl', '4xl', '5xl', '6xl', '7xl'],
            'border_radius_preset': ['none', 'sm', 'md', 'lg', 'xl', '2xl', '3xl', 'full'],
            'spacing_scale': ['tight', 'normal', 'relaxed', 'loose'],
            'shadow_preset': ['none', 'sm', 'md', 'lg', 'xl', '2xl'],
            'button_style': ['rounded', 'square', 'pill'],
            'button_size': ['small', 'medium', 'large'],
            'button_border_width': ['0', '1', '2', '4'],
        }

        valid_text_sizes = [
            'text-xs', 'text-sm', 'text-base', 'text-lg', 'text-xl',
            'text-2xl', 'text-3xl', 'text-4xl', 'text-5xl', 'text-6xl',
            'text-7xl', 'text-8xl', 'text-9xl',
        ]

        hex_re = re.compile(r'^#[0-9a-fA-F]{6}$')

        system_prompt = (
            "You are a senior web designer choosing a design system for a website. "
            "Return ONLY a JSON object with the design system values. No explanation, no markdown fences."
        )

        user_prompt = f"""Choose a complete design system for this website:

Business: {plan['business_name']}
Description: {plan.get('business_description', '')[:500]}
Design preferences: {plan.get('design_preferences', 'modern and professional')}

Return a JSON object with ALL of these keys:

COLORS (hex codes like "#1e3a8a"):
- primary_color: main brand color
- primary_color_hover: slightly darker/lighter variant
- secondary_color: complementary color
- accent_color: highlight/CTA color
- background_color: page background (usually "#ffffff" or near-white)
- text_color: body text (usually dark gray)
- heading_color: heading text (usually darker than body)

FONTS (pick from this list):
{font_list}

- heading_font: for all headings (h1-h6)
- body_font: for body text

HEADING SIZES (Tailwind classes: text-xs, text-sm, text-base, text-lg, text-xl, text-2xl, text-3xl, text-4xl, text-5xl, text-6xl, text-7xl, text-8xl, text-9xl):
- h1_size, h2_size, h3_size, h4_size, h5_size, h6_size

LAYOUT:
- container_width: one of {valid_choices['container_width']}
- border_radius_preset: one of {valid_choices['border_radius_preset']}
- spacing_scale: one of {valid_choices['spacing_scale']}
- shadow_preset: one of {valid_choices['shadow_preset']}

BUTTONS:
- button_style: one of {valid_choices['button_style']}
- button_size: one of {valid_choices['button_size']}
- button_border_width: one of {valid_choices['button_border_width']}
- primary_button_bg: hex color
- primary_button_text: hex color
- primary_button_border: hex color
- primary_button_hover: hex color
- secondary_button_bg: hex color
- secondary_button_text: hex color
- secondary_button_border: hex color
- secondary_button_hover: hex color"""

        llm = LLMBase()
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        response = llm.get_completion(messages, tool_name=get_ai_model('generation'))
        content = response.choices[0].message.content
        data = self._extract_design_json(content)

        if not data:
            self.log("    Could not parse LLM response as JSON, skipping design system")
            return False

        # Define field categories for validation
        color_fields = [
            'primary_color', 'primary_color_hover', 'secondary_color', 'accent_color',
            'background_color', 'text_color', 'heading_color',
            'primary_button_bg', 'primary_button_text', 'primary_button_border',
            'primary_button_hover', 'secondary_button_bg', 'secondary_button_text',
            'secondary_button_border', 'secondary_button_hover',
        ]
        font_fields = ['heading_font', 'body_font']
        size_fields = ['h1_size', 'h2_size', 'h3_size', 'h4_size', 'h5_size', 'h6_size']

        applied = 0
        skipped = 0

        for key, value in data.items():
            if not isinstance(value, str):
                value = str(value)
            value = value.strip()

            if key in color_fields:
                if hex_re.match(value):
                    setattr(settings, key, value)
                    applied += 1
                else:
                    logger.debug(f"Design system: invalid hex for {key}: {value}")
                    skipped += 1

            elif key in font_fields:
                if value in valid_fonts:
                    setattr(settings, key, value)
                    # Also apply heading_font to all h1-h6 individual font fields
                    if key == 'heading_font':
                        for hf in ['h1_font', 'h2_font', 'h3_font', 'h4_font', 'h5_font', 'h6_font']:
                            setattr(settings, hf, value)
                    applied += 1
                else:
                    logger.debug(f"Design system: invalid font for {key}: {value}")
                    skipped += 1

            elif key in size_fields:
                if value in valid_text_sizes:
                    setattr(settings, key, value)
                    applied += 1
                else:
                    logger.debug(f"Design system: invalid size for {key}: {value}")
                    skipped += 1

            elif key in valid_choices:
                if value in valid_choices[key]:
                    setattr(settings, key, value)
                    applied += 1
                else:
                    logger.debug(f"Design system: invalid choice for {key}: {value}")
                    skipped += 1

        self.log(f"    Design system: {applied} fields applied, {skipped} skipped")
        return True

    @staticmethod
    def _format_font_list(choices) -> str:
        """Format GOOGLE_FONTS_CHOICES into a categorized string for the LLM prompt."""
        categories = {}
        for name, label in choices:
            # Extract category from label: "Roboto (Modern Sans-serif)" → "Sans-serif"
            paren = label.rsplit('(', 1)
            if len(paren) == 2:
                cat = paren[1].rstrip(')')
                # Normalize: keep the last word as category
                words = cat.split()
                category = words[-1] if words else 'Other'
            else:
                category = 'Other'
            categories.setdefault(category, []).append(name)

        lines = []
        for cat, fonts in categories.items():
            lines.append(f"  {cat}: {', '.join(fonts)}")
        return '\n'.join(lines)

    @staticmethod
    def _extract_design_json(content: str) -> Optional[Dict]:
        """Extract JSON from LLM response (handles ```json blocks and raw JSON)."""
        # Try to extract from code fences first
        fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', content, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try the whole content as JSON
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            pass

        # Try to find a JSON object in the content
        brace_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def generate_pages(self, plan: Dict):
        """Generate all pages from the plan (home first, then rest in parallel)."""
        from djangopress.ai.services import ContentGenerationService
        from djangopress.core.models import Page, SiteSettings

        import django
        django.setup()

        service = ContentGenerationService(model_name=self.model)
        settings = SiteSettings.objects.first()
        default_lang = settings.get_default_language()
        language_codes = settings.get_language_codes()

        self.log(f"\n--- Generating {len(plan['pages'])} pages --- {self._elapsed()}")

        # Ensure home page is generated first
        pages = list(plan['pages'])
        home_idx = next(
            (i for i, p in enumerate(pages) if p['name'].lower() == 'home'),
            None
        )
        if home_idx is not None and home_idx != 0:
            pages.insert(0, pages.pop(home_idx))

        def _generate_single_page(i, page_spec):
            """Generate a single page — safe to call from a thread."""
            from djangopress.ai.services import ContentGenerationService
            from djangopress.core.models import Page

            thread_service = ContentGenerationService(model_name=self.model)
            page_name = page_spec['name']
            page_desc = page_spec['description']

            self.log(f"\n  [{i+1}/{len(pages)}] Generating: {page_name}")
            brief = self._build_page_brief(page_spec, plan)

            try:
                progress_cb = self._make_page_progress_callback(page_name)
                result = thread_service.generate_page(
                    brief=brief,
                    language=default_lang,
                    on_progress=progress_cb,
                )

                if page_name.lower() in ('home', 'homepage', 'home page', 'inicio'):
                    slug_i18n = {lang: 'home' for lang in language_codes}
                else:
                    slug_i18n = result.get('slug_i18n', {})

                title_i18n = result.get('title_i18n', {})

                html_i18n = result.get('html_content_i18n', {})
                page = Page.objects.create(
                    title_i18n=title_i18n,
                    slug_i18n=slug_i18n,
                    html_content_i18n=html_i18n,
                    is_active=True,
                    sort_order=i * 10,
                )

                self.log(f"    Saved: {page.default_title} (/{page.default_slug}/)")
                default_html = next(iter(html_i18n.values()), '')
                self.log(f"    HTML: {len(default_html)} chars")
                return page

            except Exception as e:
                self.log(f"    ERROR generating {page_name}: {e}")
                self.errors.append({'page': page_name, 'error': str(e)})

                try:
                    self.log(f"    Retrying {page_name} with simplified brief...")
                    simple_brief = f"Create a {page_name} page. {page_desc}"
                    retry_cb = self._make_page_progress_callback(f"{page_name} (retry)")
                    result = thread_service.generate_page(
                        brief=simple_brief,
                        language=default_lang,
                        on_progress=retry_cb,
                    )

                    if page_name.lower() in ('home', 'homepage', 'home page', 'inicio'):
                        slug_i18n = {lang: 'home' for lang in language_codes}
                    else:
                        slug_i18n = result.get('slug_i18n', {})

                    page = Page.objects.create(
                        title_i18n=result.get('title_i18n', {}),
                        slug_i18n=slug_i18n,
                        html_content_i18n=result.get('html_content_i18n', {}),
                        is_active=True,
                        sort_order=i * 10,
                    )
                    self.errors.pop()
                    self.log(f"    Retry succeeded: {page.default_title}")
                    return page
                except Exception as retry_e:
                    self.log(f"    Retry also failed for {page_name}: {retry_e}")
                    self.errors.append({'page': f'{page_name} (retry)', 'error': str(retry_e)})
                    return None

        # Generate home page first (needs to exist before others for inter-page linking)
        home_page = _generate_single_page(0, pages[0])
        if home_page:
            self.generated_pages.append(home_page)
            # Set as homepage in SiteSettings
            if not settings.homepage_id:
                settings.homepage = home_page
                settings.save(update_fields=['homepage'])
                self.log(f"    Set as site homepage")

        # Generate remaining pages + header + footer in parallel
        remaining = pages[1:]
        self.log(f"\n  Generating {len(remaining)} remaining pages + header + footer in parallel...")

        def _generate_header_task():
            """Generate header in the parallel pool."""
            try:
                self.generate_header(plan)
                return ('header', True)
            except Exception as e:
                self.log(f"  Header generation failed in parallel: {e}")
                return ('header', False)

        def _generate_footer_task():
            """Generate footer in the parallel pool."""
            try:
                self.generate_footer(plan)
                return ('footer', True)
            except Exception as e:
                self.log(f"  Footer generation failed in parallel: {e}")
                return ('footer', False)

        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {}

            # Submit remaining pages
            for i, page_spec in enumerate(remaining):
                future = pool.submit(_generate_single_page, i + 1, page_spec)
                futures[future] = ('page', i + 1, page_spec)

            # Submit header and footer
            futures[pool.submit(_generate_header_task)] = ('header',)
            futures[pool.submit(_generate_footer_task)] = ('footer',)

            for future in as_completed(futures):
                task_info = futures[future]
                if task_info[0] == 'page':
                    page = future.result()
                    if page:
                        self.generated_pages.append(page)
                else:
                    # header or footer — result already handled inside the task
                    future.result()

    def _build_page_brief(self, page_spec: Dict, plan: Dict) -> str:
        """Build an enriched generation brief for a page."""
        name = page_spec['name']
        desc = page_spec['description']

        # Start with the page description
        brief_parts = [
            f"Create a {name} page for {plan['business_name']}.",
            "",
            f"Page description: {desc}",
        ]

        # Add design context if available
        if plan['design_preferences']:
            brief_parts.extend([
                "",
                f"Design direction: {plan['design_preferences']}",
            ])

        # Add notes if relevant
        if plan['additional_notes']:
            brief_parts.extend([
                "",
                f"Additional context: {plan['additional_notes']}",
            ])

        # Add image placeholder instruction
        brief_parts.extend([
            "",
            "Include image placeholders with data-image-prompt and data-image-name attributes on <img> tags.",
            "Use https://placehold.co/WxH?text=Label as placeholder src.",
        ])

        return '\n'.join(brief_parts)

    def generate_design_guide(self, plan: Dict = None):
        """Generate a design guide from the project briefing and design system settings."""
        from djangopress.core.models import SiteSettings
        from djangopress.ai.utils.llm_config import LLMBase

        self.log(f"\n--- Generating Design Guide --- {self._elapsed()}")

        try:
            settings = SiteSettings.objects.first()
            if not settings:
                return

            default_lang = settings.get_default_language()
            site_name = settings.get_site_name(default_lang)
            project_briefing = settings.get_project_briefing()
            settings_summary = self._build_settings_summary(settings)

            # Build page list from plan (if available) for context
            page_context = ""
            if plan and plan.get('pages'):
                page_names = [p['name'] for p in plan['pages']]
                page_context = f"\nPlanned pages: {', '.join(page_names)}"

            system_prompt = (
                "You are a senior UI/UX designer creating a design guide for a website. "
                "Based on the project briefing and design system settings, write a comprehensive "
                "design guide in markdown format that defines visual patterns, component styles, "
                "and conventions to ensure consistency across all pages."
            )

            user_prompt = f"""Site: {site_name}
Briefing: {project_briefing}

Design System Settings:
{settings_summary}
{page_context}

Write a design guide that defines the visual patterns and component conventions.
Focus on: color usage, typography hierarchy, spacing patterns, button styles,
card layouts, section structure, image treatment, and responsive behavior.
Keep it concise and actionable — this guide will be injected into AI prompts
for generating pages to ensure visual consistency."""

            llm = LLMBase()
            messages = [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ]
            response = llm.get_completion(messages, tool_name=get_ai_model('generation'))
            guide = response.choices[0].message.content

            # Strip markdown code fences
            guide = re.sub(r'^```(?:markdown)?\n?', '', guide)
            guide = re.sub(r'\n?```$', '', guide)

            settings.design_guide = guide
            settings.save()
            self.log(f"  Design guide generated ({len(guide)} chars)")

        except Exception as e:
            self.log(f"  Design guide generation failed: {e}")
            self.errors.append({'page': 'design_guide', 'error': str(e)})

    def _build_settings_summary(self, settings) -> str:
        """Build a text summary of current design system settings."""
        lines = []
        for field in ['primary_color', 'secondary_color', 'accent_color',
                       'background_color', 'text_color', 'heading_color',
                       'heading_font', 'body_font', 'h1_font', 'h1_size',
                       'container_width', 'border_radius_preset',
                       'spacing_scale', 'shadow_preset',
                       'button_style', 'button_size']:
            value = getattr(settings, field, None)
            if value:
                lines.append(f"  {field}: {value}")
        return '\n'.join(lines) if lines else '  (defaults)'

    def create_menu_items(self):
        """Create MenuItem records for all generated pages."""
        from djangopress.core.models import MenuItem

        if not self.generated_pages:
            return

        self.log(f"\n--- Creating Menu Items --- {self._elapsed()}")

        # Clear existing top-level menu items
        MenuItem.objects.filter(parent__isnull=True).delete()

        for i, page in enumerate(self.generated_pages):
            item = MenuItem.objects.create(
                label_i18n=page.title_i18n,
                page=page,
                sort_order=i * 10,
                is_active=True,
            )
            self.log(f"  Menu item: {page.default_title}")

    def generate_header(self, plan: Dict):
        """Generate the site header GlobalSection."""
        from djangopress.ai.services import ContentGenerationService
        from djangopress.core.models import GlobalSection

        self.log("\n--- Generating Header ---")

        instructions = plan.get('header_instructions', '')
        if not instructions:
            instructions = (
                f"Create a modern, responsive header for {plan['business_name']}. "
                "Include logo, navigation links to all pages, and a mobile hamburger menu. "
                "Add a language switcher."
            )

        try:
            # Ensure the GlobalSection exists
            section, created = GlobalSection.objects.get_or_create(
                key='main-header',
                defaults={
                    'name': 'Main Header',
                    'section_type': 'header',
                    'is_active': True,
                }
            )

            service = ContentGenerationService(model_name=self.model)
            progress_cb = self._make_page_progress_callback('Header')
            result = service.refine_global_section(
                section_key='main-header',
                refinement_instructions=instructions,
                model_override=get_ai_model('header_footer'),
                on_progress=progress_cb,
            )

            section.html_template_i18n = result.get('html_template_i18n', {})
            section.save()
            html_len = max((len(v) for v in section.html_template_i18n.values()), default=0)
            self.log(f"  Header generated ({html_len} chars)")

        except Exception as e:
            self.log(f"  Header generation failed: {e}")
            self.errors.append({'page': 'header', 'error': str(e)})

    def generate_footer(self, plan: Dict):
        """Generate the site footer GlobalSection."""
        from djangopress.ai.services import ContentGenerationService
        from djangopress.core.models import GlobalSection

        self.log("\n--- Generating Footer ---")

        instructions = plan.get('footer_instructions', '')
        if not instructions:
            instructions = (
                f"Create a footer for {plan['business_name']}. "
                "Include quick links, contact info, social media icons, and copyright."
            )

        try:
            section, created = GlobalSection.objects.get_or_create(
                key='main-footer',
                defaults={
                    'name': 'Main Footer',
                    'section_type': 'footer',
                    'is_active': True,
                }
            )

            service = ContentGenerationService(model_name=self.model)
            progress_cb = self._make_page_progress_callback('Footer')
            result = service.refine_global_section(
                section_key='main-footer',
                refinement_instructions=instructions,
                model_override=get_ai_model('header_footer'),
                on_progress=progress_cb,
            )

            section.html_template_i18n = result.get('html_template_i18n', {})
            section.save()
            html_len = max((len(v) for v in section.html_template_i18n.values()), default=0)
            self.log(f"  Footer generated ({html_len} chars)")

        except Exception as e:
            self.log(f"  Footer generation failed: {e}")
            self.errors.append({'page': 'footer', 'error': str(e)})

    def process_all_images(self):
        """Process images on all generated pages."""
        from djangopress.ai.services import ContentGenerationService
        from djangopress.core.models import SiteSettings

        if not self.generated_pages:
            return

        self.log(f"\n--- Processing Images --- {self._elapsed()}")

        service = ContentGenerationService(model_name=self.model)
        settings = SiteSettings.objects.first()
        languages = settings.get_language_codes() if settings else ['pt', 'en']

        # Determine image strategy
        image_strategy = self.image_strategy or 'ai_generated'
        if image_strategy == 'skip':
            self.log("  Skipping images (strategy: skip)")
            return

        total_processed = 0
        total_failed = 0

        default_lang = settings.get_default_language() if settings else 'pt'

        for page in self.generated_pages:
            html_i18n = page.html_content_i18n or {}
            html = html_i18n.get(default_lang, '') or ''
            soup = BeautifulSoup(html, 'html.parser')

            # Find all images with data-image-prompt or placeholder sources
            images = []
            for idx, img in enumerate(soup.find_all('img')):
                src = img.get('src', '')
                name = img.get('data-image-name', '')
                prompt = img.get('data-image-prompt', '')
                alt = img.get('alt', '')

                if prompt or name or 'placehold.co' in src:
                    images.append({
                        'index': idx,
                        'src': src,
                        'alt': alt,
                        'name': name,
                        'prompt': prompt,
                    })

            if not images:
                continue

            self.log(f"\n  Page: {page.default_title} ({len(images)} images)")

            try:
                # Step 1: AI analyze/suggest prompts
                suggestions = service.analyze_page_images(
                    page_id=page.id,
                    images=images,
                )

                # Step 2: Build decisions based on strategy
                decisions = []
                for img_data in images:
                    name = img_data.get('name', '')
                    src = img_data.get('src', '')

                    # Find matching suggestion
                    suggestion = next(
                        (s for s in suggestions if s.get('index') == img_data['index']),
                        {}
                    )

                    prompt = suggestion.get('prompt', img_data.get('prompt', ''))
                    aspect_ratio = suggestion.get('aspect_ratio', '16:9')
                    library_matches = suggestion.get('library_matches', [])

                    if image_strategy == 'unsplash_preferred':
                        decisions.append({
                            'image_name': name,
                            'image_src': src,
                            'action': 'unsplash',
                            'prompt': prompt,
                            'aspect_ratio': aspect_ratio,
                        })
                    elif library_matches:
                        decisions.append({
                            'image_name': name,
                            'image_src': src,
                            'action': 'library',
                            'library_image_id': library_matches[0],
                        })
                    else:
                        decisions.append({
                            'image_name': name,
                            'image_src': src,
                            'action': 'generate',
                            'prompt': prompt,
                            'aspect_ratio': aspect_ratio,
                        })

                # Step 3: Process
                result = service.process_page_images(
                    page_id=page.id,
                    image_decisions=decisions,
                    languages=languages,
                )

                n_ok = len(result.get('processed', []))
                n_fail = len(result.get('failed', []))
                total_processed += n_ok
                total_failed += n_fail
                self.log(f"    Processed: {n_ok}, Failed: {n_fail}")

                # Delay between pages
                if self.delay > 0:
                    time.sleep(self.delay)

            except Exception as e:
                self.log(f"    Image processing failed: {e}")
                self.errors.append({'page': f'{page.default_title} images', 'error': str(e)})

        self.log(f"\n  Total images: {total_processed} processed, {total_failed} failed")

    def ensure_contact_form(self):
        """Verify the default contact form exists."""
        from djangopress.core.models import DynamicForm

        form = DynamicForm.objects.filter(slug='contact').first()
        if form:
            self.log("\n--- Contact form: exists ---")
        else:
            self.log("\n--- Contact form: creating ---")
            DynamicForm.objects.create(
                name='Contact',
                slug='contact',
                fields_schema=[
                    {'name': 'name', 'type': 'text', 'label': 'Name', 'required': True},
                    {'name': 'email', 'type': 'email', 'label': 'Email', 'required': True},
                    {'name': 'message', 'type': 'textarea', 'label': 'Message', 'required': True},
                ],
                is_active=True,
            )
            self.log("  Contact form created")

    def translate_all_content(self, plan: Dict):
        """Translate all pages and global sections to enabled languages."""
        from djangopress.ai.services import ContentGenerationService
        from djangopress.core.models import SiteSettings

        settings = SiteSettings.objects.first()
        if not settings:
            return

        default_lang = settings.get_default_language()
        language_codes = settings.get_language_codes()
        additional_langs = [lc for lc in language_codes if lc != default_lang]

        if not additional_langs:
            self.log("\n--- Translation: single language, skipping ---")
            return

        self.log(f"\n--- Translating to {', '.join(additional_langs)} --- {self._elapsed()}")

        service = ContentGenerationService(model_name=self.model)

        for target_lang in additional_langs:
            self.log(f"\n  Translating to '{target_lang}'...")
            try:
                result = service.translate_content_to_language(
                    target_lang=target_lang,
                    source_lang=default_lang,
                )
                pages = result.get('translated_pages', 0)
                sections = result.get('translated_sections', 0)
                errors = result.get('errors', [])
                self.log(f"    {pages} pages, {sections} sections translated")
                if errors:
                    for err in errors:
                        self.log(f"    ERROR: {err}")
                        self.errors.append({'translation': err})
            except Exception as e:
                self.log(f"    Translation to '{target_lang}' failed: {e}")
                self.errors.append({'translation': f'{target_lang}: {str(e)}'})

    def validate_generation(self):
        """Post-generation validation — check for common issues."""
        from djangopress.core.models import Page, GlobalSection, SiteSettings

        settings = SiteSettings.objects.first()
        if not settings:
            return

        language_codes = settings.get_language_codes()
        warnings = []

        self.log(f"\n--- Validation --- {self._elapsed()}")

        # Check all pages have content in all languages
        for page in Page.objects.filter(is_active=True):
            html_i18n = page.html_content_i18n or {}
            for lang in language_codes:
                if not html_i18n.get(lang):
                    warnings.append(f'Page "{page.default_title}" missing HTML for language: {lang}')

        # Check global sections have content in all languages
        for section in GlobalSection.objects.filter(is_active=True):
            html_i18n = section.html_template_i18n or {}
            for lang in language_codes:
                if not html_i18n.get(lang):
                    warnings.append(f'GlobalSection "{section.key}" missing HTML for language: {lang}')

        # Check homepage is set
        if not settings.homepage_id:
            warnings.append('No homepage set in SiteSettings')

        if warnings:
            self.log(f"  {len(warnings)} warning(s):")
            for w in warnings:
                self.log(f"    - {w}")
        else:
            self.log("  All checks passed")

    def print_summary(self) -> Dict:
        """Print a summary of what was generated."""
        from djangopress.core.models import GlobalSection

        total_elapsed = time.time() - self._overall_start if self._overall_start else 0
        mins = int(total_elapsed // 60)
        secs = int(total_elapsed % 60)
        elapsed_str = f"{mins}m {secs:02d}s" if mins else f"{secs}s"

        self.log(f"\n{'='*60}")
        self.log(f"Generation Complete: {self.briefing['business_name']} ({elapsed_str})")
        self.log(f"{'='*60}")

        self.log(f"\nPages generated: {len(self.generated_pages)}")
        for page in self.generated_pages:
            self.log(f"  - {page.default_title} (/{page.default_slug}/)")

        header = GlobalSection.objects.filter(key='main-header').first()
        footer = GlobalSection.objects.filter(key='main-footer').first()
        header_ok = header and header.html_template_i18n
        footer_ok = footer and footer.html_template_i18n
        self.log(f"\nHeader: {'generated' if header_ok else 'missing'}")
        self.log(f"Footer: {'generated' if footer_ok else 'missing'}")

        if self.errors:
            self.log(f"\nErrors ({len(self.errors)}):")
            for err in self.errors:
                self.log(f"  - {err['page']}: {err['error'][:100]}")

        self.log(f"\nNext steps:")
        self.log(f"  1. python manage.py runserver 8000")
        self.log(f"  2. Visit http://localhost:8000/ to review the site")
        self.log(f"  3. Use /backoffice/ to refine pages, upload logos, adjust design system")

        return {
            'pages': len(self.generated_pages),
            'header': bool(header_ok),
            'footer': bool(footer_ok),
            'errors': self.errors,
        }

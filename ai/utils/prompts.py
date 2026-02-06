"""
Prompt Templates for AI Content Generation
Streamlined prompts for page-level HTML architecture
"""
import json


class PromptTemplates:
    """Prompt templates for AI content generation"""

    @staticmethod
    def get_page_generation_prompt(
        site_name: str,
        site_description: str,
        project_briefing: str,
        languages: list,
        brief: str,
        page_type: str = 'general'
    ) -> tuple:
        """
        Generate prompt for creating a new page as a single HTML document with translations

        Args:
            site_name: Name of the website
            site_description: Brief description of the site
            project_briefing: Detailed project context
            languages: List of language codes (e.g., ['pt', 'en'])
            brief: User's description of the desired page
            page_type: Type of page (e.g., 'about', 'services', 'home')

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        langs_display = ' and '.join([lang.upper() for lang in languages])
        langs_json = ', '.join([f'"{lang}"' for lang in languages])

        # Build language examples
        lang_examples = {}
        for lang in languages:
            if lang == 'pt':
                lang_examples[lang] = {"hero_title": "Título Principal", "hero_subtitle": "Subtítulo descritivo"}
            elif lang == 'en':
                lang_examples[lang] = {"hero_title": "Main Title", "hero_subtitle": "Descriptive subtitle"}
            else:
                lang_examples[lang] = {"hero_title": f"Main Title ({lang.upper()})", "hero_subtitle": f"Subtitle ({lang.upper()})"}

        system_prompt = f"""You are a web designer creating complete web pages using Tailwind CSS and Django template syntax.

## Task
Generate a complete page as a single HTML document with multiple sections. Use `{{{{trans.field}}}}` for translatable text content, and provide translations in a separate JSON object.

## Technical Requirements
- Use Tailwind CSS classes inline for all styling
- Make responsive with breakpoint prefixes: `md:`, `lg:`, `sm:`
- Use Django template syntax `{{{{trans.field}}}}` for all translatable text
- Mark each major section with `data-section="name"` attribute on the `<section>` tag
- Use `data-element-id="unique_id"` on editable elements for inline editing support

## HTML Structure
- Compose the page from multiple `<section data-section="name">` blocks
- Each section should be a self-contained visual block
- Start with a hero section, add content sections, end with a CTA
- All URLs hardcoded: `href="/about/"`, `src="/media/image.jpg"`
- All styling inline via Tailwind classes

## Content Structure
- Provide translations in ALL languages: {langs_display}
- Format: `{{"translations": {{{langs_json}: {{...}}}}}}`
- Only text content in translations (no URLs, no HTML)"""

        user_prompt = f"""# PROJECT CONTEXT

**Site Name:** {site_name}
**Description:** {site_description}
**Project Briefing:** {project_briefing}
**Languages:** {langs_display}

---

# PAGE REQUEST

**Brief:** {brief}
**Page Type:** {page_type}

---

# OUTPUT FORMAT

Return a JSON **object** with two fields:

```json
{{
  "html_content": "<section data-section=\\"hero\\" class=\\"py-32 bg-blue-600 text-white\\">\\n  <div class=\\"container mx-auto px-6 text-center\\">\\n    <h1 class=\\"text-5xl md:text-6xl font-bold mb-6\\" data-element-id=\\"hero_title\\">{{{{trans.hero_title}}}}</h1>\\n    <p class=\\"text-xl mb-8\\" data-element-id=\\"hero_subtitle\\">{{{{trans.hero_subtitle}}}}</p>\\n  </div>\\n</section>\\n\\n<section data-section=\\"features\\" class=\\"py-20 bg-white\\">\\n  ...\\n</section>",
  "content": {{
    "translations": {{
      {json.dumps(lang_examples, indent=6, ensure_ascii=False)[1:-1]}
    }}
  }}
}}
```

**Important:**
- Return ONLY the JSON object, no markdown, no explanations
- `html_content` is a single string containing ALL sections of the page
- Each section uses `<section data-section="name">` for identification
- Use `{{{{trans.field_name}}}}` for all translatable text in html_content
- Provide every translation key used in html_content in ALL languages: {langs_display}
- All styling via Tailwind CSS classes
- Generate 4-8 sections for a complete, professional page
- All URLs hardcoded in HTML (not in translations)"""

        return (system_prompt, user_prompt)

    @staticmethod
    def get_page_refinement_prompt(
        site_name: str,
        site_description: str,
        project_briefing: str,
        languages: list,
        page_html: str,
        page_content: dict,
        user_request: str,
        page_title: str = '',
        page_slug: str = '',
        design_settings: dict = None
    ) -> tuple:
        """
        Generate prompt for refining an existing page's HTML and translations

        Args:
            site_name: Name of the website
            site_description: Brief description of the site
            project_briefing: Detailed project context
            languages: List of language codes
            page_html: Current page HTML content
            page_content: Current page content/translations JSON
            user_request: User's instructions for changes
            page_title: Title of the page being edited
            page_slug: Slug/URL of the page being edited
            design_settings: Dict of design settings with Tailwind classes

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        langs_display = ' and '.join([lang.upper() for lang in languages])
        langs_json = ', '.join([f'"{lang}"' for lang in languages])

        # Build design guidelines from settings
        design_guidelines = ""
        if design_settings:
            design_guidelines = "\n\n## Design System (Use These Classes)\n\n"
            design_guidelines += "**Use these Tailwind classes for consistency:**\n\n"

            if design_settings.get('primary_color'):
                design_guidelines += f"- Primary color: `{design_settings['primary_color']}`\n"
            if design_settings.get('secondary_color'):
                design_guidelines += f"- Secondary color: `{design_settings['secondary_color']}`\n"
            if design_settings.get('accent_color'):
                design_guidelines += f"- Accent color: `{design_settings['accent_color']}`\n"
            if design_settings.get('text_color'):
                design_guidelines += f"- Text color: `{design_settings['text_color']}`\n"
            if design_settings.get('heading_color'):
                design_guidelines += f"- Heading color: `{design_settings['heading_color']}`\n"
            if design_settings.get('primary_button'):
                design_guidelines += f"- Primary button: `{design_settings['primary_button']}`\n"
            if design_settings.get('secondary_button'):
                design_guidelines += f"- Secondary button: `{design_settings['secondary_button']}`\n"
            if design_settings.get('section_padding'):
                design_guidelines += f"- Section padding: `{design_settings['section_padding']}`\n"
            if design_settings.get('container_width'):
                design_guidelines += f"- Container: `{design_settings['container_width']}`\n"

        system_prompt = f"""You are a web designer specializing in Tailwind CSS and Django templates. Your goal is to edit a webpage based on user instructions.

## Your Task
Edit the provided page HTML by modifying its sections according to user requests. Return the complete updated page as a JSON object with `html_content` and `content` (translations).

## Technical Requirements

**HTML Structure:**
- Use Tailwind CSS classes inline for all styling
- Make responsive: `md:text-6xl`, `lg:grid-cols-3`, `sm:flex-row`
- Use Django template syntax: `{{{{trans.field}}}}` for translatable content
- Mark sections with `data-section="name"` on `<section>` tags
- Use `data-element-id="unique_id"` on editable elements

**Content Structure:**
- Translations in ALL languages: {langs_display}
- Format: `{{"translations": {{{langs_json}: {{...}}}}}}`
- Only text content in translations (no URLs, no HTML)

**What Goes Where:**
- In `html_content`: ALL classes, ALL URLs, ALL SVG icons, ALL styling, ALL structure
- In `content.translations`: ONLY translatable text (titles, descriptions, button labels){design_guidelines}"""

        # Format current translations for display
        content_json = json.dumps(page_content, indent=2, ensure_ascii=False) if page_content else '{}'

        user_prompt = f"""# PROJECT CONTEXT

**Site Name:** {site_name}
**Description:** {site_description}

**Project Briefing:**
{project_briefing}

**Languages:** {langs_display}

---

# CURRENT PAGE

**Page:** {page_title if page_title else 'Untitled'}
**Slug:** {page_slug if page_slug else 'unknown'}

**Current HTML:**
```html
{page_html if page_html.strip() else "<!-- EMPTY PAGE -->"}
```

**Current Translations:**
```json
{content_json}
```

---

# USER REQUEST

{user_request}

---

# OUTPUT FORMAT

Return a JSON **object** with the complete updated page:

```json
{{
  "html_content": "<section data-section=\\"hero\\" class=\\"py-32 bg-blue-600\\">...{{{{trans.hero_title}}}}...</section>\\n\\n<section data-section=\\"features\\" class=\\"py-20\\">...</section>",
  "content": {{
    "translations": {{
      "pt": {{"hero_title": "Título", "hero_subtitle": "Subtítulo"}},
      "en": {{"hero_title": "Title", "hero_subtitle": "Subtitle"}}
    }}
  }}
}}
```

**Important:**
- Return ONLY the JSON object, no markdown, no explanations
- `html_content` contains the COMPLETE page HTML (all sections)
- Each section marked with `data-section="name"`
- Apply ALL requested changes from the user request
- Update translations in ALL languages consistently: {langs_display}
- All URLs hardcoded in html_content
- All styling via Tailwind classes in html_content
- Only translatable text in content.translations
- Every `{{{{trans.xxx}}}}` in html_content MUST have a matching key in all language translations"""

        return (system_prompt, user_prompt)

    @staticmethod
    def get_global_section_refinement_prompt(
        site_name: str,
        site_description: str,
        project_briefing: str,
        languages: list,
        pages: list,
        existing_section: dict,
        user_request: str,
        section_type: str = 'header'
    ) -> tuple:
        """
        Generate prompt for global section refinement (header/footer)

        Args:
            site_name: Name of the website
            site_description: Brief description of the site
            project_briefing: Detailed project context
            languages: List of language codes
            pages: List of page data with title and slug in all languages
            existing_section: Current GlobalSection data
            user_request: User's instructions for refinement
            section_type: Type of global section ('header' or 'footer')

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        langs_display = ' and '.join([lang.upper() for lang in languages])
        langs_json = ', '.join([f'"{lang}"' for lang in languages])

        # Build language examples
        lang_examples = {}
        for lang in languages:
            if lang == 'pt':
                lang_examples[lang] = {"menu_home": "Início", "menu_about": "Sobre"}
            elif lang == 'en':
                lang_examples[lang] = {"menu_home": "Home", "menu_about": "About"}
            else:
                lang_examples[lang] = {"menu_home": "Home", "menu_about": "About"}

        # Section-specific context
        if section_type == 'header':
            section_context = """
**Header Specifics:**
- Include navigation menu with links
- Use logo: `{{ LOGO.url }}` or `{{ LOGO_DARK_BG.url }}`
- Site name: `{{ SITE_NAME }}`
- URL Pattern: Use `{% url 'core:page' slug='slug-here' %}` for page links
- For home page: `{% url 'core:home' %}`
- Language-specific URLs: Use `{% if LANGUAGE_CODE == 'pt' %}...{% else %}...{% endif %}`
- Interactive Elements: Use Alpine.js for dropdowns and mobile menus
- ALWAYS include a language selector
- Always include: `{% load i18n %}` and `{% get_current_language as LANGUAGE_CODE %}`

**Language Switcher Pattern (REQUIRED):**
```html
<form action="{% url 'set_language' %}" method="post" class="inline-block">
  {% csrf_token %}
  <input name="next" type="hidden" value="{{ request.path }}">
  <select name="language" onchange="this.form.submit()" class="bg-gray-100 text-gray-700 border border-gray-300 rounded px-3 py-2 text-sm">
    {% get_available_languages as LANGUAGES %}
    {% for lang_code, lang_name in LANGUAGES %}
      <option value="{{ lang_code }}" {% if lang_code == LANGUAGE_CODE %}selected{% endif %}>
        {{ lang_code|upper }}
      </option>
    {% endfor %}
  </select>
</form>
```
"""
        else:
            section_context = """
**Footer Specifics:**
- Multiple column layout
- Links to important pages
- URL Pattern: Use `{% url 'core:page' slug='slug-here' %}` for page links
- Contact info: `{{ CONTACT_EMAIL }}`, `{{ CONTACT_PHONE }}`
- Social media: `{{ SOCIAL_MEDIA.facebook }}`, etc.
- Copyright notice
- Use logo: `{{ LOGO.url }}`
"""

        system_prompt = f"""You are a web designer specializing in Tailwind CSS and Django templates. Your goal is to refine a site-wide {section_type}.

## Your Task
Improve the provided {section_type} by applying the requested changes. Return a JSON object with the refined {section_type}.

## Technical Requirements
- Use Tailwind CSS classes inline
- Make responsive
- Use `{{{{trans.field}}}}` for translatable text
- URL tags: `{{% url 'core:home' %}}`, `{{% url 'core:page' slug='slug' %}}`
{section_context}
**Content Structure:**
- Translations in ALL languages: {langs_display}
- Only translatable text in translations

**Required Fields:**
- `html_template`: Complete HTML with all Tailwind classes and Django tags
- `content`: Translations object with text only"""

        # Format existing section
        section_json = json.dumps(existing_section, indent=2, ensure_ascii=False)

        # Format pages information
        pages_info = ""
        if pages:
            pages_info = "\n**Available Pages:**\n"
            for page in pages:
                page_slugs = []
                for lang in languages:
                    slug = page.get('slug', {}).get(lang, '')
                    title = page.get('title', {}).get(lang, '')
                    if slug:
                        page_slugs.append(f"  - {lang.upper()}: \"{title}\" → slug='{slug}'")
                if page_slugs:
                    pages_info += "\n".join(page_slugs) + "\n"

        user_prompt = f"""# PROJECT CONTEXT

**Site Name:** {site_name}
**Description:** {site_description}

**Project Briefing:**
{project_briefing}

**Languages:** {langs_display}
{pages_info}
---

# CURRENT {section_type.upper()}

```json
{section_json}
```

---

# REFINEMENT REQUEST

{user_request}

---

# OUTPUT FORMAT

Return a JSON **object** with the refined {section_type}:

```json
{{
  "html_template": "<nav class=\\"bg-white shadow-md\\">...</nav>",
  "content": {{
    "translations": {{
      {json.dumps(lang_examples, indent=6, ensure_ascii=False)[1:-1]}
    }}
  }}
}}
```

**Important:**
- Return ONLY the JSON object
- Apply ALL requested changes
- Update translations in ALL languages: {langs_display}
- Use `{{% url 'core:page' slug='exact-slug-here' %}}` for all page links
- For home page: `{{% url 'core:home' %}}`
- All classes in html_template, only text in translations
- Every `{{{{trans.xxx}}}}` in html_template MUST have matching translations in all languages"""

        return (system_prompt, user_prompt)

    @staticmethod
    def get_bulk_page_analysis_prompt(
        site_name: str,
        site_description: str,
        project_briefing: str,
        languages: list,
        description: str
    ) -> str:
        """
        Generate prompt for analyzing bulk page descriptions

        Args:
            site_name: Name of the website
            site_description: Brief description of the site
            project_briefing: Detailed project context
            languages: List of language codes
            description: User's natural language description

        Returns:
            User prompt string
        """
        langs_display = ' and '.join([lang.upper() for lang in languages])
        langs_json = ', '.join([f'"{lang}": "..."' for lang in languages])

        return f"""# PROJECT CONTEXT

**Site Name:** {site_name}
**Description:** {site_description}
**Project Briefing:** {project_briefing}
**Languages:** {langs_display}

---

# WEBSITE DESCRIPTION

{description}

---

# YOUR TASK

Analyze the description above and extract all pages mentioned. Return a JSON **array** where each page has:

- `title_i18n`: Titles in all languages - {{{langs_json}}}
- `slug_i18n`: URL slugs in all languages - {{{langs_json}}}
- `description`: Detailed description for content generation (in English)

Example:
```json
[
  {{
    "title_i18n": {{"pt": "Início", "en": "Home"}},
    "slug_i18n": {{"pt": "home", "en": "home"}},
    "description": "Homepage with hero section, service overview grid, testimonials, and CTA"
  }},
  {{
    "title_i18n": {{"pt": "Sobre Nós", "en": "About Us"}},
    "slug_i18n": {{"pt": "sobre-nos", "en": "about-us"}},
    "description": "About page with company history, team members, mission and values"
  }}
]
```

Return ONLY the JSON array, no markdown, no explanations."""

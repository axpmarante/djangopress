"""
Prompt Templates for AI Content Generation
Streamlined prompts for page-level HTML architecture
"""
import json


class PromptTemplates:
    """Prompt templates for AI content generation"""

    @staticmethod
    def _format_pages_info(pages, languages):
        """Format available pages as text for prompt injection.

        Args:
            pages: List of dicts with 'title' and 'slug' (both i18n dicts)
            languages: List of language codes
        Returns:
            Formatted string block, or empty string if no pages.
        """
        if not pages:
            return ""
        lines = ["\n**Available Pages (use these slugs for inter-page links):**"]
        for page in pages:
            page_slugs = []
            for lang in languages:
                slug = page.get('slug', {}).get(lang, '')
                title = page.get('title', {}).get(lang, '')
                if slug:
                    page_slugs.append(f"  - {lang.upper()}: \"{title}\" → slug='{slug}'")
            if page_slugs:
                lines.extend(page_slugs)
        return "\n".join(lines) + "\n"

    @staticmethod
    def get_page_generation_prompt(
        site_name: str,
        site_description: str,
        project_briefing: str,
        languages: list,
        brief: str,
    ) -> tuple:
        """
        Generate prompt for creating a new page as a single HTML document with translations

        Args:
            site_name: Name of the website
            site_description: Brief description of the site
            project_briefing: Detailed project context
            languages: List of language codes (e.g., ['pt', 'en'])
            brief: User's description of the desired page

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
        design_guide: str = ''
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
            design_guide: Freeform markdown design guide for AI context

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        langs_display = ' and '.join([lang.upper() for lang in languages])
        langs_json = ', '.join([f'"{lang}"' for lang in languages])

        # Build design guidelines
        design_guidelines = ""
        if design_guide:
            design_guidelines = "\n\n## Design Guide\nFollow these design patterns and conventions:\n" + design_guide

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
        section_type: str = 'header',
        design_guide: str = ''
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

        design_guidelines = ""
        if design_guide:
            design_guidelines = f"""

## Design Guide
Follow these design patterns and conventions:
{design_guide}"""

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
- `content`: Translations object with text only{design_guidelines}"""

        # Format existing section
        section_json = json.dumps(existing_section, indent=2, ensure_ascii=False)

        pages_info = PromptTemplates._format_pages_info(pages, languages)

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

    @staticmethod
    def get_page_metadata_prompt(brief: str, languages: list) -> tuple:
        """
        Generate prompt for suggesting page title and slug from the brief.

        Args:
            brief: User's description of the desired page
            languages: List of language codes

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        langs_display = ' and '.join([lang.upper() for lang in languages])
        langs_json = ', '.join([f'"{lang}": "..."' for lang in languages])

        system_prompt = "You are a web content specialist. Given a page description, suggest a concise page title and a URL-safe slug for each language."

        user_prompt = f"""Given this page description, suggest a title and slug in each language: {langs_display}

**Page Description:**
{brief}

Return a JSON object:
```json
{{
  "title_i18n": {{{langs_json}}},
  "slug_i18n": {{{langs_json}}}
}}
```

**Rules:**
- Titles should be concise (2-5 words), suitable for navigation menus
- Slugs must be lowercase, hyphenated, URL-safe (a-z, 0-9, hyphens only)
- Translate naturally for each language (not literal word-for-word)
- Return ONLY the JSON object, no markdown, no explanations"""

        return (system_prompt, user_prompt)

    # =========================================================================
    # Two-Step Generation Prompts
    # =========================================================================

    @staticmethod
    def get_page_generation_html_prompt(
        site_name: str,
        site_description: str,
        project_briefing: str,
        default_language: str,
        brief: str,
        has_reference_images: bool = False,
        design_guide: str = '',
        pages: list = None,
        languages: list = None
    ) -> tuple:
        """
        Generate prompt for Step 1: create clean HTML with real text in the default language.
        No {{ trans.xxx }} variables, no JSON wrapping — just raw HTML.

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        lang_name = {'pt': 'Portuguese', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian'}.get(default_language, default_language.upper())

        system_prompt = f"""You are a web designer creating complete web pages using Tailwind CSS.

## Task
Generate a complete, professional web page as clean HTML with real text content written in {lang_name}.

## Technical Requirements
- Use Tailwind CSS classes inline for all styling
- Make responsive with breakpoint prefixes: `sm:`, `md:`, `lg:`
- Use Alpine.js (`x-data`, `x-show`, `@click`) for interactive elements if needed
- Write all text content directly in {lang_name} — do NOT use template variables or placeholders

## HTML Structure
- Compose the page from multiple `<section>` blocks
- Each `<section>` MUST have `data-section="name"` and `id="name"` attributes
- Use `data-element-id="unique_id"` on editable text elements (headings, paragraphs, buttons, links)
- Start with a hero section, add content sections, end with a CTA
- All URLs hardcoded: `href="/about/"`, `src="/media/image.jpg"`
- Generate 4-8 sections for a complete, professional page

## CRITICAL: Page Content Only
- Do NOT include `<html>`, `<head>`, `<body>`, `<header>`, `<nav>`, or `<footer>` tags
- Do NOT include any navigation menus, site headers, or site footers
- The header and footer are managed separately as global site components
- Your output is ONLY the page body content — a series of `<section>` blocks
- Do NOT include `<script>` or `<link>` tags for Tailwind/Alpine — they are already loaded

## Important
- Write ALL text in {lang_name} — real words, real sentences
- Do NOT use `{{{{ trans.xxx }}}}` or any template variables for text
- Do NOT wrap the output in JSON
- Return ONLY the HTML, no markdown code blocks, no explanations"""

        if design_guide:
            system_prompt += f"""

## Design Guide
Follow these design patterns and conventions:
{design_guide}"""

        if has_reference_images:
            system_prompt += """

## Reference Images
The user has provided reference design images. Use them as visual inspiration for:
- Layout structure and section arrangement
- Color scheme and visual style
- Typography and spacing patterns
- Overall aesthetic and mood
Match the design style shown in the images while following all other technical requirements."""

        pages_info = PromptTemplates._format_pages_info(pages, languages or [])

        user_prompt = f"""# PROJECT CONTEXT

**Site Name:** {site_name}
**Description:** {site_description}
**Project Briefing:** {project_briefing}
**Language:** {lang_name}
{pages_info}
---

# PAGE REQUEST

**Brief:** {brief}

---

Return ONLY the raw HTML for this page. All text must be real content in {lang_name}. No template variables, no JSON, no code blocks."""

        return (system_prompt, user_prompt)

    @staticmethod
    def get_page_refinement_html_prompt(
        site_name: str,
        site_description: str,
        project_briefing: str,
        default_language: str,
        page_html: str,
        user_request: str,
        page_title: str = '',
        page_slug: str = '',
        design_guide: str = '',
        has_reference_images: bool = False,
        handle_images: bool = False,
        pages: list = None,
        languages: list = None
    ) -> tuple:
        """
        Generate prompt for Step 1 of refinement: edit clean HTML with real text.
        The HTML has already been de-templatized (real text, no {{ trans.xxx }}).

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        lang_name = {'pt': 'Portuguese', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian'}.get(default_language, default_language.upper())

        # Build design guidelines
        design_guidelines = ""
        if design_guide:
            design_guidelines = "\n\n## Design Guide\nFollow these design patterns and conventions:\n" + design_guide

        system_prompt = f"""You are a web designer specializing in Tailwind CSS. Your goal is to edit a webpage based on user instructions.

## Your Task
Edit the provided HTML page by applying the requested changes. Return the complete updated HTML.

## Technical Requirements
- Use Tailwind CSS classes inline for all styling
- Make responsive: `md:text-6xl`, `lg:grid-cols-3`, `sm:flex-row`
- Each `<section>` MUST have `data-section="name"` and `id="name"` attributes
- Use `data-element-id="unique_id"` on editable text elements
- All text is in {lang_name} — keep it that way, do NOT use template variables

## CRITICAL: Page Content Only
- Do NOT include `<html>`, `<head>`, `<body>`, `<header>`, `<nav>`, or `<footer>` tags
- Do NOT include any navigation menus, site headers, or site footers
- The header and footer are managed separately as global site components
- Output ONLY the page body content — a series of `<section>` blocks
- Do NOT include `<script>` or `<link>` tags for Tailwind/Alpine — they are already loaded

## Important
- Return ONLY the complete updated HTML
- Do NOT use `{{{{ trans.xxx }}}}` or any template variables
- Do NOT wrap the output in JSON
- No markdown code blocks, no explanations{design_guidelines}"""

        if handle_images:
            system_prompt += """

## Image Handling
For every image on the page:
- Use a placeholder src: `https://placehold.co/{width}x{height}?text={Short+Label}`
- Add `data-image-prompt="detailed description for AI image generation"` attribute
- Add `data-image-name="descriptive-slug-name"` attribute
- Write rich, specific prompts (style, subject, mood, setting) in data-image-prompt
- Choose appropriate dimensions for each image's context (hero: 1200x600, card: 600x400, avatar: 400x400, etc.)
- Example: <img src="https://placehold.co/800x400?text=Hero+Image" data-image-name="hero-banner" data-image-prompt="Aerial photo of luxury villa with infinity pool overlooking ocean at golden hour, Mediterranean architecture" alt="..." class="...">"""

        if has_reference_images:
            system_prompt += """

## Reference Images
The user has provided reference design images. Use them as visual inspiration for:
- Layout structure and section arrangement
- Color scheme and visual style
- Typography and spacing patterns
- Overall aesthetic and mood
Match the design style shown in the images while following all other technical requirements."""

        pages_info = PromptTemplates._format_pages_info(pages, languages or [])

        user_prompt = f"""# PROJECT CONTEXT

**Site Name:** {site_name}
**Description:** {site_description}

**Project Briefing:**
{project_briefing}
{pages_info}
---

# CURRENT PAGE

**Page:** {page_title if page_title else 'Untitled'}
**Slug:** {page_slug if page_slug else 'unknown'}
**Language:** {lang_name}

**Current HTML:**
{page_html if page_html.strip() else "<!-- EMPTY PAGE -->"}

---

# USER REQUEST

{user_request}

---

Return ONLY the complete updated HTML. All text in {lang_name}. No template variables, no JSON, no code blocks."""

        return (system_prompt, user_prompt)

    @staticmethod
    def get_chat_refinement_html_prompt(
        site_name: str,
        site_description: str,
        project_briefing: str,
        default_language: str,
        page_html: str,
        user_request: str,
        page_title: str = '',
        page_slug: str = '',
        design_guide: str = '',
        has_reference_images: bool = False,
        conversation_history: str = '',
        handle_images: bool = False,
        pages: list = None,
        languages: list = None
    ) -> tuple:
        """
        Wraps get_page_refinement_html_prompt and injects conversation history
        into the user prompt so the LLM preserves previous refinements.

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        system_prompt, user_prompt = PromptTemplates.get_page_refinement_html_prompt(
            site_name=site_name,
            site_description=site_description,
            project_briefing=project_briefing,
            default_language=default_language,
            page_html=page_html,
            user_request=user_request,
            page_title=page_title,
            page_slug=page_slug,
            design_guide=design_guide,
            has_reference_images=has_reference_images,
            handle_images=handle_images,
            pages=pages,
            languages=languages,
        )

        if conversation_history:
            history_block = f"""# PREVIOUS REFINEMENTS

This page has been refined through a conversation. Here is what has been done so far:

{conversation_history}

Do NOT undo any of these previous changes unless specifically asked to.

---

"""
            # Insert before the # USER REQUEST section
            user_prompt = user_prompt.replace(
                '# USER REQUEST',
                history_block + '# USER REQUEST',
            )

        return (system_prompt, user_prompt)

    @staticmethod
    def get_image_analysis_prompt(
        site_name: str,
        project_briefing: str,
        design_guide: str,
        page_title: str,
        page_html: str,
        images: list,
        library_catalog: list
    ) -> tuple:
        """
        Generate prompt for analyzing page images and suggesting generation prompts
        plus matching library images.

        Args:
            site_name: Name of the website
            project_briefing: Detailed project context
            design_guide: Freeform markdown design guide
            page_title: Title of the page
            page_html: De-templatized page HTML (real text)
            images: List of dicts with index, src, alt, name
            library_catalog: List of dicts with id, title, alt_text, key, category, tags

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        system_prompt = """You are an image consultant for a website. Given page context and a list of images that need real photos, your job is to:

1. **Suggest a detailed AI image generation prompt** for each image — photographic, specific, describing subject, style, lighting, composition, and mood.
2. **Pick the best aspect ratio** from: 1:1, 16:9, 4:3, 3:2, 9:16 — based on where the image sits in the layout.
3. **Find up to 3 matching images** from the media library catalog (by ID), ordered by relevance. Return an empty array if none fit.

Return a JSON array. No markdown, no explanations — just the JSON."""

        images_json = json.dumps(images, indent=2, ensure_ascii=False)

        library_section = ""
        if library_catalog:
            library_json = json.dumps(library_catalog, indent=2, ensure_ascii=False)
            library_section = f"""
## Media Library Catalog

These images are already available. Return their IDs as `library_matches` if they fit:

```json
{library_json}
```
"""
        else:
            library_section = "\n## Media Library\nThe media library is empty. Return `library_matches: []` for all images.\n"

        design_section = ""
        if design_guide:
            design_section = f"\n## Design Guide\n{design_guide}\n"

        user_prompt = f"""## Site: {site_name}

## Project Briefing
{project_briefing}
{design_section}
## Page: {page_title}

```html
{page_html}
```

## Images to Analyze

```json
{images_json}
```
{library_section}
## Output Format

Return a JSON array:
```json
[
  {{
    "index": 0,
    "prompt": "Professional photo of a modern dental clinic reception area with clean white walls, natural light streaming through large windows, potted plants, and a welcoming receptionist smiling at camera",
    "aspect_ratio": "16:9",
    "library_matches": [42, 17, 8]
  }}
]
```

Rules:
- Write detailed, photographic prompts suitable for AI image generation (30-60 words each)
- Pick aspect ratio based on image context (hero banners → 16:9, profile photos → 1:1, tall cards → 3:2, etc.)
- Return up to 3 library image IDs that best match, ordered by relevance, or [] if none fit
- Return ONLY the JSON array"""

        return (system_prompt, user_prompt)

    @staticmethod
    def get_templatize_and_translate_prompt(
        html: str,
        languages: list,
        default_language: str
    ) -> tuple:
        """
        Generate prompt for Step 2: extract text, assign variable names, and translate.
        Returns a mapping JSON — the caller does the HTML replacement in Python.

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        langs_display = ' and '.join([lang.upper() for lang in languages])
        lang_name = {'pt': 'Portuguese', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian'}.get(default_language, default_language.upper())

        system_prompt = f"""You are a localization specialist. Your job is to extract all human-readable text from HTML and produce a variable mapping with translations.

## What to Extract
- ALL visible text: headings, paragraphs, button labels, link text, list items, spans, etc.
- Extract the EXACT text as it appears (preserve whitespace trimming)
- Do NOT extract: HTML tags, CSS classes, URLs, attribute values, SVG code, Alpine.js directives, HTML comments

## Variable Naming
- Use descriptive names based on the `data-section` attribute and element role: `hero_title`, `hero_subtitle`, `features_card1_title`, `cta_button`
- For elements with `data-element-id`, use that as the variable name
- Keep names short and descriptive using snake_case

## Translation Rules
- The original text is in {lang_name} — use it as the {default_language.upper()} translation
- Provide natural, fluent translations for ALL other languages
- Only text strings — no HTML, no URLs"""

        user_prompt = f"""# HTML TO PROCESS

Extract all text from this HTML, assign variable names, and translate to: {langs_display}

```html
{html}
```

---

# OUTPUT FORMAT

Return a JSON **array** of objects. Each object maps one text string:

```json
[
  {{
    "var": "hero_title",
    "original": "Welcome to Our Site",
    "translations": {{
      "{default_language}": "Welcome to Our Site",
      "...": "..."
    }}
  }}
]
```

**Rules:**
- Return ONLY the JSON array, no markdown, no explanations
- `original` must be the EXACT text from the HTML (trimmed of leading/trailing whitespace)
- Every text string visible to users must be included
- `translations` must include ALL languages: {langs_display}
- The {default_language.upper()} translation must match `original` exactly
- Do NOT include alt attributes, title attributes, or meta content — only visible body text"""

        return (system_prompt, user_prompt)

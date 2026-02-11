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
    def _get_components_reference():
        """Return HTML patterns doc for interactive components pre-loaded in base.html."""
        return """

## Interactive Components (Available Libraries)

The following JS libraries are pre-loaded and auto-initialize from HTML attributes. Use them when the user requests interactive elements.

### Carousel / Slider (Splide.js)
```html
<div class="splide" data-splide='{"type":"loop","perPage":3,"gap":"1.5rem","breakpoints":{"768":{"perPage":1},"1024":{"perPage":2}}}'>
  <div class="splide__track">
    <ul class="splide__list">
      <li class="splide__slide"><!-- slide content --></li>
      <li class="splide__slide"><!-- slide content --></li>
    </ul>
  </div>
</div>
```
Options: `type` (slide|loop|fade), `perPage`, `gap`, `autoplay`, `interval`, `breakpoints`, `arrows`, `pagination`.

### Image Lightbox / Gallery
```html
<div class="grid grid-cols-3 gap-4">
  <a href="/media/full-image.jpg" data-lightbox="gallery-name">
    <img src="/media/thumb.jpg" alt="Description" class="rounded-lg">
  </a>
</div>
```
Use `data-lightbox="same-group-name"` on `<a>` wrapping each image. Images with the same group name become a navigable gallery.

### Tabs (Alpine.js)
```html
<div x-data="{ tab: 'tab1' }">
  <div class="flex border-b">
    <button @click="tab = 'tab1'" :class="tab === 'tab1' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500'" class="px-4 py-2 font-medium">Tab 1</button>
    <button @click="tab = 'tab2'" :class="tab === 'tab2' ? 'border-b-2 border-blue-500 text-blue-600' : 'text-gray-500'" class="px-4 py-2 font-medium">Tab 2</button>
  </div>
  <div class="relative overflow-hidden min-h-[400px]">
    <div class="absolute inset-0 p-6" x-show="tab === 'tab1'" x-transition:enter="transition ease-out duration-300" x-transition:enter-start="opacity-0" x-transition:enter-end="opacity-100" x-transition:leave="transition ease-in duration-200" x-transition:leave-start="opacity-100" x-transition:leave-end="opacity-0">Content 1</div>
    <div class="absolute inset-0 p-6" x-show="tab === 'tab2'" x-cloak x-transition:enter="transition ease-out duration-300" x-transition:enter-start="opacity-0" x-transition:enter-end="opacity-100" x-transition:leave="transition ease-in duration-200" x-transition:leave-start="opacity-100" x-transition:leave-end="opacity-0">Content 2</div>
  </div>
</div>
```
CRITICAL for tabs: Each panel MUST use `absolute inset-0` so panels stack on top of each other — this prevents flicker from both panels being visible during transitions. The container needs `relative overflow-hidden min-h-[400px]` (adjust height as needed). Add `x-cloak` on initially-hidden panels. Move padding from the container to each panel (`p-6` or `p-8 md:p-12`).

### Accordion (Alpine.js)
```html
<div x-data="{ open: null }" class="space-y-2">
  <div class="border rounded-lg">
    <button @click="open = open === 1 ? null : 1" class="w-full flex justify-between items-center p-4 font-medium">
      <span>Question 1</span>
      <svg :class="open === 1 && 'rotate-180'" class="w-5 h-5 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
    </button>
    <div x-show="open === 1" x-collapse>
      <div class="p-4 pt-0">Answer 1</div>
    </div>
  </div>
</div>
```

### Modal (Alpine.js)
```html
<div x-data="{ open: false }">
  <button @click="open = true" class="px-4 py-2 bg-blue-600 text-white rounded">Open Modal</button>
  <div x-show="open" x-transition.opacity class="fixed inset-0 bg-black/50 z-40" @click="open = false"></div>
  <div x-show="open" x-transition class="fixed inset-0 z-50 flex items-center justify-center p-4" @click.self="open = false">
    <div class="bg-white rounded-xl shadow-xl max-w-lg w-full p-6">
      <h3 class="text-xl font-bold mb-4">Modal Title</h3>
      <p>Modal content here.</p>
      <button @click="open = false" class="mt-4 px-4 py-2 bg-gray-200 rounded">Close</button>
    </div>
  </div>
</div>
```

### Form Submission (Dynamic Forms)
Forms are handled by the DynamicForm system. Each form has a **slug** and a submission endpoint at `/forms/SLUG/submit/`.

**How it works:**
1. A `DynamicForm` record must exist in the database with a matching slug (e.g. slug=`contact`)
2. The HTML form's `action` points to `/forms/SLUG/submit/`
3. On submit, all form fields are saved as JSON and the site owner gets an email notification
4. Common slugs: `contact`, `quote-request`, `booking`, `newsletter`

```html
<form action="/forms/contact/submit/" method="post" class="space-y-6">
  {{% csrf_token %}}
  <!-- Honeypot - do NOT remove -->
  <div style="position:absolute;left:-9999px;" aria-hidden="true">
    <input type="text" name="website_url" tabindex="-1" autocomplete="off">
  </div>
  <input type="text" name="name" required placeholder="..." class="w-full px-4 py-3 border rounded-lg">
  <input type="email" name="email" required placeholder="..." class="w-full px-4 py-3 border rounded-lg">
  <textarea name="message" rows="5" required placeholder="..." class="w-full px-4 py-3 border rounded-lg"></textarea>
  <button type="submit" class="...">{{{{ trans.form_submit }}}}</button>
</form>
```

**Rules:**
- The `action` MUST be `/forms/SLUG/submit/` where SLUG matches a DynamicForm slug
- Always include `{{% csrf_token %}}`
- Input `name` attributes are fixed identifiers (not translated) — they become the JSON keys in the submission
- Use `{{{{ trans.xxx }}}}` for visible text: labels, placeholders, and button text
- For checkbox fields use `<input type="checkbox" name="consent">`
- Always include the honeypot field exactly as shown (the hidden `website_url` input). Do not change the field name `website_url`
- The form slug MUST correspond to an existing DynamicForm record — if no form exists for that slug, submissions will fail

**Rules:**
- Always use the exact class names shown (e.g. `splide`, `splide__track`, `splide__list`, `splide__slide`)
- Splide options go in the `data-splide` JSON attribute — do NOT add inline `<script>` tags
- Lightbox uses `data-lightbox` on `<a>` tags wrapping images
- Alpine.js components use `x-data`, `x-show`, `x-transition`, `x-collapse`, `@click`
- All components are responsive — use Tailwind breakpoint classes and Splide `breakpoints` option
"""

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

## Images
When adding images, NEVER use external URLs (Unsplash, Pexels, etc.). Use placeholder images:
- `<img>` tags: use `src="https://placehold.co/WIDTHxHEIGHT?text=Short+Label"` with `data-image-prompt="detailed description for AI image generation"` and `data-image-name="slug_name"`
- Background images: use a CSS background-color as fallback and add a child `<img>` with `class="absolute inset-0 w-full h-full object-cover"` using the same placeholder pattern
- Choose appropriate dimensions: hero 1200x600, cards 600x400, avatars 400x400, etc.
- Write rich, specific prompts in data-image-prompt (style, subject, mood, setting)

## Content Structure
- Provide translations in ALL languages: {langs_display}
- Format: `{{"translations": {{{langs_json}: {{...}}}}}}`
- Only text content in translations (no URLs, no HTML)
{PromptTemplates._get_components_reference()}"""

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
        design_guide: str = '',
        menu_items: list = None
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
            menu_items: List of menu item dicts with label_i18n, page slugs, url, etc.

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

        # Build menu items info for the prompt
        menu_info = ""
        if menu_items:
            menu_lines = ["\n**Menu Items (from database — use MENU_ITEMS loop):**"]
            for item in menu_items:
                labels = item.get('label_i18n', {})
                label_parts = [f"{lang.upper()}: \"{labels.get(lang, '')}\"" for lang in languages if labels.get(lang)]
                page_slug = item.get('page_slug', '')
                custom_url = item.get('url', '')
                target = f"page slug='{page_slug}'" if page_slug else f"url='{custom_url}'"
                children = item.get('children', [])
                if children:
                    menu_lines.append(f"  - {', '.join(label_parts)} → {target} **[has dropdown children]**")
                    for child in children:
                        child_labels = child.get('label_i18n', {})
                        child_label_parts = [f"{lang.upper()}: \"{child_labels.get(lang, '')}\"" for lang in languages if child_labels.get(lang)]
                        child_slug = child.get('page_slug', '')
                        child_url = child.get('url', '')
                        child_target = f"page slug='{child_slug}'" if child_slug else f"url='{child_url}'"
                        menu_lines.append(f"    - {', '.join(child_label_parts)} → {child_target}")
                else:
                    menu_lines.append(f"  - {', '.join(label_parts)} → {target}")
            menu_info = "\n".join(menu_lines)

        pages_info = PromptTemplates._format_pages_info(pages, languages)

        # Section-specific context
        if section_type == 'header':
            section_context = f"""
**Header Specifics:**
- Include navigation menu with links
- Use logo: `{{{{ LOGO.url }}}}` or `{{{{ LOGO_DARK_BG.url }}}}`
- Site name: `{{{{ SITE_NAME }}}}`
- Interactive Elements: Use Alpine.js for dropdowns and mobile menus
- ALWAYS include a language selector
- Always include: `{{% load i18n %}}`, `{{% load section_tags %}}`, and `{{% get_current_language as LANGUAGE_CODE %}}`

**Navigation Menu — REQUIRED PATTERN:**
Menu items are stored in the database and available via `MENU_ITEMS` context variable (top-level items only).
Each item may have `item.children.all` for dropdown sub-items.
Use the `get_menu_label` and `get_menu_url` template filters (from `section_tags`) to render them.
Do NOT hardcode page links. Use this loop pattern:

**Desktop nav — items with children get an Alpine.js dropdown:**
```html
{{% for item in MENU_ITEMS %}}
  {{% if item.children.all %}}
  <div x-data="{{{{ open: false }}}}" @mouseenter="open = true" @mouseleave="open = false" class="relative">
    <button @click="open = !open" class="inline-flex items-center text-sm font-semibold ...">
      {{{{ item|get_menu_label:LANGUAGE_CODE }}}}
      <svg class="ml-1 h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
    </button>
    <div x-show="open" x-cloak x-transition class="absolute left-0 mt-2 w-48 rounded-md bg-white shadow-lg ring-1 ring-black/5 z-50">
      {{% for child in item.children.all %}}
      <a href="{{{{ child|get_menu_url:LANGUAGE_CODE }}}}" class="block px-4 py-2 text-sm ..."{{% if child.open_in_new_tab %}} target="_blank"{{% endif %}}>{{{{ child|get_menu_label:LANGUAGE_CODE }}}}</a>
      {{% endfor %}}
    </div>
  </div>
  {{% else %}}
  <a href="{{{{ item|get_menu_url:LANGUAGE_CODE }}}}" class="text-sm font-semibold ..."{{% if item.open_in_new_tab %}} target="_blank"{{% endif %}}>{{{{ item|get_menu_label:LANGUAGE_CODE }}}}</a>
  {{% endif %}}
{{% endfor %}}
```

**Mobile nav — children shown nested under parent:**
```html
{{% for item in MENU_ITEMS %}}
  {{% if item.children.all %}}
  <div x-data="{{{{ open: false }}}}">
    <button @click="open = !open" class="flex w-full items-center justify-between ...">
      {{{{ item|get_menu_label:LANGUAGE_CODE }}}}
      <svg :class="{{'rotate-180': open}}" class="h-4 w-4 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
    </button>
    <div x-show="open" x-cloak class="pl-4 mt-1 space-y-1">
      {{% for child in item.children.all %}}
      <a href="{{{{ child|get_menu_url:LANGUAGE_CODE }}}}" class="block ..."{{% if child.open_in_new_tab %}} target="_blank"{{% endif %}}>{{{{ child|get_menu_label:LANGUAGE_CODE }}}}</a>
      {{% endfor %}}
    </div>
  </div>
  {{% else %}}
  <a href="{{{{ item|get_menu_url:LANGUAGE_CODE }}}}" class="block ..."{{% if item.open_in_new_tab %}} target="_blank"{{% endif %}}>{{{{ item|get_menu_label:LANGUAGE_CODE }}}}</a>
  {{% endif %}}
{{% endfor %}}
```

- `get_menu_url` returns the correct language-specific URL for each menu item (handles page slugs per language automatically)
- `get_menu_label` returns the label in the current language
- Use `item.children.all` to check for and iterate over sub-items — these are prefetched and ready to use
- Do NOT use `MENU_ITEMS.last` or any index-based access — the user can reorder items at any time
- Do NOT use `{{{{ trans.menu_xxx }}}}` for menu labels — the menu items have their own i18n labels
- For CTA buttons, use `{{{{ trans.cta_text }}}}` for the label and `/forms/contact/submit/` or a `{{{{ trans.xxx }}}}` variable for the URL — keep CTAs separate from the menu loop
- You can still use `{{{{ trans.xxx }}}}` for other translatable text (taglines, CTAs, etc.)
{menu_info}

**Language Switcher Pattern (REQUIRED):**
```html
<form action="{{% url 'set_language' %}}" method="post" class="inline-block">
  {{% csrf_token %}}
  <input name="next" type="hidden" value="{{{{ request.path }}}}">
  <select name="language" onchange="this.form.submit()" class="bg-gray-100 text-gray-700 border border-gray-300 rounded px-3 py-2 text-sm">
    {{% get_available_languages as LANGUAGES %}}
    {{% for lang_code, lang_name in LANGUAGES %}}
      <option value="{{{{ lang_code }}}}" {{% if lang_code == LANGUAGE_CODE %}}selected{{% endif %}}>
        {{{{ lang_code|upper }}}}
      </option>
    {{% endfor %}}
  </select>
</form>
```
"""
        else:
            section_context = f"""
**Footer Specifics:**
- Multiple column layout with link groups
- Contact info: `{{{{ CONTACT_EMAIL }}}}`, `{{{{ CONTACT_PHONE }}}}`
- Social media: `{{{{ SOCIAL_MEDIA.facebook }}}}`, `{{{{ SOCIAL_MEDIA.instagram }}}}`, etc.
- Copyright notice with current year
- Use logo: `{{{{ LOGO.url }}}}`
- Always include: `{{% load i18n %}}` and `{{% get_current_language as LANGUAGE_CODE %}}`

**Footer Navigation Links:**
- Use `{{% url 'core:page' slug='slug-here' %}}` for page links
- For home page: `{{% url 'core:home' %}}`
- For pages with different slugs per language, use: `{{% if LANGUAGE_CODE == 'pt' %}}{{% url 'core:page' slug='pt-slug' %}}{{% else %}}{{% url 'core:page' slug='en-slug' %}}{{% endif %}}`
- Use `{{{{ trans.xxx }}}}` for all link labels and other translatable text
- Do NOT use MENU_ITEMS — footer links are managed directly in the template
- Refer to the Available Pages list below for correct slugs in each language

{pages_info}
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
- For home page link: `{{% url 'core:home' %}}`
{section_context}
**Content Structure:**
- Translations in ALL languages: {langs_display}
- Only translatable text in translations

**Required Fields:**
- `html_template`: Complete HTML with all Tailwind classes and Django tags
- `content`: Translations object with text only{design_guidelines}"""

        # Format existing section
        section_json = json.dumps(existing_section, indent=2, ensure_ascii=False)

        # Section-specific navigation reminders for the user prompt
        if section_type == 'header':
            nav_reminder = f"""- Use `{{% for item in MENU_ITEMS %}}` loop with `get_menu_url` and `get_menu_label` filters for navigation — do NOT hardcode page links
- For items with children, use `{{% if item.children.all %}}` to render Alpine.js dropdown menus, and `{{% for child in item.children.all %}}` for sub-items
- Include `{{% load section_tags %}}` at the top of html_template (alongside `{{% load i18n %}}`)
- Menu labels come from `MENU_ITEMS` — do NOT add them to translations"""
        else:
            nav_reminder = f"""- Use `{{% url 'core:page' slug='...' %}}` for page links — do NOT use MENU_ITEMS
- Include `{{% load i18n %}}` at the top of html_template"""

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
- For home page: `{{% url 'core:home' %}}`
{nav_reminder}
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

    # =========================================================================
    # Blueprint Prompts
    # =========================================================================

    @staticmethod
    def get_suggest_sections_prompt(
        site_name: str,
        project_briefing: str,
        page_title: str,
        page_description: str,
        existing_sections: list,
        all_pages_info: list,
    ) -> tuple:
        """
        Suggest 4-8 sections for a blueprint page.
        Returns (system_prompt, user_prompt).
        """
        system_prompt = """You are a web content strategist. Given a page title, description, and project context, suggest 4-8 content sections for the page.

Return a JSON array where each item has:
- "id": a short kebab-case identifier (e.g. "hero", "services-grid", "testimonials")
- "title": human-readable section title
- "content": a detailed markdown content plan for this section (5-15 lines). For each section describe:
  - What headings and body text should say (specific, not generic)
  - Calls to action (button labels, where they link)
  - Visual elements (images, icons, background treatment)
  - Tone and key messages
  - Any data points, features, or items to list
  - Layout hints (grid, cards, split layout, etc.)
- "order": integer starting at 0

The content field is a planning document that will guide HTML generation — be specific and actionable, not vague.

Return ONLY the JSON array. No markdown code blocks, no explanations."""

        existing_info = ""
        if existing_sections:
            titles = [s.get('title', '') for s in existing_sections if s.get('title')]
            if titles:
                existing_info = f"\n\n**Existing sections (keep or improve these):** {', '.join(titles)}"

        pages_list = ""
        if all_pages_info:
            pages_list = "\n**Other pages in the site:** " + ", ".join(
                [p.get('title', '') for p in all_pages_info if p.get('title')]
            )

        user_prompt = f"""**Site:** {site_name}
**Project Briefing:** {project_briefing}

**Page Title:** {page_title}
**Page Description:** {page_description}{existing_info}{pages_list}

Suggest 4-8 content sections for this page. Return ONLY the JSON array."""

        return (system_prompt, user_prompt)

    @staticmethod
    def get_fill_section_content_prompt(
        site_name: str,
        project_briefing: str,
        page_title: str,
        section_title: str,
        section_id: str,
        other_sections: list,
        context: str = '',
    ) -> tuple:
        """
        Fill markdown content for a single blueprint section.
        Returns (system_prompt, user_prompt).
        """
        system_prompt = """You are a web content writer. Write a concise markdown description (5-15 lines) for a website section.

This is a content plan, not final copy. Describe:
- What content appears in this section (headings, body text, lists, CTAs)
- The tone and key messages
- Any specific data points or features to highlight

Write in plain markdown. No code blocks wrapping the output, no JSON. Just the markdown content."""

        other_info = ""
        if other_sections:
            parts = []
            for s in other_sections:
                title = s.get('title', '')
                content = s.get('content', '')
                if title:
                    if content:
                        parts.append(f"### {title}\n{content}")
                    else:
                        parts.append(f"### {title}\n(no content yet)")
            if parts:
                other_info = "\n\n**Other sections on this page (for context — avoid repeating their content):**\n" + "\n\n".join(parts)

        context_info = ""
        if context:
            context_info = f"\n**Additional instructions:** {context}"

        user_prompt = f"""**Site:** {site_name}
**Project Briefing:** {project_briefing}
**Page:** {page_title}
**Section to write:** {section_title} (id: {section_id}){context_info}{other_info}

Write 5-15 lines of markdown describing the planned content for this section. Do not repeat content already covered by other sections."""

        return (system_prompt, user_prompt)

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
        languages: list = None,
        outline: list = None
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
{PromptTemplates._get_components_reference()}
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

        # Build outline block if provided
        outline_block = ""
        if outline:
            outline_lines = ["\n## CONTENT PLAN\nFollow this section structure. Use the provided `data-section` ids.\n"]
            for section in outline:
                sid = section.get('id', '')
                stitle = section.get('title', '')
                scontent = section.get('content', '')
                outline_lines.append(f"### `data-section=\"{sid}\"` — {stitle}")
                if scontent:
                    outline_lines.append(scontent)
                outline_lines.append("")
            outline_block = "\n".join(outline_lines)

        user_prompt = f"""# PROJECT CONTEXT

**Site Name:** {site_name}
**Description:** {site_description}
**Project Briefing:** {project_briefing}
**Language:** {lang_name}
{pages_info}
---

# PAGE REQUEST

**Brief:** {brief}
{outline_block}
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
- No markdown code blocks, no explanations

## Images
- **PRESERVE existing image `src` URLs exactly as they are.** Do NOT replace, remove, or change any existing `src` attribute unless the user explicitly asks to change the image itself.
- When adding NEW images, NEVER use external URLs (Unsplash, Pexels, etc.). Use placeholder images:
  - `<img>` tags: use `src="https://placehold.co/WIDTHxHEIGHT?text=Short+Label"` with `data-image-prompt="detailed description for AI image generation"` and `data-image-name="slug_name"`
  - Background images: use a CSS background-color as fallback and add a child `<img>` with `class="absolute inset-0 w-full h-full object-cover"` using the same placeholder pattern
  - Choose appropriate dimensions: hero 1200x600, cards 600x400, avatars 400x400, etc.
  - Write rich, specific prompts in data-image-prompt (style, subject, mood, setting){design_guidelines}
{PromptTemplates._get_components_reference()}"""

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
    def get_section_refinement_prompt(
        site_name: str,
        site_description: str,
        project_briefing: str,
        default_language: str,
        full_page_html: str,
        section_name: str,
        user_request: str,
        page_title: str = '',
        page_slug: str = '',
        design_guide: str = '',
        conversation_history: str = '',
        pages: list = None,
        languages: list = None
    ) -> tuple:
        """
        Generate prompt for section-only refinement.
        Sends the full page for design context but asks the LLM to return
        ONLY the target section — drastically reducing output tokens.

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        lang_name = {'pt': 'Portuguese', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian'}.get(default_language, default_language.upper())

        design_guidelines = ""
        if design_guide:
            design_guidelines = "\n\n## Design Guide\nFollow these design patterns and conventions:\n" + design_guide

        system_prompt = f"""You are a web designer specializing in Tailwind CSS. Your goal is to edit ONE specific section of a webpage.

## Your Task
Edit ONLY the `<section data-section="{section_name}">` section based on the user's instructions. Return ONLY that single section — nothing else.

## Technical Requirements
- Use Tailwind CSS classes inline for all styling
- Make responsive: `md:text-6xl`, `lg:grid-cols-3`, `sm:flex-row`
- The `<section>` MUST keep `data-section="{section_name}"` and `id="{section_name}"` attributes
- Use `data-element-id="unique_id"` on editable text elements
- All text is in {lang_name} — keep it that way, do NOT use template variables

## Images
- **PRESERVE existing image `src` URLs exactly as they are.** Do NOT replace, remove, or change any existing `src` attribute unless the user explicitly asks to change the image itself.
- When adding NEW images, NEVER use external URLs (Unsplash, Pexels, etc.). Instead use placeholder images:
  - `<img>` tags: use `src="https://placehold.co/WIDTHxHEIGHT?text=Label"` with `data-image-prompt="description of ideal image"` and `data-image-name="slug_name"`
  - Background images: use a CSS background-color as fallback and add a child `<img>` with `class="absolute inset-0 w-full h-full object-cover"` using the same placeholder pattern above, so the image can be processed later

## CRITICAL: Return ONLY the Target Section
- Output ONLY the single `<section data-section="{section_name}">...</section>` block
- Do NOT return any other sections from the page
- Do NOT include `<html>`, `<head>`, `<body>`, `<header>`, `<nav>`, or `<footer>` tags
- Do NOT include `<script>` or `<link>` tags

## Important
- Return ONLY the updated section HTML
- Do NOT use `{{{{ trans.xxx }}}}` or any template variables
- Do NOT wrap the output in JSON
- No markdown code blocks, no explanations{design_guidelines}
{PromptTemplates._get_components_reference()}"""

        pages_info = PromptTemplates._format_pages_info(pages, languages or [])

        history_block = ""
        if conversation_history:
            history_block = f"""
# PREVIOUS REFINEMENTS

This section has been refined through a conversation:

{conversation_history}

Do NOT undo any of these previous changes unless specifically asked to.

---
"""

        user_prompt = f"""# PROJECT CONTEXT

**Site Name:** {site_name}
**Description:** {site_description}

**Project Briefing:**
{project_briefing}
{pages_info}
---

# FULL PAGE (for design context only — do NOT output the entire page)

The full page HTML is provided below so you can see the overall design, colors, spacing, and style. Use it as context to keep the section visually consistent with the rest of the page.

**Page:** {page_title if page_title else 'Untitled'}
**Slug:** {page_slug if page_slug else 'unknown'}
**Language:** {lang_name}

```html
{full_page_html if full_page_html.strip() else "<!-- EMPTY PAGE -->"}
```

---
{history_block}
# USER REQUEST

Edit the `<section data-section="{section_name}">` section:

{user_request}

---

Return ONLY the updated `<section data-section="{section_name}">...</section>` block. Nothing else. All text in {lang_name}. No template variables, no JSON, no code blocks."""

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
            library_catalog: List of dicts with id, title, alt_text, key, tags

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
- ALL visible text that a user would read: headings, paragraphs, button labels, link text, list items, spans, etc.
- Extract the EXACT text as it appears (preserve whitespace trimming)
- Do NOT extract: HTML tags, CSS classes, URLs, attribute values, SVG code, Alpine.js directives, HTML comments
- Do NOT extract code snippets, technical identifiers, or decorative/presentational text (e.g. code examples, variable names like `INSTALLED_APPS`, syntax characters like `[]` `{{}}`, programming strings like `'core'`, color hex values, etc.)
- Do NOT extract text from image attributes: `alt`, `data-image-prompt`, `data-image-name`, `title`, or any text inside `src` URLs (including placehold.co `?text=` labels)
- Only extract text that would actually need translation for a different language audience

## Variable Naming — CRITICAL
- Variable names MUST use **snake_case** with ONLY letters, digits, and underscores
- NO hyphens, NO dots, NO spaces, NO special characters in variable names
- For elements with `data-element-id`, convert the ID to snake_case: `data-element-id="stack-heading"` → variable name `stack_heading`
- Use descriptive names based on the `data-section` attribute and element role: `hero_title`, `hero_subtitle`, `features_card1_title`, `cta_button`
- Examples: `hero_title`, `stack_heading`, `cta_button_text` (NEVER `hero-title`, `stack-heading`)

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

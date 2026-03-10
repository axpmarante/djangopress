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
- Do NOT hardcode menu labels — the menu items have their own i18n labels via `get_menu_label`
- For CTA buttons, write the button text directly in the target language — keep CTAs separate from the menu loop
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
- Write all link labels and translatable text directly in the target language
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

        system_prompt = f"""You are a senior frontend designer specializing in Tailwind CSS and Django templates. Your goal is to refine a site-wide {section_type}.

## Your Task
Improve the provided {section_type} by applying the requested changes. Return a JSON object with the refined {section_type}.

## Technical Requirements
- Use Tailwind CSS classes inline
- Make responsive
- Write all text directly in the target language — do NOT use {{{{ trans.xxx }}}} template variables
- For home page link: `{{% url 'core:home' %}}`
{section_context}
**Required Output:**
- `html_template_i18n`: A JSON object with one key per language ({langs_display}), each containing the complete HTML with real text in that language
- Preserve all Django template tags ({{% url %}}, {{{{ SITE_NAME }}}}, {{{{ CONTACT_EMAIL }}}}, etc.) — only content text changes per language{design_guidelines}"""

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
- Include `{{% load i18n %}}` at the top of the HTML
- Write all link labels and text directly in the target language"""

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
  "html_template_i18n": {{
    {', '.join([f'"{lang}": "<nav class=\\"...\\">...text in {lang.upper()}...</nav>"' for lang in languages])}
  }}
}}
```

**Important:**
- Return ONLY the JSON object
- Apply ALL requested changes
- Produce complete HTML for ALL languages: {langs_display}
- Each language version must have all text written directly in that language
- Preserve all Django template tags ({{% url %}}, {{{{ SITE_NAME }}}}, {{{{ CONTACT_EMAIL }}}}, etc.) — only content text changes per language
- For home page: `{{% url 'core:home' %}}`
{nav_reminder}"""

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
        outline: list = None,
        component_references: str = '',
    ) -> tuple:
        """
        Generate prompt for Step 1: create clean HTML with real text in the default language.
        No {{ trans.xxx }} variables, no JSON wrapping — just raw HTML.

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        from djangopress.ai.utils.components import ComponentRegistry
        component_index = ComponentRegistry.get_index()

        lang_name = {'pt': 'Portuguese', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian'}.get(default_language, default_language.upper())

        system_prompt = f"""You are a senior frontend designer creating complete web pages using Tailwind CSS.

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
- Sections with `data-overlay="rgba(r,g,b,a)"` have a semi-transparent overlay applied via `background-image: linear-gradient(rgba, rgba)` in the style attribute. Preserve both the `data-overlay` attribute and the corresponding gradient. To darken: increase the alpha. To remove: delete both `data-overlay` and the gradient from style.
- Sections may contain `<iframe data-bg-video="youtube">` as a direct child for background video. Preserve these elements exactly — do not remove or modify them unless explicitly asked.
- Start with a hero section, add content sections, end with a CTA
- All URLs hardcoded: `href="/about/"`, `src="/media/image.jpg"`
- Generate 4-8 sections for a complete, professional page

## CRITICAL: Page Content Only
- Do NOT include `<html>`, `<head>`, `<body>`, `<header>`, `<nav>`, or `<footer>` tags
- Do NOT include any navigation menus, site headers, or site footers
- The header and footer are managed separately as global site components
- Your output is ONLY the page body content — a series of `<section>` blocks
- Do NOT include `<script>` or `<link>` tags for Tailwind/Alpine — they are already loaded

{component_index}
{component_references}

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
        languages: list = None,
        component_references: str = '',
    ) -> tuple:
        """
        Generate prompt for Step 1 of refinement: edit clean HTML with real text.
        The HTML has already been de-templatized (real text, no {{ trans.xxx }}).

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        from djangopress.ai.utils.components import ComponentRegistry
        component_index = ComponentRegistry.get_index()

        lang_name = {'pt': 'Portuguese', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian'}.get(default_language, default_language.upper())

        # Build design guidelines
        design_guidelines = ""
        if design_guide:
            design_guidelines = "\n\n## Design Guide\nFollow these design patterns and conventions:\n" + design_guide

        system_prompt = f"""You are a senior frontend designer specializing in Tailwind CSS. Your goal is to edit a webpage based on user instructions.

## Your Task
Edit the provided HTML page by applying the requested changes. Return the complete updated HTML.

## Technical Requirements
- Use Tailwind CSS classes inline for all styling
- Make responsive: `md:text-6xl`, `lg:grid-cols-3`, `sm:flex-row`
- Each `<section>` MUST have `data-section="name"` and `id="name"` attributes
- Sections with `data-overlay="rgba(r,g,b,a)"` have a semi-transparent overlay applied via `background-image: linear-gradient(rgba, rgba)` in the style attribute. Preserve both the `data-overlay` attribute and the corresponding gradient unless asked to change it.
- Sections may contain `<iframe data-bg-video="youtube">` as a direct child for background video. Preserve these elements exactly — do not remove or modify them unless explicitly asked.
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

{component_index}
{component_references}"""

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
        languages: list = None,
        component_references: str = '',
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
            component_references=component_references,
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
        languages: list = None,
        multi_option: bool = False,
        component_references: str = '',
        include_component_index: bool = True,
        has_reference_images: bool = False,
    ) -> tuple:
        """
        Generate prompt for section-only refinement.
        Sends the full page for design context but asks the LLM to return
        ONLY the target section — drastically reducing output tokens.

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        if include_component_index:
            from djangopress.ai.utils.components import ComponentRegistry
            component_index = ComponentRegistry.get_index()
        else:
            component_index = ''

        lang_name = {'pt': 'Portuguese', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian'}.get(default_language, default_language.upper())

        design_guidelines = ""
        if design_guide:
            design_guidelines = "\n\n## Design Guide\nFollow these design patterns and conventions:\n" + design_guide

        multi_option_block = ""
        if multi_option:
            multi_option_block = f"""

## Multiple Options
Return exactly 3 distinct variations of the section. Separate them with HTML comment markers on their own line:
<!-- OPTION_1 -->
(first variation — full <section> block)
<!-- OPTION_2 -->
(second variation — full <section> block)
<!-- OPTION_3 -->
(third variation — full <section> block)

Make each variation meaningfully different: vary layout structure, visual emphasis, spacing, or content arrangement. All 3 must satisfy the user request and include the complete <section data-section="{section_name}"> wrapper.

IMPORTANT: Keep output concise to fit all 3 options. For SVG icons, use simple paths (< 3 lines each) or Heroicons-style minimal SVGs. Never use complex multi-path SVGs — they waste tokens and prevent generating all 3 options."""

        system_prompt = f"""You are a senior frontend designer specializing in Tailwind CSS. Your goal is to edit ONE specific section of a webpage.

## Your Task
Edit ONLY the `<section data-section="{section_name}">` section based on the user's instructions. Return ONLY that single section — nothing else.

## Technical Requirements
- Use Tailwind CSS classes inline for all styling
- Make responsive: `md:text-6xl`, `lg:grid-cols-3`, `sm:flex-row`
- The `<section>` MUST keep `data-section="{section_name}"` and `id="{section_name}"` attributes
- Sections with `data-overlay="rgba(r,g,b,a)"` have a semi-transparent overlay applied via `background-image: linear-gradient(rgba, rgba)` in the style attribute. Preserve both the `data-overlay` attribute and the corresponding gradient unless asked to change it.
- Sections may contain `<iframe data-bg-video="youtube">` as a direct child for background video. Preserve these elements exactly — do not remove or modify them unless explicitly asked.
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
- No markdown code blocks, no explanations{multi_option_block}{design_guidelines}

{component_index}
{component_references}"""

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
    def get_section_generation_prompt(
        site_name: str,
        site_description: str,
        project_briefing: str,
        default_language: str,
        full_page_html: str,
        insert_after: str,
        user_request: str,
        page_title: str = '',
        page_slug: str = '',
        design_guide: str = '',
        conversation_history: str = '',
        pages: list = None,
        languages: list = None,
        component_references: str = '',
    ) -> tuple:
        """
        Generate prompt for creating a brand new section on a page.
        Sends the full page for design context and asks the LLM to return
        3 variations of a new section.

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        from djangopress.ai.utils.components import ComponentRegistry
        component_index = ComponentRegistry.get_index()

        lang_name = {'pt': 'Portuguese', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian'}.get(default_language, default_language.upper())

        if insert_after:
            position_context = f'after the `<section data-section="{insert_after}">` section'
        else:
            position_context = 'at the top of the page (before all other sections)'

        design_guidelines = ""
        if design_guide:
            design_guidelines = "\n\n## Design Guide\nFollow these design patterns and conventions:\n" + design_guide

        system_prompt = f"""You are a senior frontend designer specializing in Tailwind CSS. Your goal is to create a brand new section for a webpage.

## Your Task
Create a brand new section based on the user's description. The section will be inserted {position_context}.

## Technical Requirements
- Use Tailwind CSS classes inline for all styling
- Make responsive: `md:text-6xl`, `lg:grid-cols-3`, `sm:flex-row`
- The `<section>` MUST have `data-section="section_name"` and `id="section_name"` attributes — choose a descriptive snake_case name based on the section's purpose (e.g. `testimonials`, `pricing_plans`, `team_members`)
- Match the visual style, colors, spacing, and typography of the existing page sections
- All text must be in {lang_name} — do NOT use template variables

## Images
- NEVER use external URLs (Unsplash, Pexels, etc.). Instead use placeholder images:
  - `<img>` tags: use `src="https://placehold.co/WIDTHxHEIGHT?text=Label"` with `data-image-prompt="description of ideal image"` and `data-image-name="slug_name"`
  - Background images: use a CSS background-color as fallback and add a child `<img>` with `class="absolute inset-0 w-full h-full object-cover"` using the same placeholder pattern above, so the image can be processed later

## Multiple Options
Return exactly 3 distinct variations of the new section. Separate them with HTML comment markers on their own line:
<!-- OPTION_1 -->
(first variation — full <section> block)
<!-- OPTION_2 -->
(second variation — full <section> block)
<!-- OPTION_3 -->
(third variation — full <section> block)

Make each variation meaningfully different: vary layout structure, visual emphasis, spacing, or content arrangement. All 3 must satisfy the user request and include the complete `<section data-section="section_name">` wrapper with matching `id`.

IMPORTANT: Keep output concise to fit all 3 options. For SVG icons, use simple paths (< 3 lines each) or Heroicons-style minimal SVGs. Never use complex multi-path SVGs — they waste tokens and prevent generating all 3 options.

## CRITICAL: Return ONLY the New Section Variations
- Output ONLY the 3 `<section>` variations with their option markers
- Do NOT return any existing sections from the page
- Do NOT include `<html>`, `<head>`, `<body>`, `<header>`, `<nav>`, or `<footer>` tags
- Do NOT include `<script>` or `<link>` tags

## Important
- Return ONLY the new section HTML (3 variations)
- Do NOT use `{{{{ trans.xxx }}}}` or any template variables
- Do NOT wrap the output in JSON
- No markdown code blocks, no explanations{design_guidelines}

{component_index}
{component_references}"""

        pages_info = PromptTemplates._format_pages_info(pages, languages or [])

        history_block = ""
        if conversation_history:
            history_block = f"""
# PREVIOUS CONVERSATION

This section is being created through a conversation:

{conversation_history}

Take into account any previous feedback or direction from the user.

---
"""

        user_prompt = f"""# PROJECT CONTEXT

**Site Name:** {site_name}
**Description:** {site_description}

**Project Briefing:**
{project_briefing}
{pages_info}
---

# EXISTING PAGE — do NOT reproduce these sections

The full page HTML is provided below so you can see the overall design, colors, spacing, and style. Use it as context to keep the new section visually consistent with the rest of the page. Do NOT reproduce any of these existing sections.

**Page:** {page_title if page_title else 'Untitled'}
**Slug:** {page_slug if page_slug else 'unknown'}
**Language:** {lang_name}

```html
{full_page_html if full_page_html.strip() else "<!-- EMPTY PAGE -->"}
```

---
{history_block}
# USER REQUEST

Create a new section to be inserted {position_context}:

{user_request}

---

Return ONLY 3 variations of the new section, separated by <!-- OPTION_1 -->, <!-- OPTION_2 -->, <!-- OPTION_3 --> markers. Each must be a complete `<section>` block. All text in {lang_name}. No template variables, no JSON, no code blocks."""

        return (system_prompt, user_prompt)

    @staticmethod
    def get_element_refinement_prompt(
        site_name: str,
        site_description: str,
        project_briefing: str,
        default_language: str,
        section_html: str,
        section_name: str,
        element_html: str,
        user_request: str,
        design_guide: str = '',
        conversation_history: str = '',
        multi_option: bool = False,
        component_references: str = '',
        include_component_index: bool = True,
    ) -> tuple:
        """
        Generate prompt for element-level refinement.
        Sends the parent section for design context but asks the LLM to return
        ONLY the target element.

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        if include_component_index:
            from djangopress.ai.utils.components import ComponentRegistry
            component_index = ComponentRegistry.get_index()
        else:
            component_index = ''

        lang_name = {'pt': 'Portuguese', 'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German', 'it': 'Italian'}.get(default_language, default_language.upper())

        design_guidelines = ""
        if design_guide:
            design_guidelines = "\n\n## Design Guide\nFollow these design patterns and conventions:\n" + design_guide


        multi_option_block = ""
        if multi_option:
            multi_option_block = """

## Multiple Options
Return exactly 3 distinct variations of the element. Separate them with HTML comment markers on their own line:
<!-- OPTION_1 -->
(first variation — the element marked with data-target="true")
<!-- OPTION_2 -->
(second variation)
<!-- OPTION_3 -->
(third variation)

Make each variation meaningfully different: vary styling, layout, or visual approach. All 3 must satisfy the user request and keep the data-target="true" attribute.

IMPORTANT: Keep output concise to fit all 3 options. For SVG icons, use simple paths (< 3 lines each) or Heroicons-style minimal SVGs. Never use complex multi-path SVGs."""

        system_prompt = f"""You are a senior frontend designer specializing in Tailwind CSS. Your goal is to edit ONE specific element within a webpage section.

## Your Task
Edit ONLY the element marked with `data-target="true"` based on the user's instructions. Return ONLY that single element — nothing else.

## Technical Requirements
- Use Tailwind CSS classes inline for all styling
- Make responsive: `md:text-6xl`, `lg:grid-cols-3`, `sm:flex-row`
- The element MUST keep its `data-target="true"` attribute
- Do NOT add `data-target` to any other elements
- You may restructure the element's children freely
- You may change/add/remove classes, attributes, and child elements
- All text is in {lang_name} — keep it that way, do NOT use template variables

## Images
- **PRESERVE existing image `src` URLs exactly as they are.** Do NOT replace, remove, or change any existing `src` attribute unless the user explicitly asks to change the image itself.
- When adding NEW images, use placeholder: `src="https://placehold.co/WIDTHxHEIGHT?text=Label"` with `data-image-prompt="description"` and `data-image-name="slug_name"`

## CRITICAL: Return ONLY the Target Element
- Output ONLY the single element marked with `data-target="true"` and its children
- Do NOT return the parent section or any sibling elements
- Do NOT include `<html>`, `<head>`, `<body>`, `<section>`, `<header>`, `<nav>`, or `<footer>` tags
- Do NOT include `<script>` or `<link>` tags

## Important
- Return ONLY the updated element HTML
- Do NOT use `{{{{{{ trans.xxx }}}}}}` or any template variables
- Do NOT wrap the output in JSON
- No markdown code blocks, no explanations{multi_option_block}{design_guidelines}

{component_index}
{component_references}"""

        history_block = ""
        if conversation_history:
            history_block = f"""
# PREVIOUS REFINEMENTS

This element has been refined through a conversation:

{conversation_history}

Do NOT undo any of these previous changes unless specifically asked to.

---
"""

        user_prompt = f"""# SECTION CONTEXT (for design consistency — do NOT output the full section)

The element lives inside `<section data-section="{section_name}">`. Here is the full section so you can see the surrounding design, colors, spacing, and style:

```html
{section_html}
```

---

# ELEMENT TO EDIT

The element marked with `data-target="true"`:

```html
{element_html}
```

---
{history_block}
# USER REQUEST

Edit the element marked with `data-target="true"`:

{user_request}

---

Return ONLY the updated element. Nothing else. All text in {lang_name}. No template variables, no JSON, no code blocks."""

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
    def get_library_auto_match_prompt(
        image_context: dict,
        library_catalog: list,
        page_context: str = '',
    ) -> tuple:
        """
        Generate prompt for auto-matching a single image to the best library image.

        Args:
            image_context: Dict with name, alt, src, prompt (description of what's needed)
            library_catalog: List of dicts with id, title, alt_text, key, tags, description
            page_context: Optional surrounding HTML for context

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        system_prompt = """You are an image matching specialist. Given context about an image slot on a webpage and a catalog of available library images, pick the single best matching image.

Return ONLY a JSON object with the chosen image ID:
{"image_id": 42}

If no image in the catalog is even remotely suitable, return:
{"image_id": null}

Pick based on semantic relevance: subject matter, context, mood, and purpose. A good match doesn't need to be perfect — it needs to fit the section's intent."""

        catalog_json = json.dumps(library_catalog, indent=2, ensure_ascii=False)

        context_parts = []
        if image_context.get('name'):
            context_parts.append(f"**Image name:** {image_context['name']}")
        if image_context.get('alt'):
            context_parts.append(f"**Alt text:** {image_context['alt']}")
        if image_context.get('prompt'):
            context_parts.append(f"**Description/prompt:** {image_context['prompt']}")
        if image_context.get('src'):
            context_parts.append(f"**Current src:** {image_context['src']}")

        image_info = '\n'.join(context_parts) if context_parts else 'No metadata available'

        page_section = ''
        if page_context:
            page_section = f"""
## Page Context (surrounding HTML)

```html
{page_context[:2000]}
```
"""

        user_prompt = f"""## Image to Match

{image_info}
{page_section}
## Library Catalog

```json
{catalog_json}
```

Pick the single best matching image from the catalog. Return ONLY the JSON object with the image ID."""

        return (system_prompt, user_prompt)

    @staticmethod
    def get_translate_only_prompt(
        text_dict: dict,
        languages: list,
        default_language: str
    ) -> tuple:
        """
        Generate prompt for v2 templatization: translate pre-extracted text strings.
        Python has already extracted the text and assigned variable names —
        the LLM only needs to translate.

        Args:
            text_dict: Dict of {var_name: "original text in default language"}
            languages: List of language codes
            default_language: Language code the original text is in

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        langs_display = ' and '.join([lang.upper() for lang in languages])
        other_languages = [l for l in languages if l != default_language]
        other_langs_display = ' and '.join([l.upper() for l in other_languages])
        lang_name = {
            'pt': 'Portuguese', 'en': 'English', 'es': 'Spanish',
            'fr': 'French', 'de': 'German', 'it': 'Italian',
        }.get(default_language, default_language.upper())

        text_json = json.dumps(text_dict, indent=2, ensure_ascii=False)

        system_prompt = f"""You are a professional translator. Translate the provided text strings from {lang_name} to {other_langs_display}.

## Rules
- Translate naturally and fluently — not word-for-word
- Preserve the tone and style of the original
- Keep proper nouns, brand names, and technical terms unchanged
- The {default_language.upper()} value is always the original text — copy it exactly
- Return ONLY the JSON object, no markdown, no explanations"""

        user_prompt = f"""Translate these text strings to ALL languages: {langs_display}

The original text is in {lang_name} ({default_language.upper()}).

```json
{text_json}
```

Return a JSON object where each key is a language code, and each value is an object mapping variable names to translations:

```json
{{
  "{default_language}": {{"var_name": "original text", ...}},
  "{other_languages[0] if other_languages else 'en'}": {{"var_name": "translated text", ...}}
}}
```

Every variable must appear in every language. The {default_language.upper()} values must match the originals exactly."""

        return (system_prompt, user_prompt)

    @staticmethod
    def get_html_translation_prompt(html, source_lang, target_lang):
        """Prompt for translating HTML from one language to another.
        LLM outputs clean HTML only -- no JSON wrapping."""

        # Get full language names for better LLM understanding
        lang_names = {
            'pt': 'Portuguese', 'en': 'English', 'fr': 'French',
            'es': 'Spanish', 'de': 'German', 'it': 'Italian',
            'nl': 'Dutch', 'ru': 'Russian', 'ja': 'Japanese',
            'zh': 'Chinese', 'ko': 'Korean', 'ar': 'Arabic',
        }
        source_name = lang_names.get(source_lang, source_lang)
        target_name = lang_names.get(target_lang, target_lang)

        return f"""Translate this HTML from {source_name} to {target_name}.

RULES:
- Keep ALL HTML tags, CSS classes, attributes, and structure IDENTICAL
- Only translate visible text content
- Do NOT add, remove, or modify any HTML elements
- Do NOT change any class names, IDs, data attributes, or URLs
- Do NOT translate content inside <script> or <style> tags
- Do NOT translate placeholder text in data-image-prompt attributes
- Preserve all Tailwind CSS classes exactly
- Output ONLY the translated HTML, nothing else

HTML:
{html}"""

    @staticmethod
    def get_consistency_analysis_prompt(
        design_system: dict,
        design_guide: str,
        pages_html: list,
        sections_html: list,
        custom_rules: str = '',
        available_pages: list = None,
    ) -> tuple:
        """
        Generate prompt for analyzing design consistency across all pages.

        Args:
            design_system: Dict of design tokens (colors, fonts, spacing, buttons)
            design_guide: Freeform markdown design guide
            pages_html: List of dicts with id, title, html
            sections_html: List of dicts with key, name, html
            custom_rules: Optional user-defined rules

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        design_json = json.dumps(design_system, indent=2, ensure_ascii=False)

        if custom_rules:
            system_prompt = f"""You are a web design QA auditor. The user has provided specific rules to check. \
Focus your analysis on these rules — only report issues that match them.

## Rules to Check
{custom_rules}

Use the "custom" category for issues that match user rules, or a standard category \
(colors, typography, buttons, spacing, shadows, borders, layout, cta) if appropriate.

## Severity Levels
- **high** — Clearly violates a rule the user specified; visitors would notice
- **medium** — Partially violates a rule; reduces polish
- **low** — Minor deviation from the rules; cosmetic only

## Output Format
Return a JSON array. Each entry represents one page or section with its issues.
If a page has no issues, omit it from the array.

```json
[
  {{
    "page_id": 1,
    "page_title": "Home",
    "issues": [
      {{
        "severity": "high",
        "category": "buttons",
        "element": "section[data-section='hero'] .btn",
        "description": "Uses bg-blue-500 instead of the primary color bg-emerald-600",
        "suggestion": "Replace bg-blue-500 hover:bg-blue-600 with bg-emerald-600 hover:bg-emerald-700"
      }}
    ]
  }}
]
```

For GlobalSections (header/footer), use `"page_id": null` and add `"section_key": "main-header"`.

Return ONLY the JSON array. No markdown, no explanations."""
        else:
            system_prompt = """You are a web design QA auditor. Analyze pages for design inconsistencies against the design system.

## What to Check
1. **Colors** — hardcoded hex/rgb values instead of design system colors, inconsistent color usage across pages
2. **Typography** — inconsistent font families, heading sizes that don't follow the scale, mismatched text sizes for similar elements
3. **Buttons** — different button styles (padding, border-radius, colors, hover states) across pages
4. **Spacing** — inconsistent padding/margin patterns between similar sections
5. **Shadows & Borders** — mismatched shadow or border-radius values across cards, sections
6. **Layout** — inconsistent container widths, grid patterns, or section structures
7. **CTAs** — different call-to-action patterns, inconsistent link styling

## Severity Levels
- **high** — Visually jarring inconsistency that visitors would notice (e.g. completely different button styles on adjacent pages)
- **medium** — Noticeable inconsistency that reduces polish (e.g. hardcoded color instead of design token)
- **low** — Minor inconsistency, cosmetic only (e.g. slightly different spacing)

## Output Format
Return a JSON array. Each entry represents one page or section with its issues.
If a page has no issues, omit it from the array.

```json
[
  {
    "page_id": 1,
    "page_title": "Home",
    "issues": [
      {
        "severity": "high",
        "category": "buttons",
        "element": "section[data-section='hero'] .btn",
        "description": "Uses bg-blue-500 instead of the primary color bg-emerald-600",
        "suggestion": "Replace bg-blue-500 hover:bg-blue-600 with bg-emerald-600 hover:bg-emerald-700"
      }
    ]
  }
]
```

For GlobalSections (header/footer), use `"page_id": null` and add `"section_key": "main-header"`.

Return ONLY the JSON array. No markdown, no explanations."""

        pages_block = ""
        for p in pages_html:
            pages_block += f"\n### Page: {p['title']} (ID: {p['id']})\n```html\n{p['html']}\n```\n"

        sections_block = ""
        for s in sections_html:
            sections_block += f"\n### GlobalSection: {s['name']} (key: {s['key']})\n```html\n{s['html']}\n```\n"

        design_guide_block = ""
        if design_guide:
            design_guide_block = f"\n## Design Guide\n{design_guide}\n"

        pages_registry_block = ""
        if available_pages:
            lines = [f"- /{p['slug']} — {p['title']}" for p in available_pages]
            pages_registry_block = "\n## Available Pages (valid link targets)\n" + "\n".join(lines) + "\n"

        user_prompt = f"""## Design System

```json
{design_json}
```
{design_guide_block}{pages_registry_block}
## Pages to Analyze
{pages_block}{sections_block}
Analyze all pages and sections for {'the rules provided' if custom_rules else 'design inconsistencies against the design system'}. Return the JSON array."""

        return (system_prompt, user_prompt)

    @staticmethod
    def get_consistency_fix_prompt(
        design_system: dict,
        design_guide: str,
        page_html: str,
        issues: list,
        custom_rules: str = '',
    ) -> tuple:
        """
        Generate prompt for fixing design inconsistencies on a single page.

        Args:
            design_system: Dict of design tokens
            design_guide: Freeform markdown design guide
            page_html: The page's HTML to fix
            issues: List of issue dicts to fix
            custom_rules: Optional user-defined rules

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        design_json = json.dumps(design_system, indent=2, ensure_ascii=False)
        issues_json = json.dumps(issues, indent=2, ensure_ascii=False)

        system_prompt = """You are a web design consistency fixer. Fix the specific design inconsistencies listed below.

## Rules
- ONLY change Tailwind CSS classes and inline styles to fix the listed issues
- Do NOT change text content, wording, or copy
- Do NOT change HTML structure (adding/removing elements, reordering)
- Do NOT change data-section, id, or data-* attributes
- Do NOT change Alpine.js directives (x-data, x-show, @click, etc.)
- Do NOT change Django template tags ({% url %}, {% csrf_token %}, etc.)
- Do NOT change image src URLs or alt text
- Do NOT change href URLs
- Preserve ALL existing functionality
- Return the complete fixed HTML

Return ONLY the fixed HTML. No markdown code blocks, no explanations."""

        design_guide_block = ""
        if design_guide:
            design_guide_block = f"\n## Design Guide\n{design_guide}\n"

        custom_rules_block = ""
        if custom_rules:
            custom_rules_block = f"\n## Custom Rules\n{custom_rules}\n"

        user_prompt = f"""## Design System Reference

```json
{design_json}
```
{design_guide_block}{custom_rules_block}
## Issues to Fix

```json
{issues_json}
```

## HTML to Fix

```html
{page_html}
```

Fix ONLY the listed issues. Return the complete fixed HTML."""

        return (system_prompt, user_prompt)

    @staticmethod
    def get_consistency_section_fix_prompt(
        design_system: dict,
        design_guide: str,
        section_html: str,
        section_name: str,
        issues: list,
        custom_rules: str = '',
    ) -> tuple:
        """
        Generate prompt for fixing design inconsistencies on a single section.
        Same as get_consistency_fix_prompt but scoped to one section.
        """
        design_json = json.dumps(design_system, indent=2, ensure_ascii=False)
        issues_json = json.dumps(issues, indent=2, ensure_ascii=False)

        system_prompt = f"""You are a web design consistency fixer. Fix the specific design inconsistencies in the "{section_name}" section.

## Rules
- ONLY change Tailwind CSS classes and inline styles to fix the listed issues
- Do NOT change text content, wording, or copy
- Do NOT change HTML structure (adding/removing elements, reordering)
- Do NOT change data-section, id, or data-* attributes
- Do NOT change Alpine.js directives (x-data, x-show, @click, etc.)
- Do NOT change Django template tags ({{% url %}}, {{% csrf_token %}}, etc.)
- Do NOT change image src URLs or alt text
- Do NOT change href URLs
- Preserve ALL existing functionality
- Return the complete fixed section HTML (the entire <section> tag)

Return ONLY the fixed section HTML. No markdown code blocks, no explanations."""

        design_guide_block = ""
        if design_guide:
            design_guide_block = f"\n## Design Guide\n{design_guide}\n"

        custom_rules_block = ""
        if custom_rules:
            custom_rules_block = f"\n## Custom Rules\n{custom_rules}\n"

        user_prompt = f"""## Design System Reference

```json
{design_json}
```
{design_guide_block}{custom_rules_block}
## Issues to Fix in "{section_name}" Section

```json
{issues_json}
```

## Section HTML to Fix

```html
{section_html}
```

Fix ONLY the listed issues in this section. Return the complete fixed section HTML."""

        return (system_prompt, user_prompt)

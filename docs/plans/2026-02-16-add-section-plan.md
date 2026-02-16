# Add Section Feature — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let users insert new AI-generated sections at any position in a page via insertion lines, context menu, and the AI chat panel with 3-option preview.

**Architecture:** New `section-inserter.js` module renders `+` insertion lines between sections. Clicking inserts a DOM placeholder and switches the AI panel to `new-section` scope. The existing `refine-multi` endpoint gains `mode=create` to generate 3 section variations from scratch. `apply-option` gains `mode=insert` to splice the chosen section into the page HTML at the right position.

**Tech Stack:** Django, BeautifulSoup, Gemini (LLM), ES modules, Tailwind CSS

---

### Task 1: CSS — Insertion Lines & Placeholder Styles

**Files:**
- Modify: `editor_v2/static/editor_v2/css/editor.css` (append at end)

**Step 1: Add insertion line and placeholder styles**

Append to `editor.css`:

```css
/* ── Section insertion lines ── */
.ev2-insert-line {
  position: relative;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s;
  z-index: 10;
}

.ev2-insert-line:hover {
  opacity: 1;
}

.ev2-insert-line::before {
  content: '';
  position: absolute;
  left: 5%;
  right: 5%;
  top: 50%;
  height: 2px;
  background: var(--ev2-accent);
  opacity: 0.5;
  border-radius: 1px;
}

.ev2-insert-line-btn {
  position: relative;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--ev2-accent);
  color: #fff;
  border: none;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
  transition: transform 0.15s, box-shadow 0.15s;
}

.ev2-insert-line-btn:hover {
  transform: scale(1.15);
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}

/* ── Section placeholder ── */
.ev2-section-placeholder {
  border: 2px dashed var(--ev2-accent);
  border-radius: var(--ev2-radius);
  padding: 40px 20px;
  text-align: center;
  color: var(--ev2-text-muted);
  font-family: var(--ev2-font);
  font-size: 14px;
  background: rgba(99, 102, 241, 0.04);
  margin: 8px 0;
  min-height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color 0.2s;
}

.ev2-section-placeholder.ev2-preview-active {
  border: none;
  padding: 0;
  background: none;
  min-height: auto;
  display: block;
}
```

**Step 2: Commit**

```bash
git add editor_v2/static/editor_v2/css/editor.css
git commit -m "Add CSS for section insertion lines and placeholder"
```

---

### Task 2: New Module — `section-inserter.js`

**Files:**
- Create: `editor_v2/static/editor_v2/js/modules/section-inserter.js`
- Modify: `editor_v2/static/editor_v2/js/editor.js` (add import + init)

**Step 1: Create the section-inserter module**

Create `editor_v2/static/editor_v2/js/modules/section-inserter.js`:

```javascript
/**
 * Section Inserter — renders "+" insertion lines between sections.
 * Clicking creates a placeholder and triggers new-section mode in the AI panel.
 */
import { events } from '../lib/events.js';
import { getContentWrapper, getSections } from '../lib/dom.js';

let lines = [];       // DOM references to insertion line elements
let placeholder = null; // the active placeholder element
let insertAfter = null; // section name the placeholder is after (null = top)

export function getInsertState() {
    return placeholder ? { afterSection: insertAfter } : null;
}

export function init() {
    renderLines();
    events.on('inserter:refresh', renderLines);
    events.on('inserter:cancel', removePlaceholder);
}

export function destroy() {
    removeLines();
    removePlaceholder();
}

export function renderLines() {
    removeLines();
    if (placeholder) return; // don't show lines while a placeholder is active

    const wrapper = getContentWrapper();
    if (!wrapper) return;

    const sections = getSections();
    if (sections.length === 0) {
        // Empty page — single insertion line
        const line = createLine(null);
        wrapper.prepend(line);
        lines.push(line);
        return;
    }

    // Line before the first section
    const firstLine = createLine(null);
    sections[0].parentNode.insertBefore(firstLine, sections[0]);
    lines.push(firstLine);

    // Line after each section
    for (const sec of sections) {
        const name = sec.getAttribute('data-section');
        const line = createLine(name);
        sec.parentNode.insertBefore(line, sec.nextSibling);
        lines.push(line);
    }
}

function removeLines() {
    for (const l of lines) l.remove();
    lines = [];
}

function createLine(afterSectionName) {
    const line = document.createElement('div');
    line.className = 'ev2-insert-line';
    line.innerHTML = '<button class="ev2-insert-line-btn" title="Insert new section">+</button>';
    line.querySelector('button').addEventListener('click', (e) => {
        e.stopPropagation();
        insertPlaceholder(afterSectionName);
    });
    return line;
}

function insertPlaceholder(afterSectionName) {
    removePlaceholder();
    removeLines();

    const wrapper = getContentWrapper();
    if (!wrapper) return;

    insertAfter = afterSectionName;

    placeholder = document.createElement('div');
    placeholder.className = 'ev2-section-placeholder';
    placeholder.textContent = 'New section — describe it in the AI panel →';

    if (!afterSectionName) {
        // Insert at top
        const sections = getSections();
        if (sections.length > 0) {
            sections[0].parentNode.insertBefore(placeholder, sections[0]);
        } else {
            wrapper.appendChild(placeholder);
        }
    } else {
        const anchor = wrapper.querySelector(`[data-section="${afterSectionName}"]`);
        if (anchor) {
            anchor.parentNode.insertBefore(placeholder, anchor.nextSibling);
        } else {
            wrapper.appendChild(placeholder);
        }
    }

    placeholder.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Notify AI panel to switch to new-section mode
    events.emit('inserter:activated', { afterSection: afterSectionName });
}

/** Called from context menu: insert before/after a named section */
export function insertBefore(sectionName) {
    const wrapper = getContentWrapper();
    if (!wrapper) return;
    const sec = wrapper.querySelector(`[data-section="${sectionName}"]`);
    if (!sec) return;

    // Find the section before this one (or null if first)
    const sections = getSections();
    const idx = sections.indexOf(sec);
    const prevName = idx > 0 ? sections[idx - 1].getAttribute('data-section') : null;
    insertPlaceholder(prevName);
}

export function insertAfterSection(sectionName) {
    insertPlaceholder(sectionName);
}

/** Replace placeholder with generated HTML for preview */
export function previewInPlaceholder(html) {
    if (!placeholder) return;
    placeholder.classList.add('ev2-preview-active');
    placeholder.innerHTML = html;
}

/** Restore placeholder to its empty state */
export function resetPlaceholder() {
    if (!placeholder) return;
    placeholder.classList.remove('ev2-preview-active');
    placeholder.textContent = 'New section — describe it in the AI panel →';
}

export function removePlaceholder() {
    if (placeholder) {
        placeholder.remove();
        placeholder = null;
    }
    insertAfter = null;
}
```

**Step 2: Register in editor.js**

In `editor_v2/static/editor_v2/js/editor.js`, add the import and init call:

```javascript
import * as sectionInserter from './modules/section-inserter.js';
```

Add after `versions.init();`:
```javascript
    sectionInserter.init();
```

**Step 3: Commit**

```bash
git add editor_v2/static/editor_v2/js/modules/section-inserter.js editor_v2/static/editor_v2/js/editor.js
git commit -m "Add section-inserter module with insertion lines and placeholder"
```

---

### Task 3: Context Menu — Insert Before/After Items

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/context-menu.js`

**Step 1: Add import and menu items**

At the top of `context-menu.js`, add the import:

```javascript
import { insertBefore, insertAfterSection } from './section-inserter.js';
```

In `buildItems(el)`, after the `AI Refine Section` item (line ~36, just before the separator `items.push(null)`), add:

```javascript
    items.push({ label: 'Insert Section Before', icon: '+', action: () => insertBefore(name) });
    items.push({ label: 'Insert Section After', icon: '+', action: () => insertAfterSection(name) });
```

These should go inside the `if (section) { ... }` block, right after the `AI Refine Section` push and before the `items.push(null)` separator.

**Step 2: Commit**

```bash
git add editor_v2/static/editor_v2/js/modules/context-menu.js
git commit -m "Add Insert Section Before/After to context menu"
```

---

### Task 4: AI Panel — New Section Scope

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/ai-panel.js`

**Step 1: Add import and state**

At the top, add import:

```javascript
import { getInsertState, previewInPlaceholder, resetPlaceholder, removePlaceholder, renderLines } from './section-inserter.js';
```

**Step 2: Listen for inserter activation**

In `init()`, add a new event subscription:

```javascript
    unsubs.push(events.on('inserter:activated', (data) => {
        activeScope = 'new-section';
        currentSection = data.afterSection;
        events.emit('sidebar:switch-tab', 'ai');
    }));
```

**Step 3: Reset inserter state in destroy()**

In `destroy()`, add after `options = []; activeOption = 0;`:

```javascript
    removePlaceholder();
```

**Step 4: Update buildScopeSelect()**

In `buildScopeSelect()`, add a `new-section` option. After the element option block, add:

```javascript
    if (activeScope === 'new-section') {
        options += '<option value="new-section" selected>New Section</option>';
    }
```

**Step 5: Handle scope change away from new-section**

In `bindScopeSelect()`, inside the change handler, after `activeScope = e.target.value;`, add:

```javascript
        if (e.target.value !== 'new-section') {
            removePlaceholder();
            renderLines();
        }
```

**Step 6: Update send() for new-section scope**

In `send()`, after the existing `if (activeScope === 'page')` / `else if (activeScope === 'element')` / `else` chain (around line 276-302), add a new branch. Restructure to:

```javascript
        if (activeScope === 'new-section') {
            const insertState = getInsertState();
            res = await api.post('/refine-multi/', {
                page_id: config().pageId,
                mode: 'create',
                insert_after: insertState?.afterSection || null,
                instructions: text,
                conversation_history: history,
                session_id: sessionId,
            });
        } else if (activeScope === 'page') {
```

(Keep the rest of the existing chain as-is.)

Also at the top of `send()`, update the scope validation to allow `new-section`:

```javascript
    if (activeScope === 'section' && !currentSection) return;
    if (activeScope === 'element' && (!currentElementId || !currentSection)) return;
```

No change needed — `new-section` won't match either guard.

Update the `scopeLabel` assignment:

```javascript
    if (activeScope === 'section') scopeLabel = currentSection;
    if (activeScope === 'element') scopeLabel = currentElementId;
    if (activeScope === 'new-section') scopeLabel = 'new section';
```

**Step 7: Update showMultiPreview for new-section**

In `showMultiPreview(index)`, add a branch for `new-section` at the top of the conditionals:

```javascript
    if (pendingScope === 'new-section') {
        previewInPlaceholder(html);
        return;
    }
```

**Step 8: Update restorePreview for new-section**

In `restorePreview()`, add a branch:

```javascript
    if (pendingScope === 'new-section') {
        resetPlaceholder();
        originalHtml = null;
        return;
    }
```

**Step 9: Update applyResult for new-section**

In `applyResult()`, inside the `if (options.length > 0 && pendingScope)` block, update the api call to pass `mode` and `insert_after` when scope is `new-section`:

```javascript
            const isInsert = pendingScope === 'new-section';
            const insertState = getInsertState();
            await api.post('/apply-option/', {
                page_id: config().pageId,
                scope: pendingScope,
                section_name: isInsert ? null : currentSection,
                element_id: isInsert ? null : currentElementId,
                html: chosen.html,
                ...(isInsert && { mode: 'insert', insert_after: insertState?.afterSection || null }),
            });
```

**Step 10: Update discardResult for new-section**

In `discardResult()`, after `activeOption = 0;`, add:

```javascript
    if (activeScope === 'new-section') {
        removePlaceholder();
        activeScope = 'page';
        renderLines();
    }
```

**Step 11: Clean up inserter on session/scope changes**

In `bindSessionBar()` — both the select change handler and the "New Chat" click handler — add after `options = [];`:

```javascript
        if (activeScope === 'new-section') {
            removePlaceholder();
            activeScope = 'page';
        }
```

**Step 12: Commit**

```bash
git add editor_v2/static/editor_v2/js/modules/ai-panel.js
git commit -m "Add new-section scope to AI panel with placeholder preview"
```

---

### Task 5: Prompt — Section Generation Template

**Files:**
- Modify: `ai/utils/prompts.py`

**Step 1: Add `get_section_generation_prompt` method**

Add a new static method to `PromptTemplates` (after `get_section_refinement_prompt`). This is similar to the refinement prompt but instructs the LLM to create a brand new section rather than editing an existing one:

```python
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
    ) -> tuple:
        """
        Generate prompt for creating a brand new section to insert into a page.
        Returns 3 distinct variations.
        """
        lang_name = {
            'pt': 'Portuguese', 'en': 'English', 'es': 'Spanish',
            'fr': 'French', 'de': 'German', 'it': 'Italian'
        }.get(default_language, default_language.upper())

        design_guidelines = ""
        if design_guide:
            design_guidelines = "\n\n## Design Guide\nFollow these design patterns and conventions:\n" + design_guide

        position_context = "at the top of the page (before all other sections)" if not insert_after else f"after the `<section data-section=\"{insert_after}\">` section"

        system_prompt = f"""You are a senior frontend designer specializing in Tailwind CSS. Your goal is to create a brand new section for a webpage.

## Your Task
Create a NEW section based on the user's description. The section will be inserted {position_context}.

## Technical Requirements
- Use Tailwind CSS classes inline for all styling
- Make responsive: `md:text-6xl`, `lg:grid-cols-3`, `sm:flex-row`
- The `<section>` MUST have `data-section="section_name"` and `id="section_name"` attributes — choose a descriptive snake_case name
- Use `data-element-id="unique_id"` on editable text elements (headings, paragraphs, buttons, links)
- All text is in {lang_name}
- Match the visual style (colors, spacing, fonts, shadows) of the existing page sections

## Images
- NEVER use external URLs (Unsplash, Pexels, etc.)
- Use placeholder images: `src="https://placehold.co/WIDTHxHEIGHT?text=Label"` with `data-image-prompt="description"` and `data-image-name="slug_name"`

## Multiple Options
Return exactly 3 distinct variations of the section. Separate them with HTML comment markers on their own line:
<!-- OPTION_1 -->
(first variation — full <section> block)
<!-- OPTION_2 -->
(second variation — full <section> block)
<!-- OPTION_3 -->
(third variation — full <section> block)

Make each variation meaningfully different: vary layout structure, visual emphasis, spacing, or content arrangement. All 3 must include the complete `<section>` wrapper.

## CRITICAL
- Output ONLY the 3 section variations with the OPTION markers
- Do NOT return any existing sections from the page
- Do NOT include `<html>`, `<head>`, `<body>`, `<header>`, `<nav>`, or `<footer>` tags
- Do NOT use `{{{{ trans.xxx }}}}` or any template variables
- No JSON, no markdown code blocks, no explanations{design_guidelines}
{PromptTemplates._get_components_reference()}"""

        pages_info = PromptTemplates._format_pages_info(pages, languages or [])

        history_block = ""
        if conversation_history:
            history_block = f"""
# PREVIOUS MESSAGES

{conversation_history}

---
"""

        user_prompt = f"""# PROJECT CONTEXT

**Site Name:** {site_name}
**Description:** {site_description}

**Project Briefing:**
{project_briefing}
{pages_info}
---

# EXISTING PAGE (for style context — do NOT reproduce these sections)

The section will be inserted into this page. Match its visual style.

**Page:** {page_title if page_title else 'Untitled'}
**Slug:** {page_slug if page_slug else 'unknown'}
**Language:** {lang_name}
**Insert position:** {position_context}

```html
{full_page_html if full_page_html.strip() else "<!-- EMPTY PAGE -->"}
```

---
{history_block}
# USER REQUEST

Create a new section:

{user_request}

---

Return exactly 3 variations of the new section separated by <!-- OPTION_N --> markers. All text in {lang_name}. No template variables, no JSON, no code blocks."""

        return (system_prompt, user_prompt)
```

**Step 2: Commit**

```bash
git add ai/utils/prompts.py
git commit -m "Add section generation prompt template for new section creation"
```

---

### Task 6: Backend — `generate_section` Service Method

**Files:**
- Modify: `ai/services.py`

**Step 1: Add `generate_section` method to `ContentGenerationService`**

Add after `refine_section_only` (after ~line 1153):

```python
    def generate_section(
        self,
        page_id: int,
        insert_after: str,
        instructions: str,
        conversation_history: list = None,
        model_override: str = None
    ) -> Dict:
        """
        Generate a brand new section to insert into a page.
        Returns 3 option variations as raw HTML (no templatize).
        """
        from core.models import Page, SiteSettings
        from bs4 import BeautifulSoup

        print(f"\n=== Generating New Section ===")
        print(f"Page ID: {page_id}, Insert After: {insert_after}")
        print(f"Instructions: {instructions}")

        try:
            page = Page.objects.get(id=page_id)
        except Page.DoesNotExist:
            raise ValueError(f"Page with ID {page_id} not found")

        site_settings = SiteSettings.objects.first()
        default_language = site_settings.get_default_language() if site_settings else 'pt'
        site_name = site_settings.get_site_name(default_language) if site_settings else 'Website'
        site_description = site_settings.get_site_description(default_language) if site_settings else ''
        project_briefing = site_settings.get_project_briefing() if site_settings else ''
        languages = site_settings.get_language_codes() if site_settings else ['pt', 'en']
        design_guide = site_settings.design_guide if site_settings else ''
        model = model_override or self.model_name

        page_title = page.default_title
        page_slug = page.default_slug

        pages_data = []
        for p in Page.objects.filter(is_active=True).order_by('id'):
            pages_data.append({'title': p.title_i18n or {}, 'slug': p.slug_i18n or {}})

        # De-templatize full page HTML for context
        current_html = page.html_content or ''
        current_translations = (page.content or {}).get('translations', {})
        if current_translations.get(default_language):
            clean_html = self._detemplatize_html(current_html, current_translations, default_language)
        else:
            clean_html = current_html

        history_text = ''
        if conversation_history:
            for msg in conversation_history:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                if role == 'user':
                    history_text += f"\nUser: {content}"
                elif role == 'assistant':
                    history_text += f"\nAssistant: {content}"

        system_prompt, user_prompt = PromptTemplates.get_section_generation_prompt(
            site_name=site_name,
            site_description=site_description,
            project_briefing=project_briefing,
            default_language=default_language,
            full_page_html=clean_html,
            insert_after=insert_after,
            user_request=instructions,
            page_title=page_title,
            page_slug=page_slug,
            design_guide=design_guide,
            conversation_history=history_text,
            pages=pages_data,
            languages=languages,
        )

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        actual_model, provider_str = self._get_model_info(model)
        t0 = time.time()
        try:
            response = self.llm.get_completion(messages, tool_name=model)
            usage = self._extract_usage(response)
            log_ai_call(
                action='generate_section', model_name=actual_model, provider=provider_str,
                system_prompt=system_prompt, user_prompt=user_prompt,
                response_text=response.choices[0].message.content,
                duration_ms=int((time.time() - t0) * 1000),
                page=page, section_name=f'new_after_{insert_after or "top"}', **usage,
            )
        except Exception as e:
            log_ai_call(
                action='generate_section', model_name=actual_model, provider=provider_str,
                system_prompt=system_prompt, user_prompt=user_prompt,
                duration_ms=int((time.time() - t0) * 1000),
                page=page, section_name=f'new_after_{insert_after or "top"}',
                success=False, error_message=str(e),
            )
            raise

        generated_html = self._extract_html_from_response(response.choices[0].message.content)

        if not generated_html or len(generated_html.strip()) < 50:
            raise ValueError("Section generation returned empty or too-short HTML")

        print(f"Generated {len(generated_html)} chars of new section HTML")

        # Split into options
        options = self._split_multi_options(generated_html)
        validated = []
        for i, opt_html in enumerate(options):
            opt_soup = BeautifulSoup(opt_html, 'html.parser')
            opt_section = opt_soup.find('section')
            if opt_section:
                validated.append({'html': str(opt_section)})
            else:
                validated.append({'html': opt_html})
            print(f"  Option {i+1}: {len(validated[-1]['html'])} chars")

        assistant_message = f"Here are {len(validated)} design options for the new section."
        return {
            'options': validated,
            'assistant_message': assistant_message,
        }
```

**Step 2: Commit**

```bash
git add ai/services.py
git commit -m "Add generate_section service method for new section creation"
```

---

### Task 7: Backend — Extend `refine_multi` and `apply_option` Views

**Files:**
- Modify: `editor_v2/api_views.py`

**Step 1: Extend `refine_multi` for mode=create**

In `refine_multi` (around line 1056, after parsing `session_id`), add:

```python
        mode = data.get('mode', 'refine')
        insert_after = data.get('insert_after')
```

Then add a branch before the existing `if scope == 'element':` block:

```python
        if mode == 'create':
            # Generate a brand new section
            result = service.generate_section(
                page_id=page_id,
                insert_after=insert_after,
                instructions=instructions,
                conversation_history=conversation_history,
            )
        elif scope == 'element':
```

(Keep the existing `elif scope == 'element':` and `else:` branches.)

Update the session creation to handle `mode == 'create'`:

```python
        if not session:
            if mode == 'create':
                prefix = '[new section]'
            elif scope == 'element':
                prefix = f'[{element_id}]'
            else:
                prefix = f'[{section_name}]'
```

Also update the validation: when `mode == 'create'`, `section_name` is not required. Wrap the existing validation in a mode check:

```python
        if mode != 'create':
            if scope == 'element' and (not element_id or not section_name):
                return JsonResponse({'success': False, 'error': 'Missing element_id or section_name for element scope'}, status=400)

            if scope == 'section' and not section_name:
                return JsonResponse({'success': False, 'error': 'Missing section_name for section scope'}, status=400)
```

Update the session target for create mode:

```python
        if mode == 'create':
            target = f'new_after_{insert_after or "top"}'
        else:
            target = f'{section_name}/{element_id}' if scope == 'element' else section_name
```

**Step 2: Extend `apply_option` for mode=insert**

In `apply_option` (around line 1146, after parsing `html`), add:

```python
        mode = data.get('mode', 'replace')
        insert_after = data.get('insert_after')
```

Add a new branch for insert mode. Before the existing `if scope == 'element' and element_id:` block, add:

```python
        if mode == 'insert':
            # Insert new section into page
            soup = BeautifulSoup(page.html_content or '', 'html.parser')
            new_soup = BeautifulSoup(html_template, 'html.parser')
            new_section = new_soup.find('section')
            if not new_section:
                return JsonResponse({'success': False, 'error': 'No section found in generated HTML'}, status=400)

            if insert_after:
                anchor = soup.find('section', attrs={'data-section': insert_after})
                if anchor:
                    anchor.insert_after(new_section)
                else:
                    # Fallback: append at end
                    soup.append(new_section)
            else:
                # Insert at top
                first_section = soup.find('section')
                if first_section:
                    first_section.insert_before(new_section)
                else:
                    soup.append(new_section)

            new_html = str(soup)
            if new_html.startswith('<html><body>'):
                new_html = new_html[12:-14]
            page.html_content = new_html
            change_target = new_section.get('data-section', 'new section')

        elif scope == 'element' and element_id:
```

(Keep the existing `elif scope == 'element'` and `else` branches.)

Update the version creation to use the correct `change_target` — move it after the branching so it uses the right variable. Currently `change_target` is set before the branches as `element_id or section_name`. Restructure:

```python
        # Create version for rollback
        page.create_version(
            user=request.user,
            change_summary=f'AI {"new section" if mode == "insert" else "multi-option"} applied: {change_target}'
        )
```

This should go BEFORE the if/elif/else branches but AFTER `change_target` is defined. Since the insert branch defines its own `change_target`, move the version creation to right before `page.save()` instead, and have each branch set `change_target`.

**Step 3: Commit**

```bash
git add editor_v2/api_views.py
git commit -m "Extend refine_multi and apply_option for new section insertion"
```

---

### Task 8: Re-render Insertion Lines After Apply

**Files:**
- Modify: `editor_v2/static/editor_v2/js/modules/ai-panel.js`

**Step 1: Ensure insertion lines re-render after apply/discard**

In `applyResult()`, the page reloads (`window.location.reload()`), so insertion lines will re-render automatically via `sectionInserter.init()` in `editor.js`. No change needed.

In `discardResult()`, we already call `removePlaceholder()` and `renderLines()` (added in Task 4 Step 10). Verify this is correct.

**Step 2: Manual testing checklist**

1. Open any page with `?edit=v2`
2. Hover between sections — see `+` insertion lines
3. Click `+` — placeholder appears, AI panel focuses
4. Scope dropdown shows "New Section"
5. Type a description, hit Send
6. See A/B/C tabs with previews in the placeholder area
7. Switch between tabs — preview updates
8. Click Apply — "Saving..." → "Saved!" → page reloads with new section
9. Click Discard — placeholder removed, insertion lines return
10. Right-click a section → "Insert Section Before" / "Insert Section After" works
11. Switching scope away from "New Section" removes placeholder

**Step 3: Final commit**

```bash
git add -A
git commit -m "Add Section feature: insertion lines, AI generation, multi-option preview"
```
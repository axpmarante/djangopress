# Site assistant — Phase 4: layout, slider, photo, form and contact tools

**Date:** 2026-10-01
**Status:** Draft for review
**Repo:** djangopress (engine). Branch `feature/assistant-tools` (from `test/tudo`).
**Goal:** the Home / site assistant can do the everyday site jobs deterministically and safely, without regenerating whole pages:
- insert a section where asked;
- read and restyle precisely;
- reorder or replace slider and gallery images;
- find better photos and use them as section backgrounds;
- test forms;
- check that contact details are right.

---

## Context

The phase 1–2 eval (`docs/evals/2026-10-01-results-phase-1-2.md`) passed 20/20, but showed four gaps:
- **Inserting a section:** to add a section "before the contacts" the assistant regenerated the whole page, which re-translated every other section (4 sections in N8, 11 in C8).
- **Restyling:** the assistant only sees 80-character previews of sections. `update_element_styles` replaces the whole class list without the model having seen it.
- **Sliders and galleries:** they can only be changed through an AI regeneration. The editor's component panel (`editor_v2/components.py`) does this deterministically, but the assistant can't use it.
- **Images:** the assistant can list media-library images by title. It can't find a better photo, search Unsplash (the engine has `ai/utils/unsplash.py`; a key is configured on the demo), or set a section background.
- **Forms:** `validate_forms` crashes when a form's `fields_schema` holds plain strings ("string indices must be integers"). Nothing tests that a form actually submits and that its email leaves.
- **Contacts:** nothing checks the phone, email, WhatsApp and address across pages, header/footer and settings.

Decisions already taken (2026-10-01):
- **Test emails** go to the operator (`PWD_SUPERADMIN_EMAIL`) with "TESTE" in the subject, never to the client. The test submission is deleted afterwards.
- **Facts are not invented.** Phase 4 tools report what they found; contact checks against the web use `web_search` and cite sources.

---

## 1. Insert a section where asked — `insert_section`

```
insert_section(position: "before" | "after" | "start" | "end", anchor_section?: str, instructions: str)
```
- **Generation:** `ContentGenerationService.generate_section(page, insert_after, instructions, lang)`, taking the first option. For "before X", `insert_after` is the section above X, or the top of the page.
- **Saving:** `ai_apply.apply_section_html(mode='insert', insert_after=…)`. **Only the new section** is translated; the rest of the page doesn't change in any language, and the name is unique.
- **Prompt:** "To add a section use insert_section; never refine_page to add one."

## 2. Read and restyle precisely

- **`read_section(section_name)`:** the section's HTML in the editing language, capped at 12 k characters, with a note when it is cut. The model can see real classes and selectors before restyling.
- **`update_element_styles` gains `add_classes` / `remove_classes`.** The old `classes` (replace all) still works but is described as "only when you have read the element".
- Both apply to every language, as today.

## 3. Sliders and galleries from the chat

- **New service, `editor_v2/component_ops.py`:** the operation runner that `component_views.component_op` uses today moves here as `run_component_op(page, root_selector, kind, op, args, lang, user)`. The endpoint and the tools both call it, so checkpoints, all-language behaviour and translation of new text are the same as in the editor panel.
- **Tools:**
  - `list_components(page)` lists the sliders and galleries on the active page: kind, section, item count, and a short label per item (alt or first line of text).
  - `reorder_items(section, order)`.
  - `replace_item_image(section, index, image)`.
  - `add_item_images(section, after, images)`.
  - `remove_item(section, index)`.
  - Components are addressed by section plus kind. Item indices are 1-based in the tool, which is friendlier for the model, and converted inside.
- **Example:** "Põe a foto do foie gras em primeiro no slider" becomes `list_components` → `reorder_items`. No AI regeneration.

## 4. Find better photos and use them as backgrounds

- **`find_photos(query, source: "library" | "unsplash" | "both" = "both", orientation?)`:**
  - **Library:** `SiteImage` ranked by keyword overlap across title, alt, tags and the AI `description` field.
  - **Unsplash:** `unsplash.search_photos`, when configured.
  - **Result:** up to 8 candidates `{ref, source, title, thumb_url, credit}`.
  - **In the Home:** candidates show as clickable thumbnails. Clicking one sends "Use photo `<ref>`" as the next message.
- **`set_section_background(section_name, ref)`:**
  - An Unsplash `ref` is first downloaded into the media library (`unsplash.download_photo`, credit kept in the image title/description).
  - The background is then set on the section in **every** language, keeping an existing overlay gradient (same rule as the editor's background picker). It also works on sections that use an `<img>` background layer: it replaces that image, and the lightbox `href` too.
- **Editor:** the image picker gains an **Unsplash** tab (search, pick → download into the library → apply), next to Library and Upload.

## 5. Forms — fix validation, test for real

- **`validate_forms`:** fix the crash; schema entries can be strings or dicts. Add a test with both shapes.
- **Shared submission path:** the body of `core/views.form_submit` (validate → save → notify → confirm) moves to `core/services/forms.py` as `process_submission(form_def, data, lang, ip, user_agent, *, notify_to=None, subject_prefix='')`. The view calls it with the defaults, so visitor behaviour doesn't change.
- **`test_form(slug)`:**
  - builds valid test data from the form's schema (required fields filled with plausible values, the email field set to the operator's address);
  - calls `process_submission(..., notify_to=PWD_SUPERADMIN_EMAIL, subject_prefix='[TESTE] ')`, so it bypasses rate limit and honeypot but runs validation, saving and the real email send;
  - deletes the test submission;
  - reports each step: valid, saved, email sent (with Mailgun's status), confirmation email (if the form sends one, also to the operator).
  - **With no form slug:** tests every form found on the site's pages.
- **Prompt:** forms are tested only when asked, or after creating or editing a form.

## 6. Contacts — `validate_contacts`

**Collects** from SiteSettings (`contact_email`, `contact_phone`, `whatsapp_number`, `contact_address_i18n`, `google_maps_embed_url`) and from every active page and global section, in every language:
- `tel:`, `mailto:` and `wa.me` links;
- visible phone numbers and emails (regex).

**Checks:**
- **Format:** phone numbers parse as international, or Portuguese 9-digit; emails are valid syntax.
- **Email domain:** the domain resolves and has MX records (DNS lookup; skipped offline).
- **Link vs text:** each `tel:`/`mailto:` href matches the text shown next to it.
- **Consistency:** the same phone, email and WhatsApp everywhere, and the same as SiteSettings. Every place that differs is listed.
- **Maps:** the embed URL is a Google Maps embed.

**Optional `check_web: true`:** a `web_search` for the business name and city. The phone and address it finds are compared with the site's, and differences are reported **with sources**. The site is never changed.

**Output:** issues grouped as "wrong / inconsistent / can't verify", each with page, section and language.

---

## Prompt changes (executor)

- To add a section, use `insert_section`.
- To change a slider or gallery, use the component tools.
- For photos, use `find_photos`, then `set_section_background` or `replace_item_image`.
- For "is the form working" / "are the contacts right", use `test_form` / `validate_contacts`.
- Report the results in the closing summary (what was checked, what is wrong).

## Testing

- **Unit tests per tool:**
  - insert position and only-the-new-section translated (mocked generator and translation);
  - read_section cap;
  - add/remove classes in all languages;
  - each component op through the shared runner;
  - find_photos ranking and Unsplash results (mocked);
  - set_section_background with and without an overlay, and with an `<img>` layer;
  - validate_forms with string and dict schemas;
  - process_submission unchanged for visitors;
  - test_form sends to the operator with "[TESTE]" and deletes its submission (email backend locmem);
  - validate_contacts: mismatched `tel:`, a different phone on one page, an invalid email, an MX lookup that is mocked;
  - Home thumbnail rendering helper.
- **New eval cases on `demo-ai-eval`:**
  - N11 "põe a foto X em primeiro no slider";
  - N12 "procura uma foto melhor para o fundo da secção Y";
  - N13 "testa o formulário de contacto";
  - N14 "verifica se os contactos estão certos";
  - N8 and C8 re-run, expecting no re-translation of other sections.

## Out of scope

- Phase 3 (design context pack).
- Phase 5 (visual verification).
- AI-generated photos (the mockup skills already cover it).
- Fixing contacts automatically (the assistant proposes; the operator confirms).

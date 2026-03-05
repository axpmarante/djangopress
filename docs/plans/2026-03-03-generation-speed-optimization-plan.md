# Site Generation Speed Optimization — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Cut site generation from ~19 min to ~8-9 min by parallelizing pipeline stages, moving design guide before pages, and using faster models for non-HTML tasks.

**Architecture:** The `SiteGenerator.run()` pipeline currently runs stages sequentially: settings → pages → design guide → menu → header → footer. We restructure to: settings → design guide (from briefing, flash) → home page → [remaining pages + header + footer] in parallel → menu. Component selection switches to gemini-lite.

**Tech Stack:** Python concurrent.futures.ThreadPoolExecutor, Django ORM, Gemini API via Vertex AI

**Design doc:** `docs/plans/2026-03-03-generation-speed-optimization-design.md`

---

### Task 1: Switch component selection to gemini-lite

**Files:**
- Modify: `ai/utils/components/__init__.py:149-160`

**Step 1: Change the model from gemini-flash to gemini-lite**

In `select_components()`, change the model lookup and LLM call (around line 149-160):

```python
# Before (line 149-151):
from ai.utils.llm_config import MODEL_CONFIG
config = MODEL_CONFIG.get('gemini-flash')
model_name = config.model_name if config else 'gemini-flash'

# After:
from ai.utils.llm_config import MODEL_CONFIG
config = MODEL_CONFIG.get('gemini-lite')
model_name = config.model_name if config else 'gemini-lite'
```

And the LLM call (line 160):
```python
# Before:
response = llm.get_completion(messages, tool_name='gemini-flash')

# After:
response = llm.get_completion(messages, tool_name='gemini-lite')
```

Also update the `log_ai_call` calls at lines 176-187, 198-210, and 245-254 to use `'google'` provider (stays the same since gemini-lite is also google).

**Step 2: Verify the change**

Run: `DJANGO_SETTINGS_MODULE=config.settings python -c "import django; django.setup(); from ai.utils.components import ComponentRegistry; from ai.utils.llm_config import LLMBase; result = ComponentRegistry.select_components('Create a homepage with a hero section', '', LLMBase()); print('Result:', result); print('OK')"`

Expected: Returns `[]` (no interactive components needed for a simple hero page). Should complete in ~1-2s instead of ~9s.

**Step 3: Commit**

```bash
git add ai/utils/components/__init__.py
git commit -m "perf: switch component selection from gemini-flash to gemini-lite"
```

---

### Task 2: Rewrite design guide generation to use briefing + settings (no page HTML)

**Files:**
- Modify: `ai/site_generator.py:765-840` — rewrite `generate_design_guide()`

**Step 1: Rewrite `generate_design_guide()` to accept plan parameter**

Replace the current `generate_design_guide()` method (lines 765-840) with a new version that generates from the briefing and design system settings instead of analyzing page HTML:

```python
def generate_design_guide(self, plan: Dict = None):
    """Generate a design guide from the project briefing and design system settings."""
    from core.models import SiteSettings
    from ai.utils.llm_config import LLMBase

    self.log("\n--- Generating Design Guide ---")

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
        response = llm.get_completion(messages, tool_name='gemini-flash')
        guide = response.choices[0].message.content

        # Strip markdown code fences
        import re
        guide = re.sub(r'^```(?:markdown)?\n?', '', guide)
        guide = re.sub(r'\n?```$', '', guide)

        settings.design_guide = guide
        settings.save()
        self.log(f"  Design guide generated ({len(guide)} chars) using gemini-flash")

    except Exception as e:
        self.log(f"  Design guide generation failed: {e}")
        self.errors.append({'page': 'design_guide', 'error': str(e)})
```

Key changes:
- Accepts optional `plan` parameter for page context
- Uses briefing + settings instead of page HTML
- Uses `gemini-flash` instead of `self.model` (pro) — it's writing documentation, not HTML
- No dependency on `self.generated_pages` — can run before any page generation

**Step 2: Verify the method compiles**

Run: `DJANGO_SETTINGS_MODULE=config.settings python -c "import django; django.setup(); from ai.site_generator import SiteGenerator; print('Import OK')"`

Expected: No errors.

**Step 3: Commit**

```bash
git add ai/site_generator.py
git commit -m "perf: generate design guide from briefing+settings instead of page HTML

Uses gemini-flash and runs before page generation so all pages
benefit from consistent styling guidance."
```

---

### Task 3: Use gemini-flash for header and footer generation

**Files:**
- Modify: `ai/site_generator.py:877-918` — `generate_header()`
- Modify: `ai/site_generator.py:920-955` — `generate_footer()`

**Step 1: Pass model_override='gemini-flash' in generate_header()**

In `generate_header()` (line 906-909), add `model_override='gemini-flash'`:

```python
# Before (lines 906-909):
service = ContentGenerationService(model_name=self.model)
result = service.refine_global_section(
    section_key='main-header',
    refinement_instructions=instructions,
)

# After:
service = ContentGenerationService(model_name=self.model)
result = service.refine_global_section(
    section_key='main-header',
    refinement_instructions=instructions,
    model_override='gemini-flash',
)
```

**Step 2: Pass model_override='gemini-flash' in generate_footer()**

In `generate_footer()` (line 947-950), add `model_override='gemini-flash'`:

```python
# Before (lines 947-950):
service = ContentGenerationService(model_name=self.model)
result = service.refine_global_section(
    section_key='main-footer',
    refinement_instructions=instructions,
)

# After:
service = ContentGenerationService(model_name=self.model)
result = service.refine_global_section(
    section_key='main-footer',
    refinement_instructions=instructions,
    model_override='gemini-flash',
)
```

**Step 3: Verify method compiles**

Run: `DJANGO_SETTINGS_MODULE=config.settings python -c "import django; django.setup(); from ai.site_generator import SiteGenerator; print('Import OK')"`

**Step 4: Commit**

```bash
git add ai/site_generator.py
git commit -m "perf: use gemini-flash for header/footer generation

Headers and footers are structurally simple (nav bars, link columns).
Flash is 2-3x faster than pro for these structures."
```

---

### Task 4: Restructure run() pipeline — design guide before pages, parallel header/footer

**Files:**
- Modify: `ai/site_generator.py:230-256` — `run()` method
- Modify: `ai/site_generator.py:616-728` — `generate_pages()` method

**Step 1: Restructure run() to move design guide before pages and parallelize header/footer**

Replace the `run()` method (lines 230-256):

```python
def run(self):
    """Execute the full pipeline."""
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

    if not self.skip_images:
        self.process_all_images()

    self.ensure_contact_form()
    return self.print_summary()
```

**Step 2: Restructure generate_pages() to include header/footer in the parallel pool**

Replace the parallel section of `generate_pages()` (lines 711-728). After the home page is generated, submit remaining pages + header + footer to the same pool:

```python
    # Generate home page first (needs to exist before others for inter-page linking)
    home_page = _generate_single_page(0, pages[0])
    if home_page:
        self.generated_pages.append(home_page)

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
```

Note: Remove the separate `self.generate_header(plan)` and `self.generate_footer(plan)` calls from `run()` since they're now inside `generate_pages()`.

**Step 3: Verify import and basic structure**

Run: `DJANGO_SETTINGS_MODULE=config.settings python -c "import django; django.setup(); from ai.site_generator import SiteGenerator; print('Import OK')"`

**Step 4: Commit**

```bash
git add ai/site_generator.py
git commit -m "perf: parallelize header/footer with page generation, design guide before pages

Pipeline restructured:
1. Design guide generated from briefing BEFORE pages (all pages benefit)
2. Home page first (sequential)
3. Remaining pages + header + footer run in parallel (max 6 workers)

Expected speedup: ~19min → ~8-9min for 4-page sites."
```

---

### Task 5: Update benchmark script for new pipeline order

**Files:**
- Modify: `scripts/benchmark_generate.py:276-316` — `timed_run()`

**Step 1: Update timed_run() to match the new pipeline order**

The benchmark script's `timed_run()` overrides the normal `run()` to capture per-step timings. It needs to match the new flow where:
- Design guide runs before pages
- Header/footer run inside generate_pages (parallel), not as separate steps

Update `timed_run()` (lines 276-316):

```python
def timed_run(self):
    self.log(f"\n{'='*60}")
    self.log(f"Generating: {self.briefing['business_name']}")
    self.log(f"{'='*60}\n")

    set_step('plan')
    with timed('plan', timings):
        plan = self.plan()

    set_step('configure_settings')
    with timed('configure_settings', timings):
        self.configure_settings(plan)

    # Design guide now runs BEFORE pages
    if not self.skip_design_guide:
        set_step('generate_design_guide')
        with timed('generate_design_guide', timings):
            self.generate_design_guide(plan)

    # Pages + header + footer are now all inside generate_pages
    with timed('generate_pages', timings):
        timed_generate_pages(self, plan)

    set_step('create_menu_items')
    with timed('create_menu_items', timings):
        self.create_menu_items()

    # Header and footer are now generated inside generate_pages
    # Track them as 0 in the step timings for backwards compat
    timings['generate_header'] = 0.0
    timings['generate_footer'] = 0.0

    if not self.skip_images:
        set_step('process_images')
        with timed('process_images', timings):
            self.process_all_images()

    set_step('ensure_contact_form')
    with timed('ensure_contact_form', timings):
        self.ensure_contact_form()
```

**Step 2: Verify the script runs**

Run: `source .venv/bin/activate && python scripts/benchmark_generate.py --help`

Expected: Help text with no errors.

**Step 3: Commit**

```bash
git add scripts/benchmark_generate.py
git commit -m "perf: update benchmark script for new parallel pipeline order"
```

---

### Task 6: Run benchmark and compare results

**Step 1: Run the optimized benchmark**

```bash
source .venv/bin/activate && python scripts/benchmark_generate.py --delay 0
```

Expected: Completes in ~8-10 min (down from ~19 min). JSON report saved to `benchmarks/`.

**Step 2: Compare with baseline**

```bash
python scripts/benchmark_compare.py benchmarks/bench_20260303_144602_gemini_pro.json benchmarks/<new-report-filename>.json
```

Expected output should show:
- Total time: ~50% reduction
- Per-page times: similar (same model)
- Header/footer times: 2-3x faster (flash vs pro)
- Design guide: faster (flash) and now shows in configure phase
- No failures or fallbacks

**Step 3: Verify quality by starting the server**

```bash
python manage.py runserver 8000
```

Visit `/backoffice/benchmarks/` to see both reports in the dashboard. Click the new report to verify:
- Design guide was generated
- All 4 pages created
- Header and footer exist
- No errors

**Step 4: Final commit with benchmark results**

```bash
git add benchmarks/
git commit -m "bench: add optimized pipeline benchmark results"
```

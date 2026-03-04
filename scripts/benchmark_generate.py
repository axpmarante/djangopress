#!/usr/bin/env python
"""
Benchmark site generation speed from a briefing.

Usage:
    python scripts/benchmark_generate.py                          # default briefing, skip images
    python scripts/benchmark_generate.py briefings/my-site.md     # custom briefing
    python scripts/benchmark_generate.py --with-images            # include image processing
    python scripts/benchmark_generate.py --model gemini-flash     # different model

Measures wall-clock time for each pipeline step, captures every LLM API call,
and saves a JSON report to benchmarks/ for future comparison.
"""

import argparse
import datetime
import json
import os
import sys
import tempfile
import time
import threading

# Setup Django before any imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Use a temporary database so we don't touch real data
DB_PATH = os.path.join(tempfile.gettempdir(), f'djangopress_bench_{os.getpid()}.sqlite3')
os.environ['DATABASE_URL'] = f'sqlite:///{DB_PATH}'

# Project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

import django
django.setup()


# ---------------------------------------------------------------------------
# LLM call tracker — monkey-patches LLMBase.get_completion to capture timings
# ---------------------------------------------------------------------------
_llm_calls = []
_llm_lock = threading.Lock()
_step_context = threading.local()


def set_step(step_name):
    """Set the current pipeline step label for LLM call tracking."""
    _step_context.step = step_name


def get_step():
    """Get the current pipeline step label."""
    return getattr(_step_context, 'step', 'unknown')


def _install_llm_tracker():
    """Wrap LLMBase.get_completion to record every LLM API call."""
    from ai.utils.llm_config import LLMBase

    original_get_completion = LLMBase.get_completion

    def tracked_get_completion(self, messages, tool_name=None, **kwargs):
        t0 = time.time()
        result = original_get_completion(self, messages, tool_name=tool_name, **kwargs)
        elapsed = time.time() - t0

        response_text = result.choices[0].message.content if result.choices else ''
        usage = result.usage
        entry = {
            'step': get_step(),
            'tool_name': tool_name or 'default',
            'model': tool_name or 'default',
            'provider': 'google',
            'elapsed_s': round(elapsed, 2),
            'prompt_tokens': getattr(usage, 'prompt_tokens', None),
            'completion_tokens': getattr(usage, 'completion_tokens', None),
            'response_len': len(response_text) if response_text else 0,
            'success': bool(response_text),
            'fallback_used': False,
        }
        with _llm_lock:
            _llm_calls.append(entry)
        return result

    LLMBase.get_completion = tracked_get_completion
    return original_get_completion


def _install_image_gen_tracker():
    """Wrap LLMBase.generate_image to record image generation calls."""
    from ai.utils.llm_config import LLMBase

    if not hasattr(LLMBase, 'generate_image'):
        return None

    original = LLMBase.generate_image

    def tracked_generate_image(self, prompt, **kwargs):
        t0 = time.time()
        result = original(self, prompt, **kwargs)
        elapsed = time.time() - t0

        entry = {
            'step': get_step(),
            'tool_name': 'image_generation',
            'model': 'imagen',
            'provider': 'google',
            'elapsed_s': round(elapsed, 2),
            'prompt_tokens': None,
            'completion_tokens': None,
            'response_len': len(result.image_bytes) if hasattr(result, 'image_bytes') and result.image_bytes else 0,
            'success': getattr(result, 'success', False),
            'fallback_used': False,
            'prompt_text': prompt[:100],
        }
        with _llm_lock:
            _llm_calls.append(entry)
        return result

    LLMBase.generate_image = tracked_generate_image
    return original


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt_duration(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}m {secs:.1f}s"


def timed(label, timings_dict):
    """Context manager to time a block and store in timings_dict."""
    class Timer:
        def __enter__(self):
            self.t0 = time.time()
            return self
        def __exit__(self, *args):
            timings_dict[label] = round(time.time() - self.t0, 2)
    return Timer()


# ---------------------------------------------------------------------------
# Main benchmark
# ---------------------------------------------------------------------------

def run_benchmark(briefing_path, skip_images=True, skip_design_guide=False,
                  model='gemini-pro', delay=1):
    from django.core.management import call_command
    from ai.site_generator import SiteGenerator

    # Install trackers
    orig_completion = _install_llm_tracker()
    orig_image_gen = _install_image_gen_tracker()

    # Run migrations silently
    print("Setting up temporary database...")
    call_command('migrate', verbosity=0)

    from django.contrib.auth import get_user_model
    User = get_user_model()
    if not User.objects.filter(is_superuser=True).exists():
        User.objects.create_superuser('bench', 'bench@test.com', 'bench')

    print(f"\n{'='*70}")
    print(f"  DJANGOPRESS SITE GENERATION BENCHMARK")
    print(f"{'='*70}")
    print(f"  Briefing:       {briefing_path}")
    print(f"  Model:          {model}")
    print(f"  Skip images:    {skip_images}")
    print(f"  Skip design:    {skip_design_guide}")
    print(f"  Delay:          {delay}s")
    print(f"  Date:           {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    # Patch SiteGenerator.run to time each step
    timings = {}
    page_timings = {}

    original_run = SiteGenerator.run
    original_generate_pages = SiteGenerator.generate_pages

    def timed_generate_pages(self, plan):
        """Wrap generate_pages to capture per-page timings."""
        from ai.services import ContentGenerationService
        from core.models import Page, SiteSettings

        service = ContentGenerationService(model_name=self.model)
        settings = SiteSettings.objects.first()
        default_lang = settings.get_default_language()
        language_codes = settings.get_language_codes()

        pages = plan.get('pages', [])
        # Move home to front
        home_idx = None
        for i, p in enumerate(pages):
            if p['name'].lower() in ('home', 'homepage', 'inicio'):
                home_idx = i
                break
        if home_idx is not None and home_idx != 0:
            pages.insert(0, pages.pop(home_idx))

        for i, page_spec in enumerate(pages):
            page_name = page_spec['name']
            self.log(f"\n  [{i+1}/{len(pages)}] Generating: {page_name}")

            llm_calls_before = len(_llm_calls)
            t0 = time.time()
            set_step(f'page:{page_name}')

            brief = self._build_page_brief(page_spec, plan)
            page_html_chars = 0
            page_error = None
            try:
                result = service.generate_page(brief=brief, language=default_lang)
                page_html_chars = len(result.get('html_content', ''))

                if page_name.lower() in ('home', 'homepage', 'home page', 'inicio'):
                    slug_i18n = {lang: 'home' for lang in language_codes}
                else:
                    slug_i18n = result.get('slug_i18n', {lang: page_name.lower().replace(' ', '-') for lang in language_codes})

                from django.utils.text import slugify
                page = Page.objects.create(
                    title_i18n=result.get('title_i18n', {lang: page_name for lang in language_codes}),
                    slug_i18n={lang: slugify(s) or slugify(page_name) for lang, s in slug_i18n.items()},
                    html_content_i18n=result.get('html_content_i18n', {}),
                    is_active=True,
                    sort_order=i * 10,
                )
                self.generated_pages.append(page)
                self.log(f"    Saved: {page.default_title}")

            except Exception as e:
                page_error = str(e)
                self.log(f"    ERROR: {e}")
                self.errors.append({'page': page_name, 'error': str(e)})

            elapsed = round(time.time() - t0, 2)
            llm_calls_for_page = _llm_calls[llm_calls_before:]

            # Build sub-step breakdown from call order
            # Pattern: component_selection(flash), html_generation(pro), metadata(lite), templatization(flash)
            sub_step_labels = ['component_selection', 'html_generation', 'metadata', 'templatization']
            sub_steps = {}
            for j, call in enumerate(llm_calls_for_page):
                label = sub_step_labels[j] if j < len(sub_step_labels) else f'extra_{j}'
                tokens = (call.get('prompt_tokens') or 0) + (call.get('completion_tokens') or 0)
                sub_steps[label] = {
                    'elapsed_s': call['elapsed_s'],
                    'model': call['tool_name'],
                    'tokens': tokens,
                }
                # Also tag the call itself with the sub-step
                call['step'] = f"page:{page_name}:{label}"

            page_timings[page_name] = {
                'elapsed_s': elapsed,
                'llm_calls': len(llm_calls_for_page),
                'llm_time_s': round(sum(c['elapsed_s'] for c in llm_calls_for_page), 2),
                'html_chars': page_html_chars,
                'error': page_error,
                'sub_steps': sub_steps,
            }

            if i < len(pages) - 1 and self.delay > 0:
                time.sleep(self.delay)

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

        if not self.skip_design_guide and len(plan.get('pages', [])) > 0:
            set_step('generate_design_guide')
            with timed('generate_design_guide', timings):
                self.generate_design_guide(plan)

        with timed('generate_pages', timings):
            timed_generate_pages(self, plan)

        set_step('create_menu_items')
        with timed('create_menu_items', timings):
            self.create_menu_items()

        # Header and footer now use gemini-flash and run after pages in the
        # benchmark (sequentially) so we can capture their individual timings.
        # In the real pipeline they run in parallel inside generate_pages().
        set_step('generate_header')
        with timed('generate_header', timings):
            self.generate_header(plan)

        set_step('generate_footer')
        with timed('generate_footer', timings):
            self.generate_footer(plan)

        if not self.skip_images:
            set_step('process_images')
            with timed('process_images', timings):
                self.process_all_images()

        set_step('ensure_contact_form')
        with timed('ensure_contact_form', timings):
            self.ensure_contact_form()

        return self.print_summary()

    SiteGenerator.run = timed_run

    # Run
    total_start = time.time()
    try:
        generator = SiteGenerator(
            briefing_path=briefing_path,
            stdout=sys.stdout,
            dry_run=False,
            skip_images=skip_images,
            skip_design_guide=skip_design_guide,
            model=model,
            delay=delay,
        )
        result = generator.run()
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        result = None
    finally:
        SiteGenerator.run = original_run
        # Restore originals
        from ai.utils.llm_config import LLMBase
        LLMBase.get_completion = orig_completion
        if orig_image_gen:
            LLMBase.generate_image = orig_image_gen

    total_time = round(time.time() - total_start, 2)

    # ---------------------------------------------------------------------------
    # Build report
    # ---------------------------------------------------------------------------
    report = {
        'meta': {
            'date': datetime.datetime.now().isoformat(),
            'briefing': briefing_path,
            'model': model,
            'skip_images': skip_images,
            'skip_design_guide': skip_design_guide,
            'delay': delay,
            'total_time_s': total_time,
        },
        'steps': timings,
        'pages': page_timings,
        'llm_calls': _llm_calls,
        'summary': {},
    }

    # Compute summary stats
    pages_created = len(page_timings)
    total_llm_calls = len(_llm_calls)
    total_llm_time = round(sum(c['elapsed_s'] for c in _llm_calls), 2)
    fallback_count = sum(1 for c in _llm_calls if c.get('fallback_used'))
    failed_count = sum(1 for c in _llm_calls if not c.get('success'))
    image_gen_calls = [c for c in _llm_calls if c['tool_name'] == 'image_generation']
    text_llm_calls = [c for c in _llm_calls if c['tool_name'] != 'image_generation']

    report['summary'] = {
        'pages_created': pages_created,
        'total_llm_calls': total_llm_calls,
        'total_llm_time_s': total_llm_time,
        'overhead_time_s': round(total_time - total_llm_time, 2),
        'fallback_count': fallback_count,
        'failed_count': failed_count,
        'avg_page_time_s': round(sum(p['elapsed_s'] for p in page_timings.values()) / pages_created, 2) if pages_created else 0,
        'avg_llm_call_s': round(total_llm_time / total_llm_calls, 2) if total_llm_calls else 0,
        'text_llm_calls': len(text_llm_calls),
        'text_llm_avg_s': round(sum(c['elapsed_s'] for c in text_llm_calls) / len(text_llm_calls), 2) if text_llm_calls else 0,
        'image_gen_calls': len(image_gen_calls),
        'image_gen_avg_s': round(sum(c['elapsed_s'] for c in image_gen_calls) / len(image_gen_calls), 2) if image_gen_calls else 0,
    }

    # ---------------------------------------------------------------------------
    # Print results
    # ---------------------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  BENCHMARK RESULTS")
    print(f"{'='*70}")

    # Step timings
    print(f"\n  Pipeline Steps:")
    print(f"  {'Step':<30} {'Time':>10} {'%':>8}")
    print(f"  {'-'*48}")
    for step, duration in timings.items():
        pct = (duration / total_time * 100) if total_time > 0 else 0
        print(f"  {step.replace('_', ' ').title():<30} {fmt_duration(duration):>10} {pct:>7.1f}%")
    print(f"  {'-'*48}")
    print(f"  {'TOTAL':<30} {fmt_duration(total_time):>10} {'100.0%':>8}")

    # Per-page timings
    if page_timings:
        print(f"\n  Page Generation Breakdown:")
        print(f"  {'Page':<25} {'Time':>10} {'LLM Calls':>12} {'LLM Time':>10}")
        print(f"  {'-'*57}")
        for name, pt in page_timings.items():
            print(f"  {name:<25} {fmt_duration(pt['elapsed_s']):>10} {pt['llm_calls']:>12} {fmt_duration(pt['llm_time_s']):>10}")
        avg = report['summary']['avg_page_time_s']
        print(f"  {'-'*57}")
        print(f"  {'Average':<25} {fmt_duration(avg):>10}")

    # LLM call summary
    print(f"\n  LLM API Calls:")
    print(f"  {'Metric':<35} {'Value':>15}")
    print(f"  {'-'*50}")
    print(f"  {'Total calls':<35} {total_llm_calls:>15}")
    print(f"  {'Total LLM time':<35} {fmt_duration(total_llm_time):>15}")
    print(f"  {'Average per call':<35} {fmt_duration(report['summary']['avg_llm_call_s']):>15}")
    print(f"  {'Text generation calls':<35} {len(text_llm_calls):>15}")
    print(f"  {'Text gen avg':<35} {fmt_duration(report['summary']['text_llm_avg_s']):>15}")
    if image_gen_calls:
        print(f"  {'Image generation calls':<35} {len(image_gen_calls):>15}")
        print(f"  {'Image gen avg':<35} {fmt_duration(report['summary']['image_gen_avg_s']):>15}")
    if fallback_count:
        print(f"  {'Fallback to alt provider':<35} {fallback_count:>15}")
    if failed_count:
        print(f"  {'Failed calls':<35} {failed_count:>15}")

    # Overhead
    overhead = report['summary']['overhead_time_s']
    print(f"\n  {'Pipeline overhead (non-LLM)':<35} {fmt_duration(overhead):>15}")
    print(f"  {'LLM % of total':<35} {(total_llm_time/total_time*100) if total_time else 0:>14.1f}%")

    print(f"\n{'='*70}")

    # ---------------------------------------------------------------------------
    # Save report
    # ---------------------------------------------------------------------------
    benchmarks_dir = os.path.join(PROJECT_ROOT, 'benchmarks')
    os.makedirs(benchmarks_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    report_filename = f"bench_{timestamp}_{model.replace('-', '_')}.json"
    report_path = os.path.join(benchmarks_dir, report_filename)

    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\n  Report saved: {report_path}")
    print()

    # Cleanup
    cleanup_db()
    return report


def cleanup_db():
    try:
        if os.path.exists(DB_PATH):
            os.unlink(DB_PATH)
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser(
        description='Benchmark DjangoPress site generation speed',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/benchmark_generate.py                              # quick test (no images)
  python scripts/benchmark_generate.py --with-images                # full pipeline
  python scripts/benchmark_generate.py --model gemini-flash         # test a different model
  python scripts/benchmark_generate.py briefings/my-site.md         # custom briefing
        """
    )
    parser.add_argument('briefing', nargs='?', default='briefings/benchmark.md',
                        help='Path to the briefing markdown file (default: briefings/benchmark.md)')
    parser.add_argument('--with-images', action='store_true',
                        help='Include image processing (default: skip)')
    parser.add_argument('--skip-design-guide', action='store_true',
                        help='Skip design guide generation')
    parser.add_argument('--model', default='gemini-pro',
                        help='LLM model (default: gemini-pro)')
    parser.add_argument('--delay', type=int, default=1,
                        help='Delay between LLM calls in seconds (default: 1)')

    args = parser.parse_args()

    if not os.path.exists(args.briefing):
        print(f"Error: briefing file not found: {args.briefing}")
        sys.exit(1)

    try:
        run_benchmark(
            briefing_path=args.briefing,
            skip_images=not args.with_images,
            skip_design_guide=args.skip_design_guide,
            model=args.model,
            delay=args.delay,
        )
    except KeyboardInterrupt:
        print("\nBenchmark interrupted.")
        cleanup_db()
        sys.exit(1)


if __name__ == '__main__':
    main()

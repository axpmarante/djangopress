"""No AI task defaults to Gemini Pro: page generation, generate_site, the Blueprint planners, the
prompt enhancer and the benchmark all run on Flash unless a site picks another model in its settings."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from djangopress.ai.utils.llm_config import AI_MODEL_DEFAULTS, get_ai_model
from djangopress.core.models import SiteSettings


class DefaultsTest(TestCase):
    def test_no_task_defaults_to_pro(self):
        self.assertEqual([t for t, m in AI_MODEL_DEFAULTS.items() if m == 'gemini-pro'], [])

    def test_generation_and_page_refinement_run_on_flash(self):
        self.assertEqual(get_ai_model('generation'), 'gemini-flash')
        self.assertEqual(get_ai_model('refinement_page'), 'gemini-flash')

    def test_a_site_can_still_pick_another_model(self):
        s = SiteSettings.load()
        s.ai_model_config = {'generation': 'gemini-pro'}
        s.save()
        from django.core.cache import cache
        self.addCleanup(cache.clear)   # SiteSettings.load() is cached across the rollback
        self.assertEqual(get_ai_model('generation'), 'gemini-pro')


class CallersTest(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_superuser('a', 'a@x.com', 'pw'))

    def test_generate_site_runs_on_flash(self):
        import tempfile
        from djangopress.ai.site_generator import SiteGenerator
        with tempfile.NamedTemporaryFile('w', suffix='.md') as briefing, \
                mock.patch('djangopress.ai.site_generator.BriefingParser.parse', return_value={'sections': {}}):
            briefing.write('# Briefing')
            briefing.flush()
            generator = SiteGenerator(briefing.name)
        self.assertEqual(generator.model, 'gemini-flash')

    def test_the_benchmark_defaults_to_flash(self):
        with mock.patch('djangopress.backoffice.api_views.subprocess.Popen') as popen, \
                mock.patch('djangopress.backoffice.api_views.os.path.isfile', return_value=True):
            popen.return_value.pid = 1
            self.client.post('/backoffice/api/run-benchmark/', '{}', content_type='application/json')
        if popen.called:
            cmd = popen.call_args.args[0]
            self.assertEqual(cmd[cmd.index('--model') + 1], 'gemini-flash')
        else:
            self.fail('the benchmark did not start')

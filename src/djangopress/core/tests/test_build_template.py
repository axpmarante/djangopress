"""The packaged briefing template (src/djangopress/briefings/TEMPLATE.md) must match the
new content-only shape, and stay in sync with the repo-root copy that ships it."""

from pathlib import Path

from django.test import SimpleTestCase

import djangopress

PACKAGED = Path(djangopress.__file__).parent / 'briefings' / 'TEMPLATE.md'
REPO_ROOT_COPY = Path(djangopress.__file__).resolve().parents[2] / 'briefings' / 'TEMPLATE.md'


class BuildTemplateTest(SimpleTestCase):

    def test_packaged_template_is_in_the_new_shape(self):
        text = PACKAGED.read_text()
        self.assertIn('## Content', text)
        self.assertIn('## Design Constraints', text)
        self.assertNotIn('## Design Preferences', text)

    def test_packaged_matches_repo_root_copy(self):
        if not REPO_ROOT_COPY.exists():
            self.skipTest('repo-root briefings/TEMPLATE.md not present (packaged install)')
        self.assertEqual(PACKAGED.read_text(), REPO_ROOT_COPY.read_text())

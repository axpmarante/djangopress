"""BACKOFFICE_EXTRA_NAV: the sidebar hook site-local apps use to add menu items.

A flat item renders as one link. An item with 'children' renders as a
collapsible group like the engine's own News menu, each child a link to its
own view.
"""
from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from djangopress.core.context_processors import backoffice_nav

User = get_user_model()

# Engine URL names stand in for a site app's views: they reverse everywhere.
GROUP = [{
    'label': 'Shop',
    'url_prefix': '/backoffice/news/',
    'children': [
        {'label': 'Posts', 'url_name': 'backoffice:news_list', 'url_prefix': '/backoffice/news/'},
        {'label': 'Categories', 'url_name': 'backoffice:news_categories',
         'url_prefix': '/backoffice/news/categories/'},
    ],
}]


class ExtraNavGroupActiveStateTests(SimpleTestCase):
    def nav(self, path):
        item, = backoffice_nav(RequestFactory().get(path))['backoffice_extra_nav']
        return item

    @override_settings(BACKOFFICE_EXTRA_NAV=GROUP)
    def test_the_longest_matching_child_prefix_is_the_only_active_child(self):
        item = self.nav('/backoffice/news/categories/3/')
        self.assertTrue(item['is_active'])
        self.assertEqual([c['is_active'] for c in item['children']], [False, True])

    @override_settings(BACKOFFICE_EXTRA_NAV=GROUP)
    def test_a_child_whose_prefix_is_the_group_root_owns_the_root(self):
        item = self.nav('/backoffice/news/')
        self.assertEqual([c['is_active'] for c in item['children']], [True, False])

    @override_settings(BACKOFFICE_EXTRA_NAV=GROUP)
    def test_nothing_is_active_outside_the_group(self):
        item = self.nav('/backoffice/forms/')
        self.assertFalse(item['is_active'])
        self.assertEqual([c['is_active'] for c in item['children']], [False, False])

    @override_settings(BACKOFFICE_EXTRA_NAV=[{
        'label': 'Shop',
        'children': [{'label': 'Posts', 'url_name': 'backoffice:news_list',
                      'url_prefix': '/backoffice/news/'}],
    }])
    def test_a_group_without_its_own_prefix_is_active_through_its_children(self):
        self.assertTrue(self.nav('/backoffice/news/')['is_active'])

    @override_settings(BACKOFFICE_EXTRA_NAV=GROUP)
    def test_the_settings_are_not_mutated(self):
        from django.conf import settings
        self.nav('/backoffice/news/')
        self.assertNotIn('is_active', settings.BACKOFFICE_EXTRA_NAV[0])
        self.assertNotIn('is_active', settings.BACKOFFICE_EXTRA_NAV[0]['children'][0])


class ExtraNavGroupRenderTests(TestCase):
    def setUp(self):
        User.objects.create_superuser('admin', 'a@example.com', 'pw')
        self.client.login(username='admin', password='pw')

    @override_settings(BACKOFFICE_EXTRA_NAV=GROUP)
    def test_a_group_renders_a_toggle_and_a_link_per_child(self):
        html = self.client.get('/backoffice/forms/').content.decode()
        self.assertIn('<!-- Site-local app group, registered in settings.BACKOFFICE_EXTRA_NAV -->', html)
        group = html.split('<!-- Site-local app group')[1].split('</div>\n            </div>')[0]
        self.assertIn('<button', group)
        self.assertIn('href="/backoffice/news/"', group)
        self.assertIn('href="/backoffice/news/categories/"', group)
        self.assertIn("x-data=\"{ open: false }\"", group)

    @override_settings(BACKOFFICE_EXTRA_NAV=GROUP)
    def test_the_group_starts_open_on_its_own_pages(self):
        html = self.client.get('/backoffice/news/categories/').content.decode()
        group = html.split('<!-- Site-local app group')[1]
        self.assertIn("x-data=\"{ open: true }\"", group)

    @override_settings(BACKOFFICE_EXTRA_NAV=[{'label': 'Flat', 'url_name': 'backoffice:forms',
                                              'url_prefix': '/backoffice/forms/'}])
    def test_a_flat_item_still_renders_as_a_single_link(self):
        html = self.client.get('/backoffice/').content.decode()
        self.assertIn('<!-- Site-local app, registered in settings.BACKOFFICE_EXTRA_NAV -->', html)
        self.assertNotIn('Site-local app group', html)

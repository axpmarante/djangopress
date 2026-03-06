"""Native Gemini FunctionDeclaration schemas for all site assistant tools.

Each tool is defined as a google.genai.types.FunctionDeclaration with typed
parameters. Tools are organized by category and assembled dynamically by
the router based on detected intents.
"""

from google.genai import types

S = types.Schema
T = types.Type

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_I18N_OBJECT = S(
    type=T.OBJECT,
    description='Language-keyed object, e.g. {"pt": "...", "en": "..."}',
)

# ---------------------------------------------------------------------------
# PAGES_TOOLS
# ---------------------------------------------------------------------------

LIST_PAGES = types.FunctionDeclaration(
    name='list_pages',
    description='List all pages with their IDs, titles, slugs, active status, and sort order.',
)

GET_PAGE_INFO = types.FunctionDeclaration(
    name='get_page_info',
    description=(
        'Get detailed page information including section names. '
        'Provide page_id or title (case-insensitive search across all languages).'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'page_id': S(type=T.INTEGER, description='Page ID to look up.'),
            'title': S(type=T.STRING, description='Case-insensitive title search across all languages.'),
        },
    ),
)

CREATE_PAGE = types.FunctionDeclaration(
    name='create_page',
    description=(
        'Create a new page. Provide title_i18n with all enabled languages. '
        'Slug is auto-generated from title if not provided. '
        'The new page is automatically set as the active page.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'title_i18n': S(
                type=T.OBJECT,
                description='Page title per language, e.g. {"pt": "Sobre", "en": "About"}.',
            ),
            'slug_i18n': S(
                type=T.OBJECT,
                description='Page slug per language. Auto-generated from title if omitted.',
            ),
        },
        required=['title_i18n'],
    ),
)

UPDATE_PAGE_META = types.FunctionDeclaration(
    name='update_page_meta',
    description='Update page metadata (title, slug, active status, sort order).',
    parameters=S(
        type=T.OBJECT,
        properties={
            'page_id': S(type=T.INTEGER, description='ID of the page to update.'),
            'title_i18n': S(type=T.OBJECT, description='New title per language.'),
            'slug_i18n': S(type=T.OBJECT, description='New slug per language.'),
            'is_active': S(type=T.BOOLEAN, description='Whether the page is active/visible.'),
            'sort_order': S(type=T.INTEGER, description='Sort order (lower = first).'),
        },
        required=['page_id'],
    ),
)

DELETE_PAGE = types.FunctionDeclaration(
    name='delete_page',
    description='DESTRUCTIVE: Permanently delete a page and all its content. Cannot be undone.',
    parameters=S(
        type=T.OBJECT,
        properties={
            'page_id': S(type=T.INTEGER, description='ID of the page to delete.'),
        },
        required=['page_id'],
    ),
)

REORDER_PAGES = types.FunctionDeclaration(
    name='reorder_pages',
    description='Set the sort order for multiple pages at once.',
    parameters=S(
        type=T.OBJECT,
        properties={
            'order': S(
                type=T.ARRAY,
                description='List of page_id/sort_order pairs.',
                items=S(
                    type=T.OBJECT,
                    properties={
                        'page_id': S(type=T.INTEGER, description='Page ID.'),
                        'sort_order': S(type=T.INTEGER, description='New sort order.'),
                    },
                    required=['page_id', 'sort_order'],
                ),
            ),
        },
        required=['order'],
    ),
)

SET_ACTIVE_PAGE = types.FunctionDeclaration(
    name='set_active_page',
    description=(
        'Switch focus to a specific page. Required before using page-level '
        'tools like refine_section, update_element_styles, etc.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'page_id': S(type=T.INTEGER, description='ID of the page to activate.'),
        },
        required=['page_id'],
    ),
)

PAGES_TOOLS = [
    LIST_PAGES,
    GET_PAGE_INFO,
    CREATE_PAGE,
    UPDATE_PAGE_META,
    DELETE_PAGE,
    REORDER_PAGES,
    SET_ACTIVE_PAGE,
]

# ---------------------------------------------------------------------------
# PAGE_EDIT_TOOLS (require active page)
# ---------------------------------------------------------------------------

REFINE_SECTION = types.FunctionDeclaration(
    name='refine_section',
    description=(
        'AI-regenerate ONE section of the active page. Uses the AI pipeline '
        '(slower, costlier). Use only when structural or design changes are needed.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'section_name': S(
                type=T.STRING,
                description='The data-section name of the section to refine.',
            ),
            'instructions': S(
                type=T.STRING,
                description='Natural language instructions for how to change the section.',
            ),
        },
        required=['section_name', 'instructions'],
    ),
)

REFINE_PAGE = types.FunctionDeclaration(
    name='refine_page',
    description=(
        'AI-regenerate the entire active page. Most expensive operation. '
        'Use only for major redesigns or when multiple sections need coordinated changes.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'instructions': S(
                type=T.STRING,
                description='Natural language instructions for how to change the page.',
            ),
        },
        required=['instructions'],
    ),
)

UPDATE_ELEMENT_STYLES = types.FunctionDeclaration(
    name='update_element_styles',
    description=(
        'Change CSS classes on an element in the active page. '
        'Provide either a CSS selector or a section_name to target the section element itself.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'selector': S(
                type=T.STRING,
                description='CSS selector for the target element, e.g. "section[data-section=\'hero\'] > div > h1".',
            ),
            'section_name': S(
                type=T.STRING,
                description='Target the section element itself by its data-section name.',
            ),
            'new_classes': S(
                type=T.STRING,
                description='Space-separated CSS/Tailwind classes to set on the element.',
            ),
        },
        required=['new_classes'],
    ),
)

UPDATE_ELEMENT_ATTRIBUTE = types.FunctionDeclaration(
    name='update_element_attribute',
    description='Change an HTML attribute (href, src, alt, etc.) on an element in the active page.',
    parameters=S(
        type=T.OBJECT,
        properties={
            'selector': S(
                type=T.STRING,
                description='CSS selector for the target element.',
            ),
            'attribute': S(
                type=T.STRING,
                description='The attribute to change (e.g. "href", "src", "alt").',
            ),
            'value': S(
                type=T.STRING,
                description='The new attribute value. Empty string removes the attribute.',
            ),
        },
        required=['selector', 'attribute', 'value'],
    ),
)

REMOVE_SECTION = types.FunctionDeclaration(
    name='remove_section',
    description='Delete a section from the active page by its data-section name.',
    parameters=S(
        type=T.OBJECT,
        properties={
            'section_name': S(
                type=T.STRING,
                description='The data-section name of the section to remove.',
            ),
        },
        required=['section_name'],
    ),
)

REORDER_SECTIONS = types.FunctionDeclaration(
    name='reorder_sections',
    description=(
        'Reorder sections in the active page. Sections not in the list '
        'are preserved at the end.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'order': S(
                type=T.ARRAY,
                description='Ordered list of data-section names, e.g. ["hero", "features", "cta"].',
                items=S(type=T.STRING),
            ),
        },
        required=['order'],
    ),
)

PAGE_EDIT_TOOLS = [
    REFINE_SECTION,
    REFINE_PAGE,
    UPDATE_ELEMENT_STYLES,
    UPDATE_ELEMENT_ATTRIBUTE,
    REMOVE_SECTION,
    REORDER_SECTIONS,
]

# ---------------------------------------------------------------------------
# NAVIGATION_TOOLS
# ---------------------------------------------------------------------------

LIST_MENU_ITEMS = types.FunctionDeclaration(
    name='list_menu_items',
    description='List all navigation menu items with their hierarchy (parent/children).',
)

CREATE_MENU_ITEM = types.FunctionDeclaration(
    name='create_menu_item',
    description=(
        'Create a navigation menu item. Link to a page (page_id) or an '
        'external/app URL (url). For decoupled app pages (news, etc.), use url.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'label_i18n': S(
                type=T.OBJECT,
                description='Menu label per language, e.g. {"pt": "Sobre", "en": "About"}.',
            ),
            'page_id': S(
                type=T.INTEGER,
                description='Link to this page by ID. Mutually exclusive with url.',
            ),
            'url': S(
                type=T.STRING,
                description='Custom URL (e.g. "/news/" for a decoupled app). Mutually exclusive with page_id.',
            ),
            'parent_id': S(
                type=T.INTEGER,
                description='Parent menu item ID for creating sub-menu items.',
            ),
            'sort_order': S(
                type=T.INTEGER,
                description='Sort order (lower = first). Defaults to 0.',
            ),
        },
        required=['label_i18n'],
    ),
)

UPDATE_MENU_ITEM = types.FunctionDeclaration(
    name='update_menu_item',
    description='Update an existing navigation menu item.',
    parameters=S(
        type=T.OBJECT,
        properties={
            'menu_item_id': S(type=T.INTEGER, description='ID of the menu item to update.'),
            'label_i18n': S(type=T.OBJECT, description='New label per language.'),
            'page_id': S(type=T.INTEGER, description='New page link. Set to null to unlink.'),
            'url': S(type=T.STRING, description='New custom URL.'),
            'sort_order': S(type=T.INTEGER, description='New sort order.'),
            'is_active': S(type=T.BOOLEAN, description='Whether the menu item is visible.'),
            'parent_id': S(type=T.INTEGER, description='New parent menu item ID. Set to null for top-level.'),
        },
        required=['menu_item_id'],
    ),
)

DELETE_MENU_ITEM = types.FunctionDeclaration(
    name='delete_menu_item',
    description='DESTRUCTIVE: Permanently delete a navigation menu item. Cannot be undone.',
    parameters=S(
        type=T.OBJECT,
        properties={
            'menu_item_id': S(type=T.INTEGER, description='ID of the menu item to delete.'),
        },
        required=['menu_item_id'],
    ),
)

NAVIGATION_TOOLS = [
    LIST_MENU_ITEMS,
    CREATE_MENU_ITEM,
    UPDATE_MENU_ITEM,
    DELETE_MENU_ITEM,
]

# ---------------------------------------------------------------------------
# SETTINGS_TOOLS
# ---------------------------------------------------------------------------

GET_SETTINGS = types.FunctionDeclaration(
    name='get_settings',
    description=(
        'Read site settings. Returns all fields by default, or filter by '
        'providing a list of field names.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'fields': S(
                type=T.ARRAY,
                description=(
                    'Optional list of field names to return. '
                    'Omit to get all settings.'
                ),
                items=S(type=T.STRING),
            ),
        },
    ),
)

UPDATE_SETTINGS = types.FunctionDeclaration(
    name='update_settings',
    description=(
        'Update site settings. Allowed fields: '
        'contact_email, contact_phone, site_name_i18n, site_description_i18n, '
        'contact_address_i18n, facebook_url, instagram_url, linkedin_url, '
        'twitter_url, youtube_url, google_maps_embed_url, maintenance_mode, '
        'primary_color, primary_color_hover, secondary_color, accent_color, '
        'background_color, text_color, heading_color, heading_font, body_font, '
        'container_width, border_radius_preset, button_style, button_size, '
        'primary_button_bg, primary_button_text, primary_button_border, '
        'primary_button_hover, secondary_button_bg, secondary_button_text, '
        'secondary_button_border, secondary_button_hover, '
        'design_guide, project_briefing. '
        'Colors are hex codes (e.g. "#1e3a8a"). Fonts are Google Fonts names.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'updates': S(
                type=T.OBJECT,
                description='Object of field_name: new_value pairs to update.',
            ),
        },
        required=['updates'],
    ),
)

SETTINGS_TOOLS = [
    GET_SETTINGS,
    UPDATE_SETTINGS,
]

# ---------------------------------------------------------------------------
# HEADER_FOOTER_TOOLS
# ---------------------------------------------------------------------------

REFINE_HEADER = types.FunctionDeclaration(
    name='refine_header',
    description=(
        'AI-regenerate the site header (navigation bar). '
        'Provides instructions to the AI for how to change the header design or content.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'instructions': S(
                type=T.STRING,
                description='Natural language instructions for how to change the header.',
            ),
        },
        required=['instructions'],
    ),
)

REFINE_FOOTER = types.FunctionDeclaration(
    name='refine_footer',
    description=(
        'AI-regenerate the site footer. '
        'Provides instructions to the AI for how to change the footer design or content.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'instructions': S(
                type=T.STRING,
                description='Natural language instructions for how to change the footer.',
            ),
        },
        required=['instructions'],
    ),
)

HEADER_FOOTER_TOOLS = [
    REFINE_HEADER,
    REFINE_FOOTER,
]

# ---------------------------------------------------------------------------
# FORMS_TOOLS
# ---------------------------------------------------------------------------

LIST_FORMS = types.FunctionDeclaration(
    name='list_forms',
    description='List all dynamic forms with their names, slugs, and submission counts.',
)

CREATE_FORM = types.FunctionDeclaration(
    name='create_form',
    description=(
        'Create a dynamic form. The slug determines the form action URL: '
        '/forms/<slug>/submit/. Use fields_schema to define form fields.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'name': S(type=T.STRING, description='Display name for the form, e.g. "Contact Form".'),
            'slug': S(type=T.STRING, description='URL slug for the form, e.g. "contact".'),
            'notification_email': S(
                type=T.STRING,
                description='Email to notify on new submissions.',
            ),
            'fields_schema': S(
                type=T.ARRAY,
                description='JSON schema defining form fields (labels, types, validation).',
                items=S(type=T.OBJECT),
            ),
            'success_message_i18n': S(
                type=T.OBJECT,
                description='Success message per language shown after submission.',
            ),
            'is_active': S(type=T.BOOLEAN, description='Whether the form accepts submissions. Defaults to true.'),
        },
        required=['name', 'slug'],
    ),
)

UPDATE_FORM = types.FunctionDeclaration(
    name='update_form',
    description='Update an existing dynamic form. Look up by form_id or slug.',
    parameters=S(
        type=T.OBJECT,
        properties={
            'form_id': S(type=T.INTEGER, description='Form ID to update.'),
            'slug': S(type=T.STRING, description='Form slug to look up (alternative to form_id).'),
            'name': S(type=T.STRING, description='New display name.'),
            'notification_email': S(type=T.STRING, description='New notification email.'),
            'fields_schema': S(
                type=T.ARRAY,
                description='New fields schema.',
                items=S(type=T.OBJECT),
            ),
            'success_message_i18n': S(type=T.OBJECT, description='New success message per language.'),
            'is_active': S(type=T.BOOLEAN, description='Whether the form accepts submissions.'),
        },
    ),
)

DELETE_FORM = types.FunctionDeclaration(
    name='delete_form',
    description=(
        'DESTRUCTIVE: Permanently delete a form and ALL its submissions. '
        'Cannot be undone. Look up by form_id or slug.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'form_id': S(type=T.INTEGER, description='Form ID to delete.'),
            'slug': S(type=T.STRING, description='Form slug to delete (alternative to form_id).'),
        },
    ),
)

LIST_FORM_SUBMISSIONS = types.FunctionDeclaration(
    name='list_form_submissions',
    description='List recent form submissions. Optionally filter by form slug.',
    parameters=S(
        type=T.OBJECT,
        properties={
            'form_slug': S(type=T.STRING, description='Filter submissions by form slug.'),
            'limit': S(type=T.INTEGER, description='Maximum number of submissions to return. Defaults to 10.'),
        },
    ),
)

FORMS_TOOLS = [
    LIST_FORMS,
    CREATE_FORM,
    UPDATE_FORM,
    DELETE_FORM,
    LIST_FORM_SUBMISSIONS,
]

# ---------------------------------------------------------------------------
# MEDIA_TOOLS
# ---------------------------------------------------------------------------

LIST_IMAGES = types.FunctionDeclaration(
    name='list_images',
    description='Browse the media library. Search by title or tags.',
    parameters=S(
        type=T.OBJECT,
        properties={
            'search': S(type=T.STRING, description='Search query to filter images by title or tags.'),
            'limit': S(type=T.INTEGER, description='Maximum number of images to return. Defaults to 20.'),
        },
    ),
)

MEDIA_TOOLS = [
    LIST_IMAGES,
]

# ---------------------------------------------------------------------------
# NEWS_TOOLS
# ---------------------------------------------------------------------------

LIST_NEWS_POSTS = types.FunctionDeclaration(
    name='list_news_posts',
    description='List news/blog posts. Optionally filter by published status or category.',
    parameters=S(
        type=T.OBJECT,
        properties={
            'limit': S(type=T.INTEGER, description='Maximum number of posts to return. Defaults to 20.'),
            'published_only': S(type=T.BOOLEAN, description='If true, only return published posts.'),
            'category_id': S(type=T.INTEGER, description='Filter by category ID.'),
        },
    ),
)

GET_NEWS_POST = types.FunctionDeclaration(
    name='get_news_post',
    description=(
        'Get detailed news post information including sections. '
        'Provide post_id or title (case-insensitive search).'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'post_id': S(type=T.INTEGER, description='Post ID to look up.'),
            'title': S(type=T.STRING, description='Case-insensitive title search across all languages.'),
        },
    ),
)

CREATE_NEWS_POST = types.FunctionDeclaration(
    name='create_news_post',
    description=(
        'Create a new news/blog post. Slug is auto-generated from title if not provided.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'title_i18n': S(
                type=T.OBJECT,
                description='Post title per language, e.g. {"pt": "...", "en": "..."}.',
            ),
            'slug_i18n': S(
                type=T.OBJECT,
                description='Post slug per language. Auto-generated from title if omitted.',
            ),
            'excerpt_i18n': S(
                type=T.OBJECT,
                description='Short excerpt/summary per language.',
            ),
            'category_id': S(type=T.INTEGER, description='Category ID to assign.'),
            'featured_image_id': S(type=T.INTEGER, description='SiteImage ID for the featured image.'),
            'is_published': S(type=T.BOOLEAN, description='Whether the post is published. Defaults to false.'),
            'published_date': S(
                type=T.STRING,
                description='Publication date as ISO datetime string, e.g. "2025-01-15T10:00:00".',
            ),
        },
        required=['title_i18n'],
    ),
)

UPDATE_NEWS_POST = types.FunctionDeclaration(
    name='update_news_post',
    description='Update an existing news/blog post.',
    parameters=S(
        type=T.OBJECT,
        properties={
            'post_id': S(type=T.INTEGER, description='ID of the post to update.'),
            'title_i18n': S(type=T.OBJECT, description='New title per language.'),
            'slug_i18n': S(type=T.OBJECT, description='New slug per language.'),
            'excerpt_i18n': S(type=T.OBJECT, description='New excerpt per language.'),
            'category_id': S(type=T.INTEGER, description='New category ID. Set to null to unassign.'),
            'featured_image_id': S(type=T.INTEGER, description='New featured image ID. Set to null to remove.'),
            'is_published': S(type=T.BOOLEAN, description='Whether the post is published.'),
            'published_date': S(
                type=T.STRING,
                description='New publication date as ISO datetime string.',
            ),
        },
        required=['post_id'],
    ),
)

LIST_NEWS_CATEGORIES = types.FunctionDeclaration(
    name='list_news_categories',
    description='List all news categories with their names, slugs, and post counts.',
)

NEWS_TOOLS = [
    LIST_NEWS_POSTS,
    GET_NEWS_POST,
    CREATE_NEWS_POST,
    UPDATE_NEWS_POST,
    LIST_NEWS_CATEGORIES,
]

# ---------------------------------------------------------------------------
# STATS_TOOLS
# ---------------------------------------------------------------------------

GET_STATS = types.FunctionDeclaration(
    name='get_stats',
    description='Get site statistics: total/active pages, images, submissions, and menu items.',
)

STATS_TOOLS = [
    GET_STATS,
]

# ---------------------------------------------------------------------------
# META — request_additional_tools (always included)
# ---------------------------------------------------------------------------

REQUEST_TOOLS_DECLARATION = types.FunctionDeclaration(
    name='request_additional_tools',
    description=(
        'Request tools from additional categories. Use this when the user\'s '
        'request requires tools not currently available. Available categories: '
        'pages, page_edit, navigation, settings, header_footer, forms, media, news, stats.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'categories': S(
                type=T.ARRAY,
                description=(
                    'List of category names to request. Available: '
                    '"pages", "page_edit", "navigation", "settings", '
                    '"header_footer", "forms", "media", "news", "stats".'
                ),
                items=S(type=T.STRING),
            ),
        },
        required=['categories'],
    ),
)

# ---------------------------------------------------------------------------
# Category registry
# ---------------------------------------------------------------------------

TOOL_CATEGORIES = {
    'pages': PAGES_TOOLS,
    'page_edit': PAGE_EDIT_TOOLS,
    'navigation': NAVIGATION_TOOLS,
    'settings': SETTINGS_TOOLS,
    'header_footer': HEADER_FOOTER_TOOLS,
    'forms': FORMS_TOOLS,
    'media': MEDIA_TOOLS,
    'news': NEWS_TOOLS,
    'stats': STATS_TOOLS,
}


def build_tool_declarations(intents):
    """Build a types.Tool list from router intents.

    Args:
        intents: List of category names from the router.

    Returns:
        List with a single types.Tool containing all relevant FunctionDeclarations.
    """
    declarations = []
    for intent in intents:
        if intent in TOOL_CATEGORIES:
            declarations.extend(TOOL_CATEGORIES[intent])
    # Always include the meta tool so the model can request more categories
    declarations.append(REQUEST_TOOLS_DECLARATION)
    return [types.Tool(function_declarations=declarations)]

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
    description=(
        'Update page metadata. title_i18n is the page NAME (menus, headings); the SEO '
        '<title> and meta description are meta_title_i18n / meta_description_i18n. '
        'Per-language dicts are merged: send only the languages you change.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'page_id': S(type=T.INTEGER, description='ID of the page to update.'),
            'title_i18n': S(type=T.OBJECT, description='New page name per language (not the SEO title).'),
            'slug_i18n': S(type=T.OBJECT, description='New slug per language.'),
            'is_active': S(type=T.BOOLEAN, description='Whether the page is active/visible.'),
            'sort_order': S(type=T.INTEGER, description='Sort order (lower = first).'),
            'meta_title_i18n': S(type=T.OBJECT, description='SEO title (<title>) per language.'),
            'meta_description_i18n': S(type=T.OBJECT, description='SEO meta description per language.'),
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

INSERT_SECTION = types.FunctionDeclaration(
    name='insert_section',
    description=(
        'Add ONE new section to the active page at a position. Only the new section is '
        'generated and translated; the rest of the page is not touched. Always use this '
        'to add a section, never refine_page.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'position': S(type=T.STRING, enum=['before', 'after', 'start', 'end'],
                          description='Where to add it: before/after anchor_section, or the start/end of the page.'),
            'anchor_section': S(type=T.STRING,
                                description='data-section name of the existing section (for before/after).'),
            'instructions': S(type=T.STRING,
                              description='What the new section should contain and look like, with the facts to use.'),
        },
        required=['position', 'instructions'],
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
            'add_classes': S(
                type=T.STRING,
                description='Space-separated classes to add; every other class stays.',
            ),
            'remove_classes': S(
                type=T.STRING,
                description='Space-separated classes to remove; every other class stays.',
            ),
            'new_classes': S(
                type=T.STRING,
                description=('Replaces ALL classes on the element. Use only after read_section showed you '
                             'the element; prefer add_classes/remove_classes.'),
            ),
        },
    ),
)

READ_SECTION = types.FunctionDeclaration(
    name='read_section',
    description=('Read the HTML of one section of the active page (editing language), to see its real '
                 'classes and structure before restyling. Read-only.'),
    parameters=S(
        type=T.OBJECT,
        properties={'section_name': S(type=T.STRING, description='The data-section name.')},
        required=['section_name'],
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

FIND_PHOTOS = types.FunctionDeclaration(
    name='find_photos',
    description=('Search photos in the media library and on Unsplash (free stock photos). Returns up to 8 '
                 'candidates with a ref (lib:<id> or unsplash:<id>) that the user sees as thumbnails. Read-only. '
                 'Use English keywords for Unsplash.'),
    parameters=S(type=T.OBJECT, properties={
        'query': S(type=T.STRING, description='What the photo should show, e.g. "grilled fish terrace sunset".'),
        'source': S(type=T.STRING, enum=['both', 'library', 'unsplash'], description='Where to search (default both).'),
        'orientation': S(type=T.STRING, enum=['landscape', 'portrait', 'squarish'],
                         description='Unsplash orientation; landscape for section backgrounds.'),
    }, required=['query']),
)

SET_SECTION_BACKGROUND = types.FunctionDeclaration(
    name='set_section_background',
    description=('Use a photo as the background of a section of the active page, in every language. Keeps an '
                 'existing dark overlay; also replaces a full-bleed background <img>. An unsplash:<id> ref is '
                 'downloaded into the media library first.'),
    parameters=S(type=T.OBJECT, properties={
        'section_name': S(type=T.STRING, description='data-section name of the section.'),
        'image': S(type=T.STRING, description='lib:<id> or unsplash:<id> from find_photos.'),
    }, required=['section_name', 'image']),
)

_SECTION = S(type=T.STRING, description='data-section name of the section holding the slider/gallery.')
_COMPONENT = S(type=T.INTEGER, description='Which slider/gallery in that section, from 1 (default 1).')
_IMAGE_REF = 'An image reference: lib:<id> or unsplash:<id> from find_photos (lib:<id> also from list_images)'

LIST_COMPONENTS = types.FunctionDeclaration(
    name='list_components',
    description=('List the sliders, text sliders (testimonials) and galleries on the active page, with '
                 'their section and a short label per item (numbered from 1). Read-only. Call it before '
                 'changing one.'),
)

REORDER_ITEMS = types.FunctionDeclaration(
    name='reorder_items',
    description=('Reorder the items of a slider or gallery, in every language. No AI regeneration. '
                 'order lists the CURRENT item numbers in the new order, e.g. [3, 1, 2] puts item 3 first.'),
    parameters=S(type=T.OBJECT, properties={
        'section': _SECTION, 'component': _COMPONENT,
        'order': S(type=T.ARRAY, items=S(type=T.INTEGER), description='Every current item number exactly once.'),
    }, required=['section', 'order']),
)

REPLACE_ITEM_IMAGE = types.FunctionDeclaration(
    name='replace_item_image',
    description='Replace the image of one slider/gallery item, in every language (alt text per language).',
    parameters=S(type=T.OBJECT, properties={
        'section': _SECTION, 'component': _COMPONENT,
        'index': S(type=T.INTEGER, description='Item number, from 1.'),
        'image': S(type=T.STRING, description=_IMAGE_REF + '.'),
    }, required=['section', 'index', 'image']),
)

ADD_ITEM_IMAGES = types.FunctionDeclaration(
    name='add_item_images',
    description='Add images to a slider or gallery after an item, in every language.',
    parameters=S(type=T.OBJECT, properties={
        'section': _SECTION, 'component': _COMPONENT,
        'after': S(type=T.INTEGER, description='Insert after this item number (default: the last).'),
        'images': S(type=T.ARRAY, items=S(type=T.STRING), description=_IMAGE_REF + ', one per image.'),
    }, required=['section', 'images']),
)

REMOVE_ITEM = types.FunctionDeclaration(
    name='remove_item',
    description='Remove one item from a slider or gallery, in every language.',
    parameters=S(type=T.OBJECT, properties={
        'section': _SECTION, 'component': _COMPONENT,
        'index': S(type=T.INTEGER, description='Item number, from 1.'),
    }, required=['section', 'index']),
)

FIND_ELEMENTS = types.FunctionDeclaration(
    name='find_elements',
    description=('Find elements across the WHOLE site (every page plus header/footer), grouped by their exact '
                 'classes, with counts, where they are and example texts. Read-only. Use it before a site-wide '
                 'restyle ("all buttons", "every section title") instead of reading pages one by one.'),
    parameters=S(type=T.OBJECT, properties={
        'tags': S(type=T.STRING, description='Comma-separated tags, e.g. "a,button" (default) or "h2".'),
        'has_classes': S(type=T.STRING, description='Only elements that have all these classes.'),
        'text_contains': S(type=T.STRING, description='Only elements whose text contains this.'),
        'pages': S(type=T.ARRAY, items=S(type=T.STRING), description='Page titles; default every active page.'),
    }),
)

RESTYLE_ELEMENTS = types.FunctionDeclaration(
    name='restyle_elements',
    description=('Add/remove classes on every element with the given tags that has ALL has_classes, on every '
                 'page (or the pages given), in every language, in one call; header/footer only when '
                 'include_header_footer is true. Other classes stay. Get has_classes from find_elements.'),
    parameters=S(type=T.OBJECT, properties={
        'tags': S(type=T.STRING, description='Comma-separated tags, e.g. "a,button".'),
        'has_classes': S(type=T.STRING, description='Classes that identify the elements (from find_elements).'),
        'add_classes': S(type=T.STRING, description='Classes to add.'),
        'remove_classes': S(type=T.STRING, description='Classes to remove.'),
        'pages': S(type=T.ARRAY, items=S(type=T.STRING), description='Page titles; default every active page.'),
        'include_header_footer': S(type=T.BOOLEAN, description='Also change the header and footer.'),
    }, required=['has_classes']),
)

PAGE_EDIT_TOOLS = [
    FIND_ELEMENTS,
    RESTYLE_ELEMENTS,
    FIND_PHOTOS,
    SET_SECTION_BACKGROUND,
    LIST_COMPONENTS,
    REORDER_ITEMS,
    REPLACE_ITEM_IMAGE,
    ADD_ITEM_IMAGES,
    REMOVE_ITEM,
    READ_SECTION,
    INSERT_SECTION,
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

VALIDATE_CONTACTS = types.FunctionDeclaration(
    name='validate_contacts',
    description=('Check that the phone, email, WhatsApp and Google Maps details are right and the same '
                 'everywhere (Settings, every page, header and footer, every language): valid formats, '
                 'email domains that receive mail, links that dial/write to what they show. Read-only; '
                 'never changes anything. check_web also compares with what a web search finds, with sources.'),
    parameters=S(type=T.OBJECT, properties={
        'check_web': S(type=T.BOOLEAN, description='Also compare with the web (slower). Default false.'),
    }),
)

SETTINGS_TOOLS = [
    VALIDATE_CONTACTS,
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

VALIDATE_FORMS = types.FunctionDeclaration(
    name='validate_forms',
    description=(
        'Scan all pages and GlobalSections for form issues. Checks: '
        '(1) form action slugs match existing DynamicForm records, '
        '(2) HTML field names match the form fields_schema, '
        '(3) JS in form handlers is not corrupted (escaped operators), '
        '(4) honeypot field is present. '
        'Returns a diagnostic report with issues and suggested fixes.'
    ),
)

TEST_FORM = types.FunctionDeclaration(
    name='test_form',
    description=('Really submit a form with test data: validation, saving, notification and confirmation '
                 'emails. Every email goes ONLY to the operator (the agency), with [TESTE] in the subject, '
                 'never to the client; the test submission is deleted. Without slug it tests every form '
                 'used on the site pages. Use it only when asked, or after creating or editing a form.'),
    parameters=S(type=T.OBJECT, properties={
        'slug': S(type=T.STRING, description='Form slug; omit to test every form on the pages.'),
    }),
)

FORMS_TOOLS = [
    TEST_FORM,
    LIST_FORMS,
    CREATE_FORM,
    UPDATE_FORM,
    DELETE_FORM,
    LIST_FORM_SUBMISSIONS,
    VALIDATE_FORMS,
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
    FIND_PHOTOS,
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
# PROPERTIES_TOOLS
# ---------------------------------------------------------------------------

LIST_PROPERTIES = types.FunctionDeclaration(
    name='list_properties',
    description='List rental properties. Optionally filter by active status or property type.',
    parameters=S(
        type=T.OBJECT,
        properties={
            'limit': S(type=T.INTEGER, description='Maximum number of properties to return. Defaults to 20.'),
            'active_only': S(type=T.BOOLEAN, description='If true, only return active properties.'),
            'property_type': S(type=T.STRING, description='Filter by type: apartment, studio, house, villa, penthouse.'),
        },
    ),
)

GET_PROPERTY = types.FunctionDeclaration(
    name='get_property',
    description=(
        'Get detailed property information including images, capacity, and booking URL. '
        'Provide property_id or name (case-insensitive search across all languages).'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'property_id': S(type=T.INTEGER, description='Property ID to look up.'),
            'name': S(type=T.STRING, description='Case-insensitive name search across all languages.'),
        },
    ),
)

UPDATE_PROPERTY = types.FunctionDeclaration(
    name='update_property',
    description='Update an existing property.',
    parameters=S(
        type=T.OBJECT,
        properties={
            'property_id': S(type=T.INTEGER, description='ID of the property to update.'),
            'name_i18n': S(type=T.OBJECT, description='New name per language.'),
            'description_i18n': S(type=T.OBJECT, description='New description per language.'),
            'property_type': S(type=T.STRING, description='Property type: apartment, studio, house, villa, penthouse.'),
            'city': S(type=T.STRING, description='City name.'),
            'max_guests': S(type=T.INTEGER, description='Maximum number of guests.'),
            'bedrooms': S(type=T.INTEGER, description='Number of bedrooms.'),
            'beds': S(type=T.INTEGER, description='Number of beds.'),
            'typology': S(type=T.STRING, description='Typology, e.g. T1, T2, Studio.'),
            'booking_url': S(type=T.STRING, description='External booking URL.'),
            'featured_image_id': S(type=T.INTEGER, description='SiteImage ID for the featured image.'),
            'is_active': S(type=T.BOOLEAN, description='Whether the property is active/visible.'),
            'sort_order': S(type=T.INTEGER, description='Sort order (lower = first).'),
        },
        required=['property_id'],
    ),
)

LIST_PROPERTY_TEMPLATE_TAGS = types.FunctionDeclaration(
    name='list_property_template_tags',
    description=(
        'List available Django template tags from the properties app that can be embedded in page HTML. '
        'Use this to find out how to embed property cards/grids in CMS pages.'
    ),
)

PROPERTIES_TOOLS = [
    LIST_PROPERTIES,
    GET_PROPERTY,
    UPDATE_PROPERTY,
    LIST_PROPERTY_TEMPLATE_TAGS,
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
        'pages, page_edit, navigation, settings, header_footer, forms, media, news, properties, stats.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={
            'categories': S(
                type=T.ARRAY,
                description=(
                    'List of category names to request. Available: '
                    '"pages", "page_edit", "navigation", "settings", '
                    '"header_footer", "forms", "media", "news", "properties", "stats".'
                ),
                items=S(type=T.STRING),
            ),
        },
        required=['categories'],
    ),
)

WEB_SEARCH_DECLARATION = types.FunctionDeclaration(
    name='web_search',
    description=(
        'Search the web (Google) for facts that are not on the site and not given by the user: '
        'e.g. a book, an award, an event, opening of a venue. Returns an answer with its sources. '
        'Use it before writing such facts into the site; cite the sources in your reply.'
    ),
    parameters=S(
        type=T.OBJECT,
        properties={'query': S(type=T.STRING, description='What to look up, specific (names, place).')},
        required=['query'],
    ),
)

UNDO_DECLARATION = types.FunctionDeclaration(
    name='undo_last_change',
    description=(
        'Undo everything your last change-making reply did (pages, header/footer, settings, menu, forms). '
        'Use when the user says "desfaz", "volta atrás", "undo". If it reports later edits, ask the user, '
        'then call again with force=true.'
    ),
    parameters=S(type=T.OBJECT, properties={'force': S(type=T.BOOLEAN, description='Overwrite later edits too.')}),
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
    'properties': PROPERTIES_TOOLS,
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
            declarations.extend(d for d in TOOL_CATEGORIES[intent] if d not in declarations)
    # Always include the meta tool so the model can request more categories, and web search
    declarations.append(REQUEST_TOOLS_DECLARATION)
    declarations.append(WEB_SEARCH_DECLARATION)
    declarations.append(UNDO_DECLARATION)
    return [types.Tool(function_declarations=declarations)]


# --- every page-scoped tool takes an optional `page` ---------------------------------

PAGE_PARAM = S(type=T.STRING, description=(
    'The page to work on: its title as in the site map (or id). Default: the active page. '
    'Use it to change several pages in one request.'))


def _add_page_param():
    from djangopress.site_assistant.tools import PAGE_SCOPED_TOOLS
    for value in list(globals().values()):
        if isinstance(value, types.FunctionDeclaration) and value.name in PAGE_SCOPED_TOOLS:
            if value.parameters is None:
                value.parameters = S(type=T.OBJECT, properties={'page': PAGE_PARAM})
            elif 'page' not in (value.parameters.properties or {}):
                value.parameters.properties = {**(value.parameters.properties or {}), 'page': PAGE_PARAM}


_add_page_param()

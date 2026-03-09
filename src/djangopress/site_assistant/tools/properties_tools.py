"""Properties app tools — thin adapters for the properties app.

Conditionally imported — if the properties app is not installed, this module
is silently skipped via ImportError in __init__.py.
"""


def list_properties(params, context):
    from properties.models import Property

    qs = Property.objects.select_related('featured_image')

    if params.get('active_only', False):
        qs = qs.filter(is_active=True)
    if params.get('property_type'):
        qs = qs.filter(property_type=params['property_type'])

    limit = params.get('limit', 20)
    properties = qs[:limit]

    return {
        'success': True,
        'properties': [
            {
                'id': p.id,
                'name': p.name_i18n,
                'slug': p.slug,
                'property_type': p.property_type,
                'city': p.city,
                'region': p.region,
                'max_guests': p.max_guests,
                'bedrooms': p.bedrooms,
                'beds': p.beds,
                'typology': p.typology,
                'is_active': p.is_active,
                'sort_order': p.sort_order,
                'featured_image_id': p.featured_image_id,
                'booking_url': p.booking_url,
            }
            for p in properties
        ],
        'total': Property.objects.count(),
        'message': f'Found {len(properties)} properties',
    }


def get_property(params, context):
    from properties.models import Property

    property_id = params.get('property_id')
    name = params.get('name')

    if not property_id and not name:
        return {'success': False, 'message': 'Provide property_id or name'}

    try:
        if property_id:
            prop = Property.objects.select_related('featured_image').get(pk=property_id)
        else:
            props = Property.objects.select_related('featured_image').all()
            prop = None
            for p in props:
                for lang_name in (p.name_i18n or {}).values():
                    if name.lower() in lang_name.lower():
                        prop = p
                        break
                if prop:
                    break
            if not prop:
                return {'success': False, 'message': f'No property found matching "{name}"'}
    except Property.DoesNotExist:
        return {'success': False, 'message': f'Property {property_id} not found'}

    from properties.models import PropertyImage
    gallery = PropertyImage.objects.filter(property=prop).select_related('image')

    return {
        'success': True,
        'property': {
            'id': prop.id,
            'name': prop.name_i18n,
            'slug': prop.slug,
            'property_type': prop.property_type,
            'city': prop.city,
            'region': prop.region,
            'description': prop.description_i18n,
            'max_guests': prop.max_guests,
            'bedrooms': prop.bedrooms,
            'beds': prop.beds,
            'typology': prop.typology,
            'booking_url': prop.booking_url,
            'featured_image_id': prop.featured_image_id,
            'is_active': prop.is_active,
            'sort_order': prop.sort_order,
            'gallery_images': [
                {'image_id': pi.image_id, 'sort_order': pi.sort_order}
                for pi in gallery
            ],
        },
        'message': f'Property "{prop}" found',
    }


def update_property(params, context):
    from properties.models import Property

    property_id = params.get('property_id')
    if not property_id:
        return {'success': False, 'message': 'Missing property_id'}

    try:
        prop = Property.objects.get(pk=property_id)
    except Property.DoesNotExist:
        return {'success': False, 'message': f'Property {property_id} not found'}

    updatable = (
        'name_i18n', 'description_i18n', 'property_type', 'city', 'region',
        'max_guests', 'bedrooms', 'beds', 'typology', 'booking_url',
        'featured_image_id', 'is_active', 'sort_order',
    )
    changed = []
    for field in updatable:
        if field in params:
            setattr(prop, field, params[field])
            changed.append(field)

    if not changed:
        return {'success': False, 'message': 'No fields to update'}

    prop.save()
    return {
        'success': True,
        'message': f'Property "{prop}" updated: {", ".join(changed)}',
    }


def list_property_template_tags(params, context):
    return {
        'success': True,
        'template_tags': [
            {
                'name': 'featured_properties',
                'load': '{% load property_tags %}',
                'usage': '{% featured_properties 3 %}',
                'description': (
                    'Renders a grid of N property cards (default 3) with images, '
                    'names, locations, capacity info, and booking buttons. '
                    'Uses the same card design as the /apartments-villas/ listing page. '
                    'Properties are pulled from the database in sort_order.'
                ),
                'example': '{% load property_tags %}{% featured_properties 3 %}',
            },
            {
                'name': 'properties_list',
                'load': '{% load property_tags %}',
                'usage': '{% properties_list %}',
                'description': (
                    'Renders the full property card grid (all active properties). '
                    'Used on the dedicated properties listing page.'
                ),
                'example': '{% load property_tags %}{% properties_list %}',
            },
        ],
        'message': (
            'Available template tags for embedding properties in CMS pages. '
            'Use refine_section to inject these into page HTML.'
        ),
    }


PROPERTIES_TOOLS = {
    'list_properties': list_properties,
    'get_property': get_property,
    'update_property': update_property,
    'list_property_template_tags': list_property_template_tags,
}

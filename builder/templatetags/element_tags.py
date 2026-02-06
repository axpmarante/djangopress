from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def render_element(context, element):
    """
    Render an element with the current language context
    """
    language = context.get('LANGUAGE_CODE', 'pt')
    edit_mode = context.get('edit_mode', False)
    return element.render(language=language, edit_mode=edit_mode)

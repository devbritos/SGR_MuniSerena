from django import template
from core.role_access import can_access

register = template.Library()


@register.simple_tag(takes_context=True)
def allowed_route(context, route):
    return can_access(context['request'].user, route)


@register.filter
def can_visit(user, route):
    if not hasattr(user, '_sgr_ui_access'):
        user._sgr_ui_access = {}
    if route not in user._sgr_ui_access:
        user._sgr_ui_access[route] = can_access(user, route)
    return user._sgr_ui_access[route]

from django import template
from analytics.calculations import MAXIMO_CUMPLIMIENTO

register = template.Library()


@register.inclusion_tag('components/_semaphore_rules.html', takes_context=True)
def semaphore_rules(context):
    return {
        'maximum_compliance': MAXIMO_CUMPLIMIENTO,
        'is_demo': getattr(context.get('period'), 'semaphore', '') == 'DEMO',
    }

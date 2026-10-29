from django.core.paginator import Paginator
from django.db.models import Q


def search_queryset(queryset, query, *fields):
    query = (query or '').strip()
    if not query:
        return queryset
    conditions = Q()
    for field in fields:
        conditions |= Q(**{f'{field}__icontains': query})
    return queryset.filter(conditions)


def paginate(request, queryset, per_page=20):
    return Paginator(queryset, per_page).get_page(request.GET.get('page'))

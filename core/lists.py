from django.core.paginator import Paginator
from django.db.models import Q


LIST_SORT_OPTIONS = (
    ('recent', 'Más recientes'),
    ('oldest', 'Más antiguos'),
    ('az', 'Nombre: A–Z'),
    ('za', 'Nombre: Z–A'),
)
PAGE_SIZE_OPTIONS = (20, 50, 100)


def search_queryset(queryset, query, *fields):
    query = (query or '').strip()
    if not query:
        return queryset
    conditions = Q()
    for field in fields:
        conditions |= Q(**{f'{field}__icontains': query})
    return queryset.filter(conditions)


def paginate(request, queryset, per_page=20, page_size_options=None):
    page_size = get_page_size(
        request,
        default=per_page,
        page_size_options=page_size_options,
    )
    return Paginator(queryset, page_size).get_page(request.GET.get('page'))


def get_page_size(request, default=20, page_size_options=None):
    allowed_sizes = page_size_options or PAGE_SIZE_OPTIONS
    value = request.GET.get('per_page', '')
    try:
        page_size = int(value)
    except (TypeError, ValueError):
        return default
    return page_size if page_size in allowed_sizes else default


def apply_list_sort(queryset, request, sort_fields):
    sort_key = request.GET.get('sort', '')
    ordering = sort_fields.get(sort_key)
    if ordering is None:
        return queryset
    if isinstance(ordering, str):
        ordering = (ordering,)
    return queryset.order_by(*ordering)


def list_controls_context(
    request,
    default_page_size=20,
    page_size_options=None,
    sort_options=None,
):
    allowed_page_sizes = page_size_options or PAGE_SIZE_OPTIONS
    allowed_sort_options = sort_options or LIST_SORT_OPTIONS
    ignored_filters = {'sort', 'page', 'per_page', 'export'}
    return {
        'sort_options': allowed_sort_options,
        'search_query': request.GET.get('q', ''),
        'has_list_filters': any(
            key not in ignored_filters and any(value.strip() for value in values)
            for key, values in request.GET.lists()
        ),
        'selected_sort': (
            request.GET.get('sort', '')
            if request.GET.get('sort', '') in dict(allowed_sort_options)
            else ''
        ),
        'page_size_options': allowed_page_sizes,
        'selected_page_size': get_page_size(
            request,
            default=default_page_size,
            page_size_options=allowed_page_sizes,
        ),
    }


class ListControlsMixin:
    sort_fields = {}

    def get_paginate_by(self, queryset):
        if self.paginate_by is None:
            return None
        return get_page_size(self.request, default=self.paginate_by)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(list_controls_context(self.request, self.paginate_by or 20))
        return context

import logging

from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404

from .error_views import ERROR_TEMPLATES, render_error_page


logger = logging.getLogger(__name__)


class CustomErrorPagesMiddleware:
    """Use branded error pages in debug mode instead of Django's technical pages."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        show_custom_errors = (
            settings.DEBUG and settings.CUSTOM_ERROR_PAGES_IN_DEBUG
        )
        try:
            response = self.get_response(request)
        except Exception as exception:
            if not show_custom_errors:
                raise
            if isinstance(exception, Http404):
                status_code = 404
            elif isinstance(exception, PermissionDenied):
                status_code = 403
            elif isinstance(exception, SuspiciousOperation):
                status_code = 400
            else:
                logger.exception(
                    'Unhandled error while processing %s',
                    request.path,
                )
                status_code = 500
            return render_error_page(status_code)

        if not show_custom_errors or response.status_code not in ERROR_TEMPLATES:
            return response

        content_type = response.headers.get('Content-Type', '')
        if not content_type.lower().startswith('text/html'):
            return response

        return render_error_page(response.status_code)

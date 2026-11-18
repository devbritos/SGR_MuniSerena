from django.http import HttpResponse
from django.template.loader import render_to_string


ERROR_TEMPLATES = {
    400: '400.html',
    403: '403.html',
    404: '404.html',
    500: '500.html',
}


def render_error_page(status_code):
    content = render_to_string(ERROR_TEMPLATES[status_code])
    return HttpResponse(content, status=status_code)


def handler400(request, exception=None):
    return render_error_page(400)


def handler403(request, exception=None):
    return render_error_page(403)


def csrf_failure(request, reason=''):
    return handler403(request)


def handler404(request, exception=None):
    return render_error_page(404)


def handler500(request):
    return render_error_page(500)

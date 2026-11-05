from django.shortcuts import render


def handler400(request, exception=None):
    return render(request, '400.html', status=400)


def handler403(request, exception=None):
    return render(request, '403.html', status=403)


def csrf_failure(request, reason=''):
    return handler403(request)


def handler404(request, exception=None):
    return render(request, '404.html', status=404)


def handler500(request):
    return render(request, '500.html', status=500)

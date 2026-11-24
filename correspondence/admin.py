from django.contrib import admin

from .models import OfficeLetter


@admin.register(OfficeLetter)
class OfficeLetterAdmin(admin.ModelAdmin):
    readonly_fields = ('attention',)
    list_display = (
        'registry_number',
        'received_at',
        'sender',
        'state',
        'delegation',
        'responsible',
    )
    list_filter = ('state', 'delegation', 'received_at')
    search_fields = (
        'registry_number',
        'sender',
        'recipient',
        'subject',
    )
    date_hierarchy = 'received_at'

from django.contrib import admin

from .models import (
    CommunityEvent,
    DelegationPerson,
    EventRegistration,
    RegistrationChild,
)


@admin.register(CommunityEvent)
class CommunityEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'delegation', 'starts_at', 'event_type', 'status')
    list_filter = ('status', 'event_type', 'delegation', 'starts_at')
    search_fields = ('title', 'description', 'what_to_expect', 'location')
    date_hierarchy = 'starts_at'


@admin.register(DelegationPerson)
class DelegationPersonAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'rut', 'delegation', 'is_active')
    list_filter = ('delegation', 'is_active')
    search_fields = ('full_name', 'rut', 'email')


class RegistrationChildInline(admin.TabularInline):
    model = RegistrationChild
    extra = 0


@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = ('event', 'full_name', 'rut', 'status', 'email_verified_at')
    list_filter = ('status', 'event__delegation', 'event')
    search_fields = ('full_name', 'rut', 'email')
    inlines = [RegistrationChildInline]
    readonly_fields = (
        'email_verification_token_hash',
        'email_verification_sent_at',
        'email_verified_at',
        'consented_at',
    )

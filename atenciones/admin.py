from django.contrib import admin

from .models import Attention, AttentionType, SubAttention, AttentionFollowUp


class AttentionFollowUpInline(admin.TabularInline):
    model = AttentionFollowUp
    extra = 0
    can_delete = False
    readonly_fields = (
        'author', 'created_at', 'note', 'status', 'responsible',
        'next_action', 'next_contact_date', 'closure_outcome', 'closure_details',
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Attention)
class AttentionAdmin(admin.ModelAdmin):
    list_display = ('requester_name', 'delegation', 'status', 'followup_responsible', 'next_contact_date')
    list_filter = ('status', 'delegation')
    search_fields = ('requester_name', 'requester_contact')
    readonly_fields = (
        'status', 'followup_responsible', 'next_action', 'next_contact_date',
        'closure_outcome', 'closure_details', 'closed_at',
    )
    inlines = (AttentionFollowUpInline,)


admin.site.register(AttentionType)
admin.site.register(SubAttention)

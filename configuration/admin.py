from django.contrib import admin, messages

from .models import Goal, Measuring, Period

AUDIT_FIELDS = ('created_at', 'updated_at', 'deleted_at')


class GoalInline(admin.TabularInline):
    model = Goal
    fields = ('position', 'measuring', 'target_value', 'unity', 'weight', 'validity')
    autocomplete_fields = ('position', 'measuring')
    extra = 0


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'start_date',
        'end_date',
        'computable_days',
        'status',
        'version_parameter',
        'minimum_threshold',
        'maximum_computable_days',
        'semaphore',
    )
    list_filter = ('status', 'semaphore')
    search_fields = ('version_parameter',)
    ordering = ('-start_date',)
    readonly_fields = AUDIT_FIELDS
    inlines = [GoalInline]


@admin.register(Measuring)
class MeasuringAdmin(admin.ModelAdmin):
    list_display = ('id', 'service', 'measurable_item', 'validity')
    list_filter = ('validity',)
    search_fields = ('service', 'measurable_item')
    ordering = ('service', 'measurable_item')
    readonly_fields = AUDIT_FIELDS


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'target_value',
        'weight',
        'unity',
        'position',
        'measuring',
        'period',
        'validity',
    )
    list_filter = ('validity', 'period', 'measuring')
    search_fields = ('target_value', 'unity')
    autocomplete_fields = ('position', 'measuring', 'period')
    ordering = ('-period__start_date', 'position__name')
    list_select_related = ('position', 'measuring', 'period')
    readonly_fields = AUDIT_FIELDS
    actions = ['deactivate_goals', 'activate_goals']

    @admin.action(description="Desactivar metas seleccionadas")
    def deactivate_goals(self, request, queryset):
        updated = queryset.update(validity=False)
        self.message_user(request, f"{updated} meta(s) desactivada(s).", messages.SUCCESS)

    @admin.action(description="Activar metas seleccionadas")
    def activate_goals(self, request, queryset):
        updated = queryset.update(validity=True)
        self.message_user(request, f"{updated} meta(s) activada(s).", messages.SUCCESS)
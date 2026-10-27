from django.contrib import admin, messages
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from .models import Activity, Evidence

AUDIT_FIELDS = ('created_at', 'updated_at', 'deleted_at')


class EvidenceInline(admin.TabularInline):
    model = Evidence
    fk_name = "activity"
    fields = ("name", "author", "date_evidence", "metadata", "validity_state", "functionary")
    readonly_fields = ("validity_state",)
    autocomplete_fields = ("functionary",)
    extra = 0
    show_change_link = True


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'date',
        'application',
        'name_contact',
        'telephone_contact',
        'state_validity',
        'is_valid',
        'functionary',
        'measuring',
        'commitment',
    )
    list_filter = ('state_validity', 'measuring', 'date', 'functionary')
    search_fields = (
        'application',
        'name_contact',
        'telephone_contact',
        'functionary__names',
        'functionary__lastnames',
    )
    ordering = ('-date',)
    date_hierarchy = 'date'
    list_select_related = ('functionary', 'measuring', 'commitment')
    autocomplete_fields = ('functionary', 'measuring', 'commitment')
    readonly_fields = (*AUDIT_FIELDS, 'state_validity')
    inlines = [EvidenceInline]

    def get_queryset(self, request):
        latest_evidence = Evidence.objects.filter(
            activity_id=OuterRef('pk'),
        ).order_by('-created_at', '-pk')
        return super().get_queryset(request).annotate(
            latest_evidence_state=Subquery(
                latest_evidence.values('validity_state')[:1],
            )
        )

    @admin.display(boolean=True, description="Válida")
    def is_valid(self, obj):
        return (
            obj.state_validity == 'VALIDATED'
            and obj.latest_evidence_state == Evidence.Validity.APPROVED
        )


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'author',
        'date_evidence',
        'validity_state',
        'verificator',
        'activity',
        'functionary',
    )
    list_filter = ('validity_state', 'date_evidence')
    search_fields = ('name', 'author', 'activity__application')
    ordering = ('-date_evidence',)
    list_select_related = ('verificator', 'activity', 'functionary')
    autocomplete_fields = ('activity', 'verificator', 'functionary')
    readonly_fields = (*AUDIT_FIELDS, 'validity_state', 'date_validity', 'verificator')
    actions = ['approve_evidences', 'reject_evidences']

    def _verifier(self, request):
        # Funcionario del usuario logueado (None hasta que exista User → Functionary).
        return getattr(request.user, "functionary", None)

    def _is_admin(self, request, verifier):
        return (
            request.user.is_staff
            or request.user.is_superuser
            or (verifier is not None and verifier.is_admin)
        )

    def _is_latest_evidence(self, evidence):
        latest = evidence.activity.evidences.order_by(
            '-created_at',
            '-pk',
        ).first()
        return latest is not None and latest.pk == evidence.pk

    @admin.action(description="Aprobar evidencias seleccionadas", permissions=["change"])
    @transaction.atomic
    def approve_evidences(self, request, queryset):
        verifier = self._verifier(request)
        is_admin = self._is_admin(request, verifier)
        approved = skipped = stale = 0
        for ev in queryset.filter(validity_state=Evidence.Validity.PENDING):
            if not self._is_latest_evidence(ev):
                stale += 1
                continue
            if verifier and ev.functionary_id == verifier.pk and not is_admin:
                skipped += 1  # no puede aprobar lo que subió él mismo
                continue
            ev.validity_state = Evidence.Validity.APPROVED
            ev.date_validity = timezone.localdate()
            ev.verificator = verifier
            ev.save()
            ev.activity.state_validity = 'VALIDATED'
            ev.activity.save(update_fields=['state_validity', 'updated_at'])
            approved += 1
        self.message_user(request, f"{approved} evidencia(s) aprobada(s).", messages.SUCCESS)
        if skipped:
            self.message_user(
                request,
                f"{skipped} omitida(s): el verificador no puede aprobar sus propias evidencias.",
                messages.WARNING,
            )
        if stale:
            self.message_user(
                request,
                f"{stale} omitida(s): existe una evidencia más reciente para la actividad.",
                messages.WARNING,
            )

    @admin.action(description="Rechazar evidencias seleccionadas", permissions=["change"])
    @transaction.atomic
    def reject_evidences(self, request, queryset):
        verifier = self._verifier(request)
        is_admin = self._is_admin(request, verifier)
        rejected = skipped = stale = 0
        for ev in queryset.filter(validity_state=Evidence.Validity.PENDING):
            if not self._is_latest_evidence(ev):
                stale += 1
                continue
            if verifier and ev.functionary_id == verifier.pk and not is_admin:
                skipped += 1
                continue
            ev.validity_state = Evidence.Validity.REJECTED
            ev.date_validity = timezone.localdate()
            ev.verificator = verifier
            ev.save()
            ev.activity.state_validity = 'REJECTED'
            ev.activity.save(update_fields=['state_validity', 'updated_at'])
            rejected += 1
        self.message_user(request, f"{rejected} evidencia(s) rechazada(s).", messages.SUCCESS)
        if skipped:
            self.message_user(
                request,
                f"{skipped} omitida(s): no se puede revisar evidencia propia.",
                messages.WARNING,
            )
        if stale:
            self.message_user(
                request,
                f"{stale} omitida(s): existe una evidencia más reciente para la actividad.",
                messages.WARNING,
            )
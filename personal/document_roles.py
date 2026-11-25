"""Perfiles del descriptor de funciones, limitados a los módulos disponibles."""

COMMON = {
    'activities.activity': ('view', 'add', 'change'),
    'activities.evidence': ('view', 'add'),
    'agenda.commitment': ('view', 'add', 'change'),
    'agenda.meeting': ('view', 'add', 'change'),
    'agenda.meetingagreement': ('view', 'add', 'change'),
}
READ = ('view',)
WRITE = ('view', 'add', 'change')
ATTENTIONS = {'atenciones.attention': WRITE}
ORG_READ = {'organizations.organization': READ, 'organizations.organizationleader': READ}
ORG_WRITE = {key: WRITE for key in ORG_READ}
LETTER_READ = {'correspondence.officeletter': READ}
LETTER_WRITE = {'correspondence.officeletter': WRITE}
EVENT_READ = {
    'events.communityevent': READ, 'events.eventorganization': READ,
    'events.delegationperson': READ, 'events.eventregistration': READ,
}
EVENT_WRITE = {key: WRITE for key in EVENT_READ}

# Código, cargo, nombre y apellido ficticios, permisos propios del cargo.
PROFILES = (
    ('DOC_DELEGATE', 'Delegado', 'Carlos', 'Valdes', {
        **ATTENTIONS, **ORG_WRITE, **LETTER_WRITE, **EVENT_WRITE,
        'activities.evidence': WRITE,
    }),
    ('DOC_SOCIAL', 'Gestor Social', 'Maria', 'Fuentes', {
        **ATTENTIONS, **ORG_READ, **LETTER_READ, **EVENT_READ,
    }),
    ('DOC_ADMIN_SUPPORT', 'Apoyo Administrativo', 'Paula', 'Morales', {
        **ATTENTIONS, **ORG_READ, **LETTER_WRITE, **EVENT_WRITE,
    }),
    ('DOC_ORGANIZATIONS', 'Organizaciones Comunitarias', 'Andres', 'Rojas', {
        **ATTENTIONS, **ORG_WRITE, **LETTER_READ, **EVENT_WRITE,
    }),
    ('DOC_PROCUREMENT', 'Gestor de Compras y Proyectos', 'Diego', 'Castro', {
        **LETTER_WRITE, **EVENT_READ,
    }),
    ('DOC_PLANNING', 'Gestión y Planificación', 'Valentina', 'Herrera', {
        'atenciones.attention': READ, **ORG_READ, **LETTER_READ, **EVENT_READ,
    }),
    ('DOC_SERVICES', 'Coordinador de Servicios Comunitarios', 'Javier', 'Navarro', {
        **ATTENTIONS, **ORG_READ, **LETTER_READ, **EVENT_READ,
    }),
)
ROLE_LABELS = {code: title for code, title, *_ in PROFILES}


def profile_permissions(extra):
    return {
        f'{app}.{action}_{model}'
        for label, actions in {**COMMON, **extra}.items()
        for app, model in [label.split('.')]
        for action in actions
    }

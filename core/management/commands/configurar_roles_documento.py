import os
import unicodedata

from django.contrib.auth.models import Permission, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from personal.document_roles import PROFILES, profile_permissions
from personal.models import Delegation, Functionary, FunctionaryRole, Position, Role


def username_for(names, paternal_surname):
    value = f'{names[0]}.{paternal_surname}'.lower()
    return ''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c))


class Command(BaseCommand):
    help = 'Configura los siete perfiles del descriptor y, opcionalmente, cuentas ficticias.'

    def add_arguments(self, parser):
        parser.add_argument('--delegation', help='Código de delegación para las cuentas ficticias.')
        parser.add_argument('--create-users', action='store_true')
        parser.add_argument('--dry-run', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        create_users = options['create_users']
        password = os.environ.get('SGR_DEMO_PASSWORD')
        delegation = None
        if create_users:
            if not password:
                raise CommandError('Define SGR_DEMO_PASSWORD en el entorno; no se guarda en el código.')
            delegation = Delegation.objects.filter(
                code=options['delegation'], state='ACTIVO', deleted_at__isnull=True,
            ).first()
            if not delegation:
                raise CommandError('Indica con --delegation el código de una delegación activa.')

        available_permissions = list(Permission.objects.select_related('content_type'))
        for code, title, names, surname, extra in PROFILES:
            required = profile_permissions(extra)
            permissions = [p for p in available_permissions
                           if f'{p.content_type.app_label}.{p.codename}' in required]
            found = {f'{p.content_type.app_label}.{p.codename}' for p in permissions}
            if found != required:
                raise CommandError(f'Faltan permisos; revisa las migraciones: {sorted(required - found)}')
            role, _ = Role.objects.get_or_create(role_name=code)
            role.description = (
                f'{title}. Perfil según el descriptor de funciones. Alcance: delegación asignada; '
                'los registros conservan las restricciones de autoría y responsabilidad del módulo. '
                'Sin administración de usuarios, roles o catálogos; sin eliminación de registros.'
            )
            role.authorized_scope = 'DELEGATION'
            role.is_active = True
            role.deleted_at = None
            role.save()
            role.permissions.set(permissions)
            self.stdout.write(f'ROL {title}: {len(required)} permisos')
            if not create_users:
                continue

            username = username_for(names, surname)
            marker = f'{username}@pruebas.sgr.invalid'
            user = User.objects.filter(username__iexact=username).first()
            if user:
                fn = Functionary.objects.filter(user=user).first()
                if (user.email != marker or user.is_staff or user.is_superuser or not fn
                        or fn.delegation_id != delegation.pk or fn.names != names or fn.lastnames != surname
                        or not fn.has_role(code)):
                    raise CommandError(f'{username} ya existe y no corresponde a esta cuenta de prueba. No se modifica.')
                self.stdout.write(f'EXISTENTE {username} | {title} | {delegation.name} (clave conservada)')
                continue
            position = Position.objects.filter(name=title, deleted_at__isnull=True, validity=True).first()
            if not position:
                position = Position.objects.create(name=title, default_role=role)
            user = User.objects.create_user(
                username=username, password=password, first_name=names, last_name=surname,
                email=marker, is_staff=False, is_superuser=False,
            )
            fn = Functionary.objects.create(
                user=user, names=names, lastnames=surname, position=position, delegation=delegation,
            )
            # El cargo existente puede tener otro rol automático: la cuenta nueva
            # recibe exclusivamente el perfil solicitado, sin privilegios heredados.
            FunctionaryRole.objects.filter(functionary=fn).exclude(role=role).delete()
            FunctionaryRole.objects.get_or_create(functionary=fn, role=role)
            self.stdout.write(f'CREADO {username} | {title} | {delegation.name}')
        if options['dry_run']:
            transaction.set_rollback(True)
            self.stdout.write('Simulación: no se guardaron cambios.')

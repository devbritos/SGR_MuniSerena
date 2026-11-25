import os
import unicodedata

from django.contrib.auth.models import Group, Permission, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from organizations.community_access import ADMIN_ROLE, MEMBER_ROLE, PORTAL_GROUP
from organizations.models import NeighborhoodMember, Organization, OrganizationLeader
from personal.models import Functionary, Role


class Command(BaseCommand):
    help = 'Configura el portal y su administrador para una junta específica, sin crear un funcionario municipal.'

    def add_arguments(self, parser):
        parser.add_argument('--organization', type=int, required=True)
        parser.add_argument('--username', default='j.vecinos')
        parser.add_argument('--dry-run', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        organization = Organization.objects.select_for_update().select_related('delegation').get(pk=options['organization'], deleted_at__isnull=True)
        if organization.status == Organization.Status.INACTIVE or organization.delegation.state != 'ACTIVO':
            raise CommandError('La junta y su delegación deben estar activas.')
        base = {'organizations.view_neighborhoodmember', 'organizations.view_organizationleader',
                'correspondence.add_officeletter', 'correspondence.view_officeletter'}
        admin = base | {'organizations.manage_board', 'organizations.add_neighborhoodmember', 'organizations.change_neighborhoodmember'}
        roles = {}
        available = list(Permission.objects.select_related('content_type'))
        for code, required in ((MEMBER_ROLE, base), (ADMIN_ROLE, admin)):
            permissions = [p for p in available if f'{p.content_type.app_label}.{p.codename}' in required]
            if len(permissions) != len(required):
                raise CommandError('Faltan permisos del portal. Aplica primero las migraciones.')
            role, _ = Role.objects.get_or_create(role_name=code)
            role.description = 'Acceso exclusivamente a la junta vinculada: cartas, integrantes y perfil. Los tres cargos vigentes de directiva habilitan el envío de cartas.'
            if code == ADMIN_ROLE:
                role.description += ' Administra integrantes y asigna presidente, secretario y tesorero.'
            role.authorized_scope = 'DELEGATION'
            role.is_active, role.deleted_at = True, None
            role.save()
            role.permissions.set(permissions)
            roles[code] = role
        group, _ = Group.objects.get_or_create(name=PORTAL_GROUP)
        user = User.objects.filter(username__iexact=options['username']).first()
        if user:
            member = NeighborhoodMember.objects.filter(user=user, organization=organization, role=roles[ADMIN_ROLE]).first()
            if not member or user.is_staff or user.is_superuser or Functionary.objects.filter(user=user).exists():
                raise CommandError('Ese usuario ya existe y no es el administrador de esta junta. No se modifica.')
            self.stdout.write('Cuenta existente: se conserva su contraseña.')
        else:
            password = os.environ.get('SGR_BOARD_PASSWORD')
            if not password:
                raise CommandError('Define SGR_BOARD_PASSWORD para crear la cuenta. No se guarda en el código.')
            user = User.objects.create_user(username=options['username'], password=password, first_name='Administrador', last_name='Junta de Vecinos')
            member = NeighborhoodMember.objects.create(user=user, organization=organization, role=roles[ADMIN_ROLE], names='Administrador', lastnames='Junta de Vecinos')
        user.groups.add(group)

        # Vincular los dirigentes vigentes existentes sin duplicar sus fichas.
        occupied = set()
        today = timezone.localdate()
        for leader in organization.leaders.filter(is_active=True, deleted_at__isnull=True):
            if leader.starts_on and leader.starts_on > today or leader.ends_on and leader.ends_on < today:
                continue
            title = ''.join(c for c in unicodedata.normalize('NFKD', leader.position.lower()) if not unicodedata.combining(c))
            code = next((code for prefix, code in (('president', 'PRESIDENT'), ('secretar', 'SECRETARY'), ('tesorer', 'TREASURER')) if prefix in title), None)
            if not code:
                continue
            if code in occupied:
                raise CommandError(f'Hay más de un dirigente vigente para {code}; revisa la directiva antes de vincular las cuentas.')
            occupied.add(code)
            if leader.member_id:
                if leader.member.organization_id != organization.pk:
                    raise CommandError('Un dirigente está vinculado a otra junta.')
                neighbor = leader.member
            else:
                parts = leader.name.strip().split(maxsplit=1)
                neighbor, _ = NeighborhoodMember.objects.get_or_create(
                    organization=organization, names=parts[0], lastnames=parts[1] if len(parts) > 1 else '',
                    defaults={'role': roles[MEMBER_ROLE], 'phone': leader.phone, 'email': leader.email},
                )
            leader.member, leader.board_position = neighbor, code
            leader.save(update_fields=['member', 'board_position', 'updated_at'])
        self.stdout.write(f'CUENTA {user.username} | Administrador de junta de vecinos | {organization.name}')
        self.stdout.write('Acceso: /mi-junta/ | Envío de cartas: solo presidente, secretario o tesorero vigente.')
        if options['dry_run']:
            transaction.set_rollback(True)
            self.stdout.write('Simulación: no se guardaron cambios.')

import random
import re
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from faker import Faker

from activities.models import Activity, Evidence
from agenda.models import Commitment
from atenciones.models import Attention, AttentionType, SubAttention
from configuration.models import Measuring
from personal.models import (
    Delegation,
    Functionary,
    FunctionaryRole,
    Position,
    Role,
)


SEED_VERSION = 20261109
SEED_COUNTS = {
    'attentions': 1000,
    'commitments': 400,
    'activities': 400,
    'evidences': 200,
}
SEED_EVIDENCE_FILE = 'evidences/semillas/ejemplo.pdf'
SEED_EVIDENCE_CONTENT = (
    b'%PDF-1.1\n'
    b'1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n'
    b'2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\n'
    b'trailer<</Root 1 0 R>>\n%%EOF\n'
)


class Command(BaseCommand):
    help = (
        'Crea datos reproducibles de prueba (2.000 registros de negocio) '
        'y seis cuentas locales.'
    )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                'poblar_bd solo se permite con DEBUG=True; no ejecutes semillas '
                'en producción.'
            )
        if not settings.SEED_USER_PASSWORD:
            raise CommandError(
                'Define SEED_USER_PASSWORD en .env antes de crear las cuentas '
                'de prueba.'
            )
        if len(settings.SEED_USER_PASSWORD) < 16:
            raise CommandError(
                'SEED_USER_PASSWORD debe tener al menos 16 caracteres.'
            )
        try:
            validate_password(settings.SEED_USER_PASSWORD)
        except ValidationError as error:
            raise CommandError(
                f'SEED_USER_PASSWORD no cumple la política de contraseñas: {error}'
            ) from error

        with transaction.atomic():
            self.stdout.write('Creando catálogos y seis cuentas...')
            delegations, functionaries_by_delegation = (
                self._create_accounts_and_catalogs()
            )
            attention_types, sub_attentions_by_type = (
                self._create_attention_catalogs()
            )
            measuring, commitments = self._create_commitments(
                functionaries_by_delegation,
                delegations,
            )
            created = {
                'commitments': len(commitments),
            }
            created['attentions'] = self._create_attentions(
                delegations,
                functionaries_by_delegation,
                attention_types,
                sub_attentions_by_type,
            )
            activities = self._create_activities(
                functionaries_by_delegation,
                measuring,
                commitments,
            )
            created['activities'] = len(activities)
            created['evidences'] = self._create_evidences(
                activities,
                functionaries_by_delegation,
            )

            if any(created.values()):
                from core.realtime.signals import schedule_data_update

                schedule_data_update()

            total = sum(SEED_COUNTS.values())
            created_total = sum(created.values())
            self.stdout.write(
                self.style.SUCCESS(
                    f'Semilla completada: {created_total} registros nuevos; '
                    f'{total} registros de negocio esperados '
                    '(1.000 atenciones, 400 compromisos, 400 actividades y '
                    '200 evidencias).'
                )
            )

    def _create_accounts_and_catalogs(self):
        delegations_data = [
            {
                'name': 'Delegación Los Vilos',
                'code': 'LOS-VILOS',
                'commune': 'Los Vilos',
                'field': 'RURAL',
            },
            {
                'name': 'Delegación La Serena',
                'code': 'LA-SERENA',
                'commune': 'La Serena',
                'field': 'URBANO',
            },
        ]
        delegations = []
        for data in delegations_data:
            delegation, _ = Delegation.objects.get_or_create(
                name=data['name'],
                defaults={
                    'code': data['code'],
                    'commune': data['commune'],
                    'address': f'Plaza de Armas, {data["commune"]}',
                    'field': data['field'],
                },
            )
            delegations.append(delegation)

        role_labels = {
            Role.ADMIN: 'Administrador',
            Role.COORDINATOR: 'Coordinador',
            Role.DELEGATE: 'Delegado',
            Role.FUNCTIONARY: 'Funcionario',
            Role.VERIFIER: 'Verificador',
            Role.READONLY: 'Consulta',
        }
        roles = {
            code: Role.objects.get_or_create(
                role_name=code,
                defaults={'description': f'Rol de {label} del sistema SGR.'},
            )[0]
            for code, label in role_labels.items()
        }

        users_data = [
            ('admin@sgr.cl', Role.ADMIN, 0, 'Administrador', 'SGR'),
            ('coordinador@sgr.cl', Role.COORDINATOR, 1, 'Coordinador', 'SGR'),
            ('delegado@sgr.cl', Role.DELEGATE, 0, 'Delegado', 'SGR'),
            ('funcionario@sgr.cl', Role.FUNCTIONARY, 1, 'Funcionario', 'SGR'),
            ('verificador@sgr.cl', Role.VERIFIER, 0, 'Verificador', 'SGR'),
            ('consulta@sgr.cl', Role.READONLY, 1, 'Consulta', 'SGR'),
        ]
        user_model = get_user_model()
        functionaries_by_delegation = {
            delegation.pk: [] for delegation in delegations
        }

        for email, role_code, delegation_index, first_name, last_name in users_data:
            role = roles[role_code]
            delegation = delegations[delegation_index]
            position, _ = Position.objects.get_or_create(
                name=first_name,
                defaults={'default_role': role},
            )
            if position.default_role_id != role.pk:
                position.default_role = role
                position.save(update_fields=['default_role'])

            is_admin = role_code == Role.ADMIN
            user, _ = user_model.objects.get_or_create(
                username=email,
                defaults={
                    'email': email,
                    'first_name': first_name,
                    'last_name': last_name,
                    'is_staff': is_admin,
                    'is_superuser': is_admin,
                },
            )
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.is_staff = is_admin
            user.is_superuser = is_admin
            if not user.check_password(settings.SEED_USER_PASSWORD):
                user.set_password(settings.SEED_USER_PASSWORD)
            user.save()

            functionary, _ = Functionary.objects.get_or_create(
                user=user,
                defaults={
                    'delegation': delegation,
                    'position': position,
                    'names': first_name,
                    'lastnames': last_name,
                },
            )
            functionary.delegation = delegation
            functionary.position = position
            functionary.names = first_name
            functionary.lastnames = last_name
            functionary.save()
            FunctionaryRole.objects.get_or_create(
                functionary=functionary,
                role=role,
            )
            functionaries_by_delegation[delegation.pk].append(functionary)

        return delegations, functionaries_by_delegation

    @staticmethod
    def _create_attention_catalogs():
        attention_type_data = [
            ('ORI', 'Orientación', 'Orientación y consultas ciudadanas.'),
            ('SOC', 'Apoyo social', 'Solicitudes de apoyo social.'),
            ('COM', 'Servicios comunitarios', 'Servicios para la comunidad.'),
        ]
        attention_types = {}
        for code, name, description in attention_type_data:
            attention_types[code], _ = AttentionType.objects.get_or_create(
                code=code,
                defaults={'name': name, 'description': description},
            )

        subattention_data = {
            'ORI': [
                ('ORI-INFO', 'Información general'),
                ('ORI-TRAM', 'Orientación sobre trámites'),
            ],
            'SOC': [
                ('SOC-BEN', 'Beneficios sociales'),
                ('SOC-AYU', 'Ayuda social'),
            ],
            'COM': [
                ('COM-ESP', 'Uso de espacios comunitarios'),
                ('COM-ACT', 'Actividades comunitarias'),
            ],
        }
        sub_attentions_by_type = {}
        for type_code, entries in subattention_data.items():
            attention_type = attention_types[type_code]
            sub_attentions_by_type[attention_type.pk] = []
            for code, name in entries:
                sub_attention, _ = SubAttention.objects.get_or_create(
                    code=code,
                    defaults={
                        'name': name,
                        'attention_type': attention_type,
                        'description': f'Subatención de {attention_type.name}.',
                    },
                )
                sub_attentions_by_type[attention_type.pk].append(sub_attention)
        return attention_types, sub_attentions_by_type

    def _create_commitments(
        self,
        functionaries_by_delegation,
        delegations,
    ):
        measuring, _ = Measuring.objects.get_or_create(
            code='SEED-ATENCIONES',
            defaults={
                'service': 'Atención ciudadana de prueba',
                'measurable_item': 'Seguimiento de atenciones de prueba',
            },
        )
        seeded_commitments = list(
            Commitment.objects.filter(
                origin__contains='[Semilla SGR C#',
            )
        )
        existing_indices = self._seed_indices(
            (item.origin for item in seeded_commitments),
            r'\[Semilla SGR C#(\d{4})\]$',
        )
        objects = []
        today = timezone.localdate()
        for index in range(1, SEED_COUNTS['commitments'] + 1):
            if index in existing_indices:
                continue
            fake, rng = self._generators(2, index)
            delegation = rng.choice(delegations)
            functionary = rng.choice(functionaries_by_delegation[delegation.pk])
            marker = f'[Semilla SGR C#{index:04d}]'
            objects.append(
                Commitment(
                    origin=f'{fake.sentence(nb_words=5)[:75]} {marker}',
                    applic_name=fake.name()[:70],
                    territory=delegation.commune[:60],
                    commitment_date=today + timedelta(days=rng.randint(1, 180)),
                    support=fake.sentence(nb_words=8)[:200],
                    state=Commitment.State.PENDING,
                    observation=fake.paragraph(nb_sentences=2),
                    functionary=functionary,
                    measuring=measuring,
                )
            )
        Commitment.objects.bulk_create(objects, batch_size=500)
        seeded_commitments.extend(objects)
        return measuring, seeded_commitments

    def _create_attentions(
        self,
        delegations,
        functionaries_by_delegation,
        attention_types,
        sub_attentions_by_type,
    ):
        existing_descriptions = Attention.objects.filter(
            description__contains='[Semilla SGR #',
        ).values_list('description', flat=True)
        existing_indices = self._seed_indices(
            existing_descriptions,
            r'\[Semilla SGR #(\d{4})\]$',
        )
        objects = []
        for index in range(1, SEED_COUNTS['attentions'] + 1):
            if index in existing_indices:
                continue
            fake, rng = self._generators(1, index)
            attention_type = rng.choice(list(attention_types.values()))
            sub_attention = rng.choice(
                sub_attentions_by_type[attention_type.pk]
            )
            delegation = rng.choice(delegations)
            functionary = rng.choice(
                functionaries_by_delegation[delegation.pk]
            )
            marker = f'[Semilla SGR #{index:04d}]'
            objects.append(
                Attention(
                    requester_name=fake.name()[:150],
                    requester_contact=fake.phone_number()[:100],
                    attention_type=attention_type,
                    sub_attention=sub_attention,
                    description=f'{fake.paragraph()} {marker}',
                    delegation=delegation,
                    functionary=functionary,
                )
            )
        Attention.objects.bulk_create(objects, batch_size=500)
        return len(objects)

    def _create_activities(
        self,
        functionaries_by_delegation,
        measuring,
        commitments,
    ):
        existing_applications = Activity.objects.filter(
            application__contains='[Semilla SGR A#',
        ).values_list('application', flat=True)
        existing_indices = self._seed_indices(
            existing_applications,
            r'\[Semilla SGR A#(\d{4})\]$',
        )
        all_functionaries = [
            functionary
            for functionaries in functionaries_by_delegation.values()
            for functionary in functionaries
        ]
        objects = []
        today = timezone.localdate()
        for index in range(1, SEED_COUNTS['activities'] + 1):
            if index in existing_indices:
                continue
            fake, rng = self._generators(3, index)
            marker = f'[Semilla SGR A#{index:04d}]'
            objects.append(
                Activity(
                    date=today - timedelta(days=rng.randint(0, 730)),
                    application=f'{fake.sentence(nb_words=4)[:65]} {marker}',
                    taken_action=fake.paragraph(nb_sentences=3),
                    name_contact=fake.name()[:70],
                    telephone_contact=fake.phone_number()[:20],
                    state_validity=rng.choice(
                        [choice[0] for choice in Activity.STATE_CHOICES]
                    ),
                    functionary=rng.choice(all_functionaries),
                    measuring=measuring,
                    commitment=rng.choice(commitments) if commitments else None,
                    quantity=rng.randint(1, 8),
                    enters_pipe=rng.choice([True, False]),
                )
            )
        Activity.objects.bulk_create(objects, batch_size=500)
        return objects

    def _create_evidences(self, activities, functionaries_by_delegation):
        existing_names = Evidence.objects.filter(
            name__contains='[Semilla SGR E#',
        ).values_list('name', flat=True)
        existing_indices = self._seed_indices(
            existing_names,
            r'\[Semilla SGR E#(\d{4})\]$',
        )
        seeded_activities = list(
            Activity.objects.filter(application__contains='[Semilla SGR A#')
        )
        all_functionaries = [
            functionary
            for functionaries in functionaries_by_delegation.values()
            for functionary in functionaries
        ]
        objects = []
        for index in range(1, SEED_COUNTS['evidences'] + 1):
            if index in existing_indices:
                continue
            fake, rng = self._generators(4, index)
            marker = f'[Semilla SGR E#{index:04d}]'
            activity = rng.choice(seeded_activities)
            objects.append(
                Evidence(
                    name=f'Evidencia {index:04d} {marker}'[:50],
                    author=fake.name()[:50],
                    date_evidence=activity.date,
                    metadata=f'{fake.sentence()} {marker}'[:500],
                    file=SEED_EVIDENCE_FILE,
                    activity=activity,
                    functionary=rng.choice(all_functionaries),
                )
            )

        if objects and not default_storage.exists(SEED_EVIDENCE_FILE):
            default_storage.save(
                SEED_EVIDENCE_FILE,
                ContentFile(SEED_EVIDENCE_CONTENT),
            )
        Evidence.objects.bulk_create(objects, batch_size=500)
        return len(objects)

    @staticmethod
    def _seed_indices(values, pattern):
        indices = set()
        for value in values:
            match = re.search(pattern, value)
            if match:
                indices.add(int(match.group(1)))
        return indices

    @staticmethod
    def _generators(category, index):
        seed = SEED_VERSION + category * 1_000_000 + index
        fake = Faker('es_ES')
        fake.seed_instance(seed)
        return fake, random.Random(seed)

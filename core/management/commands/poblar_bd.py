import random
import re

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from faker import Faker

from atenciones.models import Attention, AttentionType, SubAttention
from personal.models import (
    Delegation,
    Functionary,
    FunctionaryRole,
    Position,
    Role,
)


class Command(BaseCommand):
    help = 'Crea catálogos, usuarios y 2.000 atenciones de prueba para SGR.'

    seed_prefix = '[Semilla SGR #'

    def handle(self, *args, **options):
        fake = Faker('es_ES')
        user_model = get_user_model()

        with transaction.atomic():
            self.stdout.write('Creando catálogos...')

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

            roles_data = [
                (Role.ADMIN, 'Administrador'),
                (Role.COORDINATOR, 'Coordinador'),
                (Role.DELEGATE, 'Delegado'),
                (Role.FUNCTIONARY, 'Funcionario'),
                (Role.VERIFIER, 'Verificador'),
                (Role.READONLY, 'Consulta'),
            ]
            roles = {}
            for role_code, role_label in roles_data:
                roles[role_code], _ = Role.objects.get_or_create(
                    role_name=role_code,
                    defaults={'description': f'Rol de {role_label} del sistema SGR.'},
                )

            attention_types_data = [
                ('ORI', 'Orientación', 'Orientación y consultas ciudadanas.'),
                ('SOC', 'Apoyo social', 'Solicitudes de apoyo social.'),
                ('COM', 'Servicios comunitarios', 'Servicios para la comunidad.'),
            ]
            attention_types = {}
            for code, name, description in attention_types_data:
                attention_types[code], _ = AttentionType.objects.get_or_create(
                    code=code,
                    defaults={'name': name, 'description': description},
                )

            sub_attentions_data = {
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
            for type_code, subattentions in sub_attentions_data.items():
                attention_type = attention_types[type_code]
                sub_attentions_by_type[attention_type.pk] = []
                for code, name in subattentions:
                    sub_attention, _ = SubAttention.objects.get_or_create(
                        code=code,
                        defaults={
                            'name': name,
                            'attention_type': attention_type,
                            'description': f'Subatención de {attention_type.name}.',
                        },
                    )
                    sub_attentions_by_type[attention_type.pk].append(sub_attention)

            self.stdout.write('Creando usuarios...')

            users_data = [
                ('admin@sgr.cl', Role.ADMIN, 0, 'Administrador', 'SGR'),
                ('coordinador@sgr.cl', Role.COORDINATOR, 1, 'Coordinador', 'SGR'),
                ('delegado@sgr.cl', Role.DELEGATE, 0, 'Delegado', 'SGR'),
                ('funcionario@sgr.cl', Role.FUNCTIONARY, 1, 'Funcionario', 'SGR'),
                ('verificador@sgr.cl', Role.VERIFIER, 0, 'Verificador', 'SGR'),
                ('consulta@sgr.cl', Role.READONLY, 1, 'Consulta', 'SGR'),
            ]
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
                if user.email != email:
                    user.email = email
                if not user.check_password('Inacap2026'):
                    user.set_password('Inacap2026')
                if is_admin:
                    user.is_staff = True
                    user.is_superuser = True
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
                functionary.save()
                FunctionaryRole.objects.get_or_create(
                    functionary=functionary,
                    role=role,
                )
                functionaries_by_delegation[delegation.pk].append(functionary)

            self.stdout.write('Generando 2.000 atenciones...')

            # El marcador estable permite reconocer cada semilla al repetir el comando.
            existing_seed_indices = set()
            seeded_descriptions = Attention.objects.filter(
                description__contains=self.seed_prefix,
            ).values_list('description', flat=True)
            for description in seeded_descriptions:
                match = re.search(r'\[Semilla SGR #(\d{4})\]$', description)
                if match:
                    existing_seed_indices.add(int(match.group(1)))

            created_count = 0
            for seed_index in range(1, 2001):
                if seed_index in existing_seed_indices:
                    continue

                # La subatención y el funcionario deben corresponder a sus FK relacionadas.
                attention_type = random.choice(list(attention_types.values()))
                sub_attention = random.choice(
                    sub_attentions_by_type[attention_type.pk]
                )
                delegation = random.choice(delegations)
                responsible_functionary = random.choice(
                    functionaries_by_delegation[delegation.pk]
                )
                description = (
                    f'{fake.paragraph()} '
                    f'[Semilla SGR #{seed_index:04d}]'
                )
                Attention.objects.create(
                    requester_name=fake.name(),
                    requester_contact=fake.phone_number(),
                    attention_type=attention_type,
                    sub_attention=sub_attention,
                    description=description,
                    delegation=delegation,
                    functionary=responsible_functionary,
                )
                created_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f'Proceso finalizado. Se crearon {created_count} atenciones '
                    'nuevas; las semillas existentes se conservaron.'
                )
            )

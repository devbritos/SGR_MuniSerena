from django.core.exceptions import ValidationError


def validate_person_name(value):
    if any(character.isdigit() for character in value):
        raise ValidationError('Los nombres y apellidos no deben contener números.')

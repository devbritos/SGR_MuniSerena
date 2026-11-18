import re

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


MAX_EVENT_IMAGE_BYTES = 5 * 1024 * 1024
MAX_EVENT_IMAGE_PIXELS = 20_000_000
EVENT_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}


def normalize_chilean_rut(value):
    compact = re.sub(r'[.\s-]', '', (value or '').upper())
    if not re.fullmatch(r'\d{6,8}[0-9K]', compact):
        raise ValidationError('Ingresa un RUT chileno válido.')

    body, supplied_digit = compact[:-1], compact[-1]
    factor = 2
    total = 0
    for digit in reversed(body):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1

    remainder = 11 - total % 11
    expected_digit = (
        '0' if remainder == 11 else 'K' if remainder == 10 else str(remainder)
    )
    if supplied_digit != expected_digit:
        raise ValidationError('El dígito verificador del RUT no es válido.')

    return f'{int(body)}-{expected_digit}'


def validate_event_image(upload):
    if upload.size > MAX_EVENT_IMAGE_BYTES:
        raise ValidationError('La imagen del evento no puede superar 5 MiB.')

    position = upload.tell()
    try:
        with Image.open(upload) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
    except (
        Image.DecompressionBombError,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ) as error:
        raise ValidationError(
            'Selecciona una imagen JPG, PNG o WebP válida.'
        ) from error
    finally:
        upload.seek(position)

    if image_format not in EVENT_IMAGE_FORMATS:
        raise ValidationError('La imagen debe ser JPG, PNG o WebP.')
    if width * height > MAX_EVENT_IMAGE_PIXELS:
        raise ValidationError('La imagen no puede superar 20 megapíxeles.')

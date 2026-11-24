from io import BytesIO

from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError


MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024
MAX_PROFILE_PHOTO_SOURCE_BYTES = 10 * 1024 * 1024
PROFILE_PHOTO_OUTPUT_DIMENSION = 512
MAX_PROFILE_PHOTO_PIXELS = 40_000_000
PROFILE_PHOTO_FORMATS = {'JPEG', 'PNG'}


def validate_person_name(value):
    if any(character.isdigit() for character in value):
        raise ValidationError('Los nombres y apellidos no deben contener números.')


def validate_profile_photo(data, expected_format=None, require_square=True, max_bytes=MAX_PROFILE_PHOTO_BYTES):
    if not isinstance(data, bytes):
        source = data
        position = source.tell()
        try:
            source.seek(0)
            data = source.read(max_bytes + 1)
        finally:
            source.seek(position)

    if len(data) > max_bytes:
        raise ValidationError(f'La imagen no puede superar {max_bytes // (1024 * 1024)} MiB.')

    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
        if image_format not in PROFILE_PHOTO_FORMATS:
            raise ValidationError('La foto debe estar en formato JPG o PNG.')
        if expected_format and image_format != expected_format:
            raise ValidationError('El formato declarado no coincide con la imagen.')
        if width * height > MAX_PROFILE_PHOTO_PIXELS:
            raise ValidationError('La imagen supera 40 megapíxeles. Selecciona una versión de menor resolución.')

        with Image.open(BytesIO(data)) as image:
            image.load()
            image = ImageOps.exif_transpose(image)
            if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                rgba = image.convert('RGBA')
                background = Image.new('RGB', rgba.size, 'white')
                background.paste(rgba, mask=rgba.getchannel('A'))
                image = background
            else:
                image = image.convert('RGB')
            if require_square:
                image = ImageOps.fit(image, (PROFILE_PHOTO_OUTPUT_DIMENSION, PROFILE_PHOTO_OUTPUT_DIMENSION), method=Image.Resampling.LANCZOS)
            else:
                image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format='JPEG', quality=90, optimize=True)
    except ValidationError:
        raise
    except (
        Image.DecompressionBombError,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ) as exc:
        raise ValidationError(
            'No se pudo validar la imagen. Selecciona un archivo JPG o PNG válido.'
        ) from exc

    validated_data = output.getvalue()
    if len(validated_data) > MAX_PROFILE_PHOTO_BYTES:
        raise ValidationError('La imagen no puede superar 2 MiB.')
    return validated_data

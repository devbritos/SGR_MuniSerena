from io import BytesIO

from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError


MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024
MIN_PROFILE_PHOTO_DIMENSION = 64
MAX_PROFILE_PHOTO_DIMENSION = 1024
MAX_PROFILE_PHOTO_PIXELS = 20_000_000
PROFILE_PHOTO_FORMATS = {'JPEG', 'PNG'}


def validate_person_name(value):
    if any(character.isdigit() for character in value):
        raise ValidationError('Los nombres y apellidos no deben contener números.')


def validate_profile_photo(data, expected_format=None, require_square=True):
    if not isinstance(data, bytes):
        position = data.tell()
        data = data.read()
        data.seek(position)

    if len(data) > MAX_PROFILE_PHOTO_BYTES:
        raise ValidationError('La imagen no puede superar 2 MiB.')

    try:
        with Image.open(BytesIO(data)) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
        if image_format not in PROFILE_PHOTO_FORMATS:
            raise ValidationError('La foto debe estar en formato JPG o PNG.')
        if expected_format and image_format != expected_format:
            raise ValidationError('El formato declarado no coincide con la imagen.')
        if require_square and width != height:
            raise ValidationError('La foto recortada debe tener formato cuadrado.')
        if not (
            MIN_PROFILE_PHOTO_DIMENSION <= width <= MAX_PROFILE_PHOTO_DIMENSION
            and MIN_PROFILE_PHOTO_DIMENSION
            <= height
            <= MAX_PROFILE_PHOTO_DIMENSION
        ):
            raise ValidationError(
                'La imagen debe medir entre 64 y 1024 píxeles por lado.'
            )
        if width * height > MAX_PROFILE_PHOTO_PIXELS:
            raise ValidationError('La imagen supera la resolución permitida.')

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

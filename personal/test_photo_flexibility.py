from io import BytesIO
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image
from .forms import ProfilePhotoForm
from .validators import validate_profile_photo, MAX_PROFILE_PHOTO_SOURCE_BYTES


class FlexibleProfilePhotoTests(SimpleTestCase):
    @staticmethod
    def source(size, color='red', exif=None):
        image = Image.new('RGB', size, color)
        output = BytesIO()
        image.save(output, format='JPEG', **({'exif': exif} if exif else {}))
        return output.getvalue()

    def test_phone_portrait_landscape_and_small_photos_are_resized(self):
        for size in ((4000, 3000), (3000, 4000), (1600, 900), (48, 32)):
            with self.subTest(size=size):
                data = validate_profile_photo(self.source(size))
                with Image.open(BytesIO(data)) as image:
                    self.assertEqual(image.size, (512, 512))
                    self.assertEqual(image.format, 'JPEG')

    def test_source_validation_accepts_more_than_twenty_megapixels(self):
        data = validate_profile_photo(self.source((6000, 4000)), require_square=False, max_bytes=MAX_PROFILE_PHOTO_SOURCE_BYTES)
        with Image.open(BytesIO(data)) as image:
            self.assertEqual(image.width, 1024)
            self.assertLess(image.height, image.width)

    def test_upload_without_browser_crop_is_automatically_fitted(self):
        upload = SimpleUploadedFile('phone.jpg', self.source((4032, 3024)), content_type='image/jpeg')
        form = ProfilePhotoForm(data={}, files={'photo_upload': upload})
        self.assertTrue(form.is_valid(), form.errors)
        with Image.open(BytesIO(form.cleaned_data['cropped_image'])) as image:
            self.assertEqual(image.size, (512, 512))

    def test_upload_over_old_two_mib_limit_is_allowed(self):
        # A valid JPEG with harmless trailing padding exercises the source-byte
        # limit without relying on random compression ratios.
        payload = self.source((1800, 1200)) + b'\0' * (3 * 1024 * 1024)
        upload = SimpleUploadedFile('larger.jpg', payload, content_type='image/jpeg')
        form = ProfilePhotoForm(data={}, files={'photo_upload': upload})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertLess(len(form.cleaned_data['cropped_image']), 2 * 1024 * 1024)

    def test_uploaded_file_cursor_is_preserved(self):
        stream = BytesIO(self.source((2000, 1000)))
        stream.seek(17)
        validate_profile_photo(stream)
        self.assertEqual(stream.tell(), 17)

    def test_exif_orientation_is_applied_before_resizing(self):
        exif = Image.Exif()
        exif[274] = 6
        data = validate_profile_photo(self.source((1600, 800), exif=exif), require_square=False)
        with Image.open(BytesIO(data)) as image:
            self.assertEqual(image.size, (512, 1024))

    def test_resolution_limit_remains_enforced(self):
        with self.assertRaisesMessage(ValidationError, '40 megapíxeles'):
            validate_profile_photo(self.source((8000, 6000)))

    def test_corrupt_upload_is_still_rejected(self):
        with self.assertRaises(ValidationError):
            validate_profile_photo(b'not an image')

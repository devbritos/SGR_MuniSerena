import re
import unicodedata

from django.db import migrations


CODE_PATTERN = re.compile(r'^[A-Z]{3}\d+$', re.IGNORECASE)


def abbreviation(name):
    normalized_name = unicodedata.normalize('NFKD', name)
    ascii_name = normalized_name.encode('ascii', 'ignore').decode('ascii')
    words = re.findall(r'[A-Za-z]+', ascii_name)
    words = [word for word in words if word.casefold() != 'delegacion']
    if not words:
        words = ['DEL']
    if len(words) > 1:
        return (words[0][:2] + words[1][:1]).upper().ljust(3, 'X')[:3]
    return words[0][:3].upper().ljust(3, 'X')


def normalize_delegation_codes(apps, schema_editor):
    Delegation = apps.get_model('personal', 'Delegation')
    database = schema_editor.connection.alias
    delegations = list(
        Delegation.objects.using(database).order_by('pk').values(
            'pk', 'name', 'code'
        )
    )
    used_codes = {
        delegation['code'].upper()
        for delegation in delegations
        if delegation['code'] and CODE_PATTERN.fullmatch(delegation['code'])
    }

    for delegation in delegations:
        code = delegation['code']
        if code and CODE_PATTERN.fullmatch(code):
            continue

        prefix = abbreviation(delegation['name'])
        number = 1
        candidate = f'{prefix}{number}'
        while candidate in used_codes:
            number += 1
            candidate = f'{prefix}{number}'

        Delegation.objects.using(database).filter(pk=delegation['pk']).update(
            code=candidate
        )
        used_codes.add(candidate)


class Migration(migrations.Migration):

    dependencies = [
        ('personal', '0010_delegationchatmessage'),
    ]

    operations = [
        migrations.RunPython(
            normalize_delegation_codes,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('atenciones', '0002_attentionfollowup_attention_closed_at_and_more'),
        ('organizations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='attention',
            name='organization',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='attentions',
                to='organizations.organization',
                verbose_name='Organización comunitaria',
            ),
        ),
    ]

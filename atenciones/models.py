from django.core.exceptions import ValidationError
from django.db import models

from core.models import BaseModel


class AttentionType(BaseModel):
    code = models.CharField(max_length=30, unique=True, verbose_name='Código')
    name = models.CharField(max_length=100, unique=True, verbose_name='Nombre')
    description = models.TextField(blank=True, verbose_name='Descripción')
    is_active = models.BooleanField(default=True, verbose_name='Activo')

    class Meta:
        ordering = ['name']
        verbose_name = 'Tipo de atención'
        verbose_name_plural = 'Tipos de atención'

    def __str__(self):
        return f'{self.code} - {self.name}'


class SubAttention(BaseModel):
    code = models.CharField(max_length=30, unique=True, verbose_name='Código')
    name = models.CharField(max_length=100, verbose_name='Nombre')
    description = models.TextField(blank=True, verbose_name='Descripción')
    attention_type = models.ForeignKey(
        AttentionType,
        on_delete=models.PROTECT,
        related_name='sub_attentions',
        verbose_name='Tipo de atención',
    )
    is_active = models.BooleanField(default=True, verbose_name='Activo')

    class Meta:
        ordering = ['attention_type__name', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['attention_type', 'name'],
                name='unique_subattention_name_per_type',
            )
        ]
        verbose_name = 'Subatención'
        verbose_name_plural = 'Subatenciones'

    def __str__(self):
        return f'{self.attention_type.name} - {self.name}'


class Attention(BaseModel):
    requester_name = models.CharField(
        max_length=150,
        verbose_name='Nombre del solicitante',
    )
    requester_contact = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Contacto del solicitante',
    )
    attention_type = models.ForeignKey(
        AttentionType,
        on_delete=models.PROTECT,
        related_name='attentions',
        verbose_name='Tipo de atención',
    )
    sub_attention = models.ForeignKey(
        SubAttention,
        on_delete=models.PROTECT,
        related_name='attentions',
        verbose_name='Subatención',
    )
    description = models.TextField(verbose_name='Descripción de la atención')
    delegation = models.ForeignKey(
        'personal.Delegation',
        on_delete=models.PROTECT,
        related_name='attentions',
        verbose_name='Delegación',
    )
    functionary = models.ForeignKey(
        'personal.Functionary',
        on_delete=models.PROTECT,
        related_name='attentions',
        verbose_name='Usuario responsable',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Atención ciudadana'
        verbose_name_plural = 'Atenciones ciudadanas'

    def clean(self):
        super().clean()
        if (
            self.sub_attention_id
            and self.attention_type_id
            and self.sub_attention.attention_type_id != self.attention_type_id
        ):
            raise ValidationError({
                'sub_attention': (
                    'La subatención debe pertenecer al tipo de atención seleccionado.'
                )
            })
        if (
            self.functionary_id
            and self.delegation_id
            and self.functionary.delegation_id != self.delegation_id
        ):
            raise ValidationError({
                'delegation': 'La delegación debe coincidir con la del funcionario.'
            })

    def __str__(self):
        return f'{self.requester_name} - {self.attention_type.name}'

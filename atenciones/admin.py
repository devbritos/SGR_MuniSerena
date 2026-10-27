from django.contrib import admin

from .models import Attention, AttentionType, SubAttention


admin.site.register(Attention)
admin.site.register(AttentionType)
admin.site.register(SubAttention)

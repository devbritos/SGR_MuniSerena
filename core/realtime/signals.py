import logging

from asgiref.sync import async_to_sync
from django.apps import apps
from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from redis.exceptions import RedisError


logger = logging.getLogger(__name__)

BUSINESS_APP_LABELS = {
    'activities',
    'agenda',
    'atenciones',
    'configuration',
    'personal',
}
GROUP_NAME = 'sgr_data_updates'


def _notify_clients():
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    try:
        async_to_sync(channel_layer.group_send)(
            GROUP_NAME,
            {'type': 'data.changed'},
        )
    except RedisError:
        logger.exception(
            'No se pudo notificar el cambio por Redis; los datos ya quedaron '
            'guardados y los clientes no recibieron la actualización en vivo.'
        )


def schedule_data_update(using='default'):
    transaction.on_commit(_notify_clients, using=using)


def _model_changed(sender, using, **kwargs):
    if kwargs.get('raw'):
        return
    schedule_data_update(using)


def _relation_changed(sender, action, using, **kwargs):
    if action in {'post_add', 'post_remove', 'post_clear'}:
        schedule_data_update(using)


def connect_model_signals():
    through_models = set()
    for model in apps.get_models():
        if model._meta.app_label not in BUSINESS_APP_LABELS:
            continue

        label = model._meta.label_lower
        post_save.connect(
            _model_changed,
            sender=model,
            dispatch_uid=f'core.live_updates.save.{label}',
        )
        post_delete.connect(
            _model_changed,
            sender=model,
            dispatch_uid=f'core.live_updates.delete.{label}',
        )

        for field in model._meta.many_to_many:
            through_models.add(field.remote_field.through)

    for through_model in through_models:
        if through_model._meta.app_label in BUSINESS_APP_LABELS:
            m2m_changed.connect(
                _relation_changed,
                sender=through_model,
                dispatch_uid=(
                    f'core.live_updates.m2m.{through_model._meta.label_lower}'
                ),
            )

import math
from typing import Iterable

from django import template
from django.db.models import Model, QuerySet
from django.template.context import Context as Context
from django.template.loader import get_template
from django.urls import reverse

register = template.Library()


@register.filter
def get_verbose_name(obj, plural=False):
    assert hasattr(obj, "_meta") or isinstance(obj, QuerySet)
    if isinstance(obj, Model):
        meta = obj._meta

    elif isinstance(obj, QuerySet):
        meta = obj.model._meta

    else:
        meta = obj._meta.model._meta

    return (meta.verbose_name_plural if plural else meta.verbose_name).title()


@register.filter
def dict_get(dictionary, key):
    return dictionary.get(key)

import contextlib
import json
import math
from typing import Iterable
from urllib.parse import urlencode

from django import template
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Model, Q, QuerySet
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.utils.safestring import mark_safe

from flex_report.app_settings import app_settings
from flex_report.utils import (
    get_column_cell,
    get_model_field,
    field_to_db_field,
    get_related_property,
)

register = template.Library()


@register.filter(name="enumerate")
def enum(iterable: Iterable):
    return enumerate(iterable)


@register.inclusion_tag("flex_report/pagination.html", takes_context=True)
def show_pagination(
    context, pagination_context=None, *, link_attributes=None, scroll_tag=None
):
    return {
        "request": context["request"],
        "link_attributes": link_attributes,
        "scroll_tag": scroll_tag,
        **(pagination_context or context["pagination"]),
    }


@register.filter(name="range")
def get_range(value):
    return range(value)


@register.filter
def is_editor(user):
    group, _ = Group.objects.get_or_create(name=app_settings.EDITORS_GROUP_NAME)
    return user.groups.filter(pk=group.pk).exists() or user.is_superuser


@register.filter
def has_report_access(user, obj):
    return obj._meta.model.objects.filter(
        Q(is_superuser=True)
        | Q(creator=user)
        | Q(users=user)
        | Q(groups__in=user.groups.all())
        | (Q(groups__isnull=True) & Q(users__isnull=True))
    )


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


@register.filter
def get_centered_range(current_page, num_pages):
    max_show_count = 5
    max_count_center = int(max_show_count / 2)
    max_show_count_ceil = math.ceil(max_show_count / 2)
    start = 1
    end = num_pages

    if current_page < max_show_count_ceil < end:
        end = max_show_count if num_pages > max_show_count else num_pages
    elif abs(current_page - num_pages) >= max_show_count_ceil:
        start = current_page - max_count_center
        end = current_page + max_count_center
    elif end > max_show_count:
        start = end - max_show_count

    return range(start, end + 1)


@register.simple_tag
def query_transform(request, **query_string):
    updated = request.GET.copy()
    for k, v in query_string.items():
        updated[k] = v
    return updated.urlencode()


@register.simple_tag(takes_context=True)
def dynamic_query_transform(context, context_name, **kwargs):
    # It's bug. in some contexts dictionary in context is unpacked and we don't need context_name,
    # but some contexts receive original dictionary and passed contexts
    current_context = context.get(context_name) or context
    for k in list(kwargs):
        kwargs[current_context[f"{k}_keyword"]] = kwargs.pop(k)
    return query_transform(context["request"], **kwargs)


def is_row_value_valid(f, v):
    return v or isinstance(f, models.BooleanField) or v == 0


@register.filter
def get_column_verbose_name(obj, column):
    lookup_exprs = list(map(lambda i: f"__{i}", ["in"]))

    for lookup in filter(lambda i: column.endswith(i), lookup_exprs):
        column = column.rstrip(lookup)

    field_col = getattr(field_to_db_field(obj, column), "verbose_name", False)
    if field_col:
        return mark_safe(field_col or column.replace("_", "").title())

    if (field := getattr(obj, column, False)) and hasattr(field, "fget"):
        field_col = field.fget.verbose_name
    elif field := get_related_property(obj, column):
        field_col = field.fget.verbose_name

    return mark_safe(field_col or column.replace("_", " ").title())


@register.filter
def get_columns_verbose_names(cols: Iterable, obj):
    return list(map(lambda c: get_column_verbose_name(obj, c), cols))


@register.filter
def get_row_value(obj, column):
    field = get_model_field(obj, column)
    value = get_column_cell(obj, column, absolute_url=False)

    tag = app_settings.DATA_TAGS.get(
        type(field),
        app_settings.DATA_TAGS["default"],
    )
    return mark_safe(tag(value) if is_row_value_valid(field, value) else "&mdash;")


@register.inclusion_tag("flex_report/view.html", takes_context=True)
def show_page_report(context):
    return context


@register.simple_tag
def get_report_button_fields(record, button):
    return json.dumps(
        {f: get_column_cell(record, f) for f in button.exposed_fields},
        cls=DjangoJSONEncoder,
    )


@register.simple_tag
def get_report_button_url(record, button):
    url = ""
    url_kwargs = {k: getattr(record, v, v) for k, v in button.url_kwargs.items()}

    with contextlib.suppress(NoReverseMatch):
        url = reverse(
            button.url_name,
            kwargs=url_kwargs
            | {"ct_pk": ContentType.objects.get_for_model(record._meta.model).pk},
        )

    with contextlib.suppress(NoReverseMatch):
        url = reverse(
            button.url_name,
            kwargs=url_kwargs,
        )

    with contextlib.suppress(NoReverseMatch):
        url = reverse(button.url_name)

    url += f"?{urlencode({k: getattr(record, v, v) for k, v in button.query_strings.items()})}"

    return url.strip("?") or "#"

import contextlib
import json
from urllib.parse import urlencode

import jdatetime
from apps.report.constants import REPORT_TEMPLATE_HTML_TAGS
from apps.report.utils import get_column_cell, get_model_field

from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.utils.safestring import mark_safe

from ..utils import field_to_db_field, get_model_field

register = template.Library()


def is_row_value_valid(f, v):
    return v or isinstance(f, models.BooleanField) or v == 0


@register.filter
def get_verbose_name(obj, column):
    return mark_safe(
        getattr(
            field_to_db_field(obj, column), "verbose_name", column.replace("_", " ")
        )
    )


@register.filter
def get_row_value(obj, column):
    field = get_model_field(obj, column)
    value = get_column_cell(obj, column, absolute_url=False)
    tag = REPORT_TEMPLATE_HTML_TAGS.get(
        type(field),
        REPORT_TEMPLATE_HTML_TAGS["default"],
    )
    return mark_safe(tag(value) if is_row_value_valid(field, value) else "")


@register.inclusion_tag("report/view.html", takes_context=True)
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
    url_kwargs = {k: getattr(record, v, v) for k, v in button.url_kwargs.items()}
    with contextlib.suppress(NoReverseMatch):
        return reverse(
            button.url_name,
            kwargs=url_kwargs,
        )

    with contextlib.suppress(NoReverseMatch):
        return reverse(button.url_name) + f"?{urlencode(url_kwargs)}"

    return "#"

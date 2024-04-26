import copy
import inspect
import contextlib

import django.db.models.options as options
from django_filters import utils as django_filter_utils
from django.utils.translation import gettext as _

from ._version import get_version
from .constants import (
    META_REPORT_KEY,
    BaseExportFormat,
    ReportModel,
    BaseDynamicField,
    DynamicSubField,
)

options.DEFAULT_NAMES = options.DEFAULT_NAMES + (META_REPORT_KEY,)


export_format = BaseExportFormat
report_model = ReportModel
dynamic_field = BaseDynamicField


__version__ = get_version()
__all__ = [
    "ReportModel",
    "report_model",
    "BaseExportFormat",
    "export_format",
    "BaseDynamicField",
    "DynamicSubField",
    "dynamic_field",
]


_verbose_field_name = copy.deepcopy(django_filter_utils.verbose_field_name)


def verbose_field_name(model, field_name):
    from .utils import get_model_property, nested_getattr

    verbose_field_name_source = (
        inspect.getsource(_verbose_field_name)
        .replace('return " ".join(names)', "return names")
        .replace("verbose_field_name", "override_verbose_field_name")
    )
    exec(verbose_field_name_source, django_filter_utils.__dict__, globals())

    if field := get_model_property(model, field_name):
        names = [
            nested_getattr(
                field, "fget.verbose_name", getattr(field, "__name__", "[invalid name]")
            )
        ]
    else:
        names = globals()["override_verbose_field_name"](model, field_name)

    return " ".join(map(_, names))


with contextlib.suppress(ImportError):
    if inspect.getsource(_verbose_field_name) != inspect.getsource(verbose_field_name):
        django_filter_utils.verbose_field_name = verbose_field_name

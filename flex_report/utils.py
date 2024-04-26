import contextlib
import csv
import datetime
import io
import json
import re
from django.utils.translation import override
from collections import OrderedDict
from decimal import Decimal
from django.db.models import QuerySet
from functools import lru_cache, reduce
from importlib import import_module
from itertools import chain
from operator import attrgetter, methodcaller, and_, or_
from typing import List
from phonenumber_field.modelfields import PhoneNumberField
import jdatetime
import pandas as pd
import xlwt
from dateparser.calendars.jalali import JalaliCalendar
from django import forms
import ast
from django.db.models import Q
from logging import getLogger
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.fields.related import ForeignObjectRel, RelatedField
from django.urls import URLPattern, URLResolver, get_resolver
from django_filters import FilterSet
from django_filters.constants import ALL_FIELDS
from django_filters.utils import LOOKUP_SEP, get_all_model_fields, get_model_field
from djmoney.models import fields as money_fields
from djmoney.money import Money
from phonenumber_field.phonenumber import PhoneNumber

from flex_report import BaseExportFormat, ReportModel, export_format, dynamic_field
from flex_report.fields import FieldFileAbsoluteURL

from .app_settings import app_settings
from .constants import (
    REPORT_CELL_STYLE_MAP,
    REPORT_CUSTOM_FIELDS_KEY,
    REPORT_EXCULDE_KEY,
    REPORT_FIELDS_KEY,
    FieldTypes,
    DynamicSubField,
)


logger = getLogger(__name__)


def nested_getattr(obj, attr, *args, sep="."):
    def _getattr(obj, attr):
        return getattr(obj, attr, *args)

    return reduce(_getattr, [obj] + attr.split(sep))


def encode_str_dict(d: dict):
    return " ".join([f'{k}="{v}"' for k, v in d.items()])


def tokenize_kwargs(string: str):
    return dict(
        [
            (i[0], i[1].strip('"').strip("'"))
            for i in map(lambda i: i.split("="), string.split('" '))
        ]
    )


def increment_string_suffix(string):
    r = re.subn(
        r"[0-9]+$",
        lambda x: f"{str(int(x.group()) + 1).zfill(len(x.group()))}",
        string,
    )
    return r[0] if r[1] else f"{string}1"


def list_index_safe(l, v, default=None):
    with contextlib.suppress(ValueError):
        return l.index(v)
    return default


def get_all_subclasses(class_):
    subclasses = set()
    work = [class_]
    while work:
        parent = work.pop()
        for child in parent.__subclasses__():
            if child not in subclasses:
                subclasses.add(child)
                work.append(child)
    return subclasses


def get_urlpatterns(app_name: str) -> List[str]:
    try:
        apps.get_app_config(app_name)  # noqa: F821
    except LookupError:
        return []

    urls_module = import_module(f"{app_name}.urls")
    url_names = []
    urlpatterns, root_namespace = urls_module.urlpatterns, urls_module.app_name

    def get_nested_urlpatterns(
        patterns: list | URLResolver, namespace: str = root_namespace
    ):
        if isinstance(patterns, URLResolver):
            nested_patterns = get_nested_urlpatterns(
                patterns.url_patterns, f"{root_namespace}:{patterns.namespace}"
            )
        else:
            nested_patterns = [f"{namespace}:{i.name}" for i in patterns]
        return nested_patterns

    for pattern in urlpatterns:
        if isinstance(pattern, URLResolver):
            url_names.extend(get_nested_urlpatterns(pattern))
        else:
            url_names.append(f"{root_namespace}:{pattern.name}")

    return url_names


def get_project_urls():
    def getter(urls, patterns=None, namespaces=None):
        patterns = [] if patterns is None else patterns
        namespaces = [] if namespaces is None else namespaces

        if not urls:
            return
        l = urls[0]
        if isinstance(l, URLPattern):
            yield patterns + [str(l.pattern)], namespaces + [l.name], l.callback
        elif isinstance(l, URLResolver):
            yield from getter(
                l.url_patterns, patterns + [str(l.pattern)], namespaces + [l.namespace]
            )
        yield from getter(urls[1:], patterns, namespaces)

    for pattern in getter(get_resolver().url_patterns):
        url, names, view = pattern
        names = [n for n in names if n is not None]
        if all(names):
            yield {
                "names": names,
                "view_name": ":".join(names),
                "url": "".join(url),
                "view": view,
            }


def get_view_name_url(name):
    return next((u["url"] for u in get_project_urls() if name == u["view_name"]), None)


def get_model_method_result(model, key):
    """
    Checks if a model has the given key defined as a method
    and checks if its returned value is a populated list, and returns it.
    """
    return (callable((method := getattr(model, key, None))) and method()) or []


@lru_cache(maxsize=None)
def get_report_models():
    """
    Returns a dict where the keys are the model names, and the values
    are the model classes that have 'use_for_report' marked from registered apps.
    """
    models = ReportModel.models
    return ContentType.objects.get_for_models(*models)


def fields_to_field_name(fields_lookups):
    """
    gets a dict that the keys are the name of fields or the field itself,
    and the values are a list of lookup expressions,
    and returns a dict where the keys are the name of fields
    and the values are the list of lookup expressions.
    """
    return {
        f if isinstance(f, str) else get_field_name(f): l
        for f, l in fields_lookups.items()
    }


def field_to_db_field(model, field):
    """Takes a model and a field name, and returns the field object of that field name."""
    return (
        get_model_field(model, field)
        if isinstance(field, str)
        else (getattr(field, "field", None) or field)
    )


def get_model_fields(model, *, as_filter=False, fields_key, excludes_key):
    """
    takes in a model and the method names under whose name the list of
    field-names included and excluded used for filtering is defined,
    and returns a tuple where the first element is a set of included field-names,
    and the second element is a set of excluded field names.
    """
    raw_fields = get_model_method_result(model, fields_key)
    raw_exclude = get_model_method_result(model, excludes_key)

    # append all model fields if needed
    if ALL_FIELDS in (raw_fields or []):
        raw_fields.remove(ALL_FIELDS)
        raw_fields.extend(get_all_model_fields(model))

    # validate fields that may not acceptable by django_filters.FilterSet
    # if not skip it and don't add it to fields
    fields = {f for f in raw_fields if is_field_valid(model, f, as_filter=as_filter)}
    exclude = {f for f in raw_exclude if is_field_valid(model, f, as_filter=as_filter)}

    return fields, exclude


@lru_cache(maxsize=None)
def get_model_filters(model):
    """
    Takes in a model and returns a list of included and excluded field names used for filtering.
    """
    fields, exclude = get_model_fields(
        model,
        as_filter=True,
        fields_key=REPORT_FIELDS_KEY,
        excludes_key=REPORT_EXCULDE_KEY,
    )
    return list(fields), list(exclude)


def get_model_custom_fields(model):
    """"""
    return (
        hasattr(model, REPORT_CUSTOM_FIELDS_KEY)
        and (custom_fields := getattr(model, REPORT_CUSTOM_FIELDS_KEY))
        and callable(custom_fields)
        and custom_fields()
        or None
    )


def get_model_custom_field_value(model, field_name):
    """"""
    custom_fields = get_model_custom_fields(model)
    return custom_fields[get_model_property(model, field_name)]


def get_model_columns(model, db_only=False):
    from flex_report.models import Column

    model_content_type = ContentType.objects.get_for_model(model)
    columns = (
        Column.objects.select_related("model")
        .filter(model=model_content_type)
        .values_list("title", "id")
    )
    if db_only:
        columns = columns.filter(searchable=True)
    return {col_id: title for title, col_id in columns.values_list("title", "id")}


def get_choice_field_choices(model, column):
    """
    Takes in a column object and returns the choices of the field of the column.
    """
    if isinstance(column, str):
        column = get_model_field(model, column)

    return getattr(column, "choices", [])


def get_column_type(model, column):
    """
    takes in a model and a column name, and returns the column type.
    currently the possible types are: field, property, and custom.
    """
    if column in dynamic_field.fields:
        return FieldTypes.dynamic

    field = get_model_field(model, column)
    if field:
        return FieldTypes.field

    field = get_model_property(model, column)

    if isinstance(field, property):
        return FieldTypes.property

    return None


def get_fields_lookups(model, fields):
    """
    Takes in a model and a list of fields, and returns a dict where the keys are the field names,
    and the values are a list of lookup-expression used for them.
    """
    db_fields = {f: field_to_db_field(model, f) for f in fields}
    fields_lookups = {f: get_field_lookups(v) for f, v in db_fields.items()}
    return OrderedDict(sorted(fields_to_field_name(fields_lookups).items()))


def get_quicksearch_fields_lookups(model, fields):
    """
    Takes in a model and a list of fields, and returns a dict where the keys are the field names,
    and the values are a list of lookup-expression used for them.
    """
    db_fields = {f: field_to_db_field(model, f) for f in fields}
    fields_lookups = {
        f: get_quicksearch_field_lookups(v)
        for f, v in db_fields.items()
        if type(v) not in [models.DateField, models.TimeField, models.DateTimeField]
    }
    return OrderedDict(sorted(fields_to_field_name(fields_lookups).items()))


@lru_cache(maxsize=None)
def get_field_lookups(field):
    """
    Takes in a field object and returns a list of valid lookup-expressions used for it.
    """
    match type(field):
        case money_fields.MoneyField:
            return ["startswith"]
        case models.DateField | models.TimeField | models.DateTimeField:
            return ["lte", "gte"]
        case models.IntegerField | models.FloatField | models.DecimalField | models.PositiveSmallIntegerField | models.PositiveIntegerField:
            return ["lte", "gte", "exact"]
        case models.ManyToManyField | models.ForeignKey:
            return ["in"]
        case models.BooleanField:
            return ["exact"]
        case _:
            return ["exact"]


@lru_cache(maxsize=None)
def get_quicksearch_field_lookups(field):
    """
    Takes in a field object and returns a list of valid lookup-expressions used for it.
    """
    match type(field):
        case models.DateField | models.TimeField | models.DateTimeField:
            return
        case _:
            return ["icontains"]


class ObjectEncoder(json.JSONEncoder):
    """
    A custom JSON encoder that can handle model instances and querysets.
    """

    def default(self, obj):
        if isinstance(obj, models.Model):
            return obj.pk
        elif isinstance(obj, models.QuerySet):
            return list(obj)
        elif isinstance(
            obj, (datetime.datetime, datetime.date, jdatetime.datetime, jdatetime.date)
        ):
            return obj.isoformat()
        elif isinstance(obj, Money):
            return float(obj.amount)
        elif isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, PhoneNumber):
            return obj.as_national

        return json.JSONEncoder.default(self, obj)


def clean_request_data(data, filterset):
    """
    Takes in request data and filterset from a view,
    and returns a dict where the keys are the field names,
    and the values are the values of the fields.
    Then point of this function is that it handles querysets and model instances
    by using ObjectEncoders.
    """
    data_keys = set(data)
    filters_name = data_keys & set(filterset.get_filters())
    filters = {name: data.get(name) for name in filters_name}
    other = {k for k in data_keys if not k.startswith("csrf")} - filters_name
    return json.loads(
        json.dumps(
            dict(filters=filters, **{o: data[o] for o in other}), cls=ObjectEncoder
        )
    )


def generate_filterset_form(model, *, form_classes=None, fields=None):
    """Generates a form class dynammically created for the given model."""
    if form_classes is None:
        form_classes = [forms.Form]
    if fields is None:
        fields = {}

    return type(
        f"{getattr(model, '__name__', '')}DynamicFilterSetForm",
        tuple(form_classes),
        fields,
    )


def get_template_columns(template, searchables=False, as_dict=True):
    """
    Takes in a template object and returns an dict of fields and custom fields defined on the model,
    where the keys are the name of the field, and the value is the display name evaluated for the field-name.
    """
    qs = template.columns.all()
    if searchables:
        qs = qs.filter(searchable=True)

    if as_dict:
        return {
            col_id: col_title for col_id, col_title in qs.values_list("id", "title")
        }

    return qs


def get_column_cell(obj, name, *, absolute_url=True):
    """
    Takes in an object and a column name, and returns the value of the column for the object.
    If the column is a custom field, it returns the value of the custom field.
    """
    model = obj._meta.model if hasattr(obj, "_meta") else None

    if isinstance(name, DynamicSubField):
        return name.get_value(obj)

    if callable(name):
        return name(obj, name)

    if isinstance(obj, dict):
        return obj.get(name, app_settings.DEFAULT_CELL_VALUE)

    attr = nested_getattr(obj, name, None, sep="__")
    if isinstance(attr, bool):
        return attr

    if model and (field := get_model_field(model, name)):
        if (
            isinstance(attr, datetime.datetime)
            and type(field) in app_settings.TIME_FORMATS
        ):
            attr = jdatetime.datetime.fromgregorian(datetime=attr).strftime(
                app_settings.TIME_FORMATS[type(field)]
            )
        elif (
            isinstance(attr, jdatetime.datetime)
            and type(field) in app_settings.TIME_FORMATS
        ):
            attr = attr.strftime(app_settings.TIME_FORMATS[type(field)])
        elif getattr(field, "one_to_many") or getattr(field, "many_to_many"):
            attr = ", ".join(map(str, methodcaller("all")(attrgetter(name)(obj))))
        elif field.choices:
            attr = getattr(obj, f"get_{field.name}_display", lambda: attr)()
        elif isinstance(field, money_fields.MoneyField):
            attr = str(attrgetter(name)(obj))
        elif isinstance(field, (models.FileField, models.ImageField)):
            attr = FieldFileAbsoluteURL(file=attr, absolute=absolute_url).url
        elif isinstance(field, PhoneNumberField):
            attr = str(attr).replace(" ", "-")

    return (attr and str(attr)) or app_settings.DEFAULT_CELL_VALUE


class ExportXls(BaseExportFormat):
    format_slug = "xls"
    format_name = "Excel"
    format_ext = ".xlsx"

    def get_export_filename(self):
        qs = self.get_export_qs()
        if not self.export_filename and isinstance(qs, QuerySet):
            with override("en"):
                return f"{qs.model._meta.verbose_name_plural}{self.format_ext}"

        return f"{self.export_filename}{self.format_ext}"

    def _apply_cell_style_map(self, style, value):
        style_map = {k: v for k, v in REPORT_CELL_STYLE_MAP if isinstance(value, k)}
        for _, cell_style in style_map:
            return cell_style, (callable(cell_style) and cell_style or (lambda i: i))(
                value
            )
        return style, value

    def _default_cell_fn(self, style, value, *args, **kwargs):
        return style, value

    def export(self):
        headers_name = self.get_export_headers()
        columns = headers_name.keys()
        queryset = self.get_export_qs()
        sheet_name = str(self.get_export_kwargs().get("sheet_name", "default"))
        cell_fn = self.get_export_kwargs().get("cell_fn", self._default_cell_fn)

        workbook = xlwt.Workbook(encoding="utf-8")
        default_style = xlwt.XFStyle()
        sheet = workbook.add_sheet(
            sheet_name
            or str(nested_getattr(queryset, "model._meta.verbose_name_plural", "sheet"))
        )

        for num, column in enumerate(columns):
            style, value = default_style, headers_name.get(column, column)
            if isinstance(column, DynamicSubField):
                value = column.get_verbose_name()
            style, value = cell_fn(
                obj=None, row_number=0, column=column, style=style, value=value
            )
            sheet.write(0, num, value, style)

        for x, obj in enumerate(queryset, start=1):
            for y, column in enumerate(columns):
                style, value = default_style, get_column_cell(obj, column)
                style, value = self._apply_cell_style_map(default_style, value)
                style, value = cell_fn(
                    obj=obj, row_number=x, column=column, style=style, value=value
                )
                value = str(value).strip("_")
                sheet.write(x, y, value, style or default_style)

        return workbook

    def handle(self):
        return self.export()

    def handle_response(self, response, *args, **kwargs):
        wb = self.handle(*args, **kwargs)
        wb.save(response)
        return response


export_format.register(ExportXls)


class ExportCsv(BaseExportFormat):
    format_slug = "csv"
    format_name = "CSV"
    format_ext = ".csv"

    def export(self):
        headers_name = self.get_export_headers()
        columns = headers_name.keys()
        queryset = self.get_export_qs()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([headers_name.get(column, column) for column in columns])
        writer.writerows(
            [[get_column_cell(obj, column) for column in columns] for obj in queryset]
        )
        return output

    def handle(self, *args, **kwargs):
        return self.export()

    def handle_response(self, response, *args, **kwargs):
        buff = self.handle(*args, **kwargs)
        response.write(buff.getvalue())
        return response


export_format.register(ExportCsv)


def queryset_to_df(queryset, columns, headers):
    header = ["#", *headers]
    data = []
    for i, obj in enumerate(queryset):
        data.append([str(i + 1), *[get_column_cell(obj, col) for col in columns]])

    df = pd.DataFrame(data, columns=header)
    return df


def get_report_filename(template):
    return f"{template.title}_{jdatetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"


def get_temporal_filter(filter_cls):
    class BaseTemporalField(filter_cls.field_class):
        def to_python(self, value):
            if value and "T" not in value:
                value = JalaliCalendar(value).get_date()["date_obj"]
            return super().to_python(value)

    return type(filter_cls.__name__, (filter_cls,), {"field_class": BaseTemporalField})


def fix_ordered_choice_field_values(choices, values):
    return (
        sorted(
            choices,
        )
        if values
        else choices
    )


def get_table_page_choices():
    seen = set()
    for u in sorted(get_project_urls(), key=lambda u: u["view_name"]):
        if (name := u["view_name"]) and name not in seen:
            seen.add(name)
            yield (name, f'{name} ({u["url"]})')


def get_table_page_optional_choices():
    return chain(
        [(None, "-" * 10)],
        get_table_page_choices(),
    )


def set_template_as_page_default(template):
    from .models import Template

    if template.page:
        Template.objects.filter(page=template.page).exclude(id=template.pk).update(
            is_page_default=False
        )
        Template.objects.filter(id=template.pk).update(is_page_default=True)


def get_model_property(model, field_name):
    fields = field_name.split(LOOKUP_SEP)

    latest_model = model
    for field in fields[:-1]:
        field = get_model_field(latest_model, field)

        if isinstance(field, RelatedField):
            field_model = field.remote_field.model
        elif isinstance(field, ForeignObjectRel):
            field_model = field.related_model
        else:
            return None

        latest_model = field_model

    property_name = fields[-1]

    if (
        hasattr(latest_model, property_name)
        and (field := getattr(latest_model, property_name))
        and (isinstance(field, property) or callable(field))
    ):
        return field

    return None


def get_field_name(field):
    """Get the name attribute of the field. If nested fields are passed, get the name property of the nested field."""
    return getattr(field, "name", None) or reduce(
        lambda o, a: getattr(o, a, None), [field, "field", "name"]
    )


def is_field_valid(model, field, *, as_filter=False):
    """
    Takes in a model and a field-name and checks if it can be evaluated,
    that is whether it's a field name or a property defined on the model.
    """
    if isinstance(field, str) and "__" in field:
        field = field.split("__")[0]

    with contextlib.suppress(AssertionError, AttributeError):
        db_field = field_to_db_field(model, field)
        # this line checks for possible AssertionErrors
        as_filter and FilterSet.filter_for_field(db_field, get_field_name(db_field))
        return as_filter or not getattr(db_field, "primary_key", False)
    return False


class QBuilder(ast.NodeVisitor):
    def visit_BoolOp(self, node):
        if isinstance(node.op, ast.And):
            return reduce(and_, (self.visit(value) for value in node.values))
        elif isinstance(node.op, ast.Or):
            return reduce(or_, (self.visit(value) for value in node.values))
        else:
            raise ValueError(f"Unsupported operator: {node.op}")

    def visit_Compare(self, node):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValueError("Only simple comparisons are supported")
        key = node.left.id
        val = node.comparators[0].s
        if isinstance(node.ops[0], ast.Eq):
            return Q(**{key: val})
        elif isinstance(node.ops[0], ast.NotEq):
            return ~Q(**{key: val})
        else:
            raise ValueError("Only equality and inequality comparisons are supported")


def string_to_q(q_str: str, q_vals: dict[str, str] = {}):
    """
    Takes a string that implements logics using parenthesis, ||, &&, and !=
    and ends in ='%(val_name)s', uses q_vals to replace val_name with the value of the key,
    and converts this whole string and val into django Q objects.
    """
    q_str = q_str.replace("||", "or").replace("&&", "and")

    try:
        q_str = q_str % q_vals
    except KeyError:
        logger.error("KeyError in string_to_q: %s", q_str)

    tree = ast.parse(q_str, mode="eval")

    builder = QBuilder()
    q_obj = builder.visit(tree.body)

    return q_obj


def get_related_property(model, field_name):
    fields = field_name.split(LOOKUP_SEP)

    latest_model = model
    for field in fields[:-1]:
        field = get_model_field(latest_model, field)

        if isinstance(field, RelatedField):
            field_model = field.remote_field.model
        elif isinstance(field, ForeignObjectRel):
            field_model = field.related_model
        else:
            return None

        latest_model = field_model

    property_name = fields[-1]

    if (
        hasattr(latest_model, property_name)
        and (field := getattr(latest_model, property_name))
        and (isinstance(field, property) or callable(field))
    ):
        return field

    return None

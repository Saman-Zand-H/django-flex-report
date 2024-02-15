import contextlib
import csv
import datetime
import importlib
import io
import json
import re
from collections import OrderedDict
from decimal import Decimal
from functools import lru_cache, reduce
from importlib import import_module
from itertools import chain
from operator import attrgetter, methodcaller
from typing import List
from phonenumber_field.modelfields import PhoneNumberField
import jdatetime
import pandas as pd
import xlwt
from dateparser.calendars.jalali import JalaliCalendar
from django import forms
from django.conf import settings
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

from flex_report import BaseExportFormat, ReportModel, export_format
from flex_report.fields import FieldFileAbsoluteURL

from .app_settings import app_settings
from .constants import (
    REPORT_CELL_STYLE_MAP,
    REPORT_CUSTOM_FIELDS_KEY,
    REPORT_EXCULDE_KEY,
    REPORT_FIELDS_KEY,
    FieldTypes,
)


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
        apps.get_app_config(app_name)
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
    field = get_model_field(model, column)

    if field:
        return FieldTypes.field

    field = get_model_property(model, column)

    if isinstance(field, property):
        return FieldTypes.property

    if callable(field):
        return FieldTypes.custom

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


def get_template_columns(template, searchables=False):
    """
    Takes in a template object and returns an dict of fields and custom fields defined on the model,
    where the keys are the name of the field, and the value is the display name evaluated for the field-name.
    """
    qs = template.columns.all()
    if searchables:
        qs = qs.filter(searchable=True)

    return {col_id: col_title for col_id, col_title in qs.values_list("id", "title")}


def get_column_cell(obj, name, *, absolute_url=True):
    """
    Takes in an object and a column name, and returns the value of the column for the object.
    If the column is a custom field, it returns the value of the custom field.
    """
    model = obj._meta.model
    if (
        (custom_field_part := name.split("."))
        and len(custom_field_part) > 1
        and get_column_type(model, (custom_field_function_name := custom_field_part[0]))
        == FieldTypes.custom
    ):
        custom_field_value = get_model_custom_field_value(
            model, custom_field_function_name
        )[custom_field_part[1]]
        custom_field_function = getattr(obj, custom_field_function_name)
        return custom_field_function(custom_field_value[0])

    if callable(name):
        return name(obj, name)

    attr = nested_getattr(obj, name, None, sep="__")
    if isinstance(attr, bool):
        return attr

    if field := get_model_field(model, name):
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
        elif isinstance(field, models.FileField):
            attr = FieldFileAbsoluteURL(file=attr, absolute=absolute_url)
        elif isinstance(field, PhoneNumberField):
            attr = str(attr).replace(" ", "-")

    return (attr and str(attr)) or app_settings.DEFAULT_CELL_VALUE


def increment_string_suffix(string):
    r = re.subn(
        r"[0-9]+$",
        lambda x: f"{str(int(x.group()) + 1).zfill(len(x.group()))}",
        string,
    )
    return r[0] if r[1] else f"{string}1"


@export_format.register
class ExportXls(BaseExportFormat):
    format_slug = "xls"
    format_name = "Excel"

    @classmethod
    def handle(cls, *args, **kwargs):
        """
        Convert queryset or list of rows as dict to XLS file.
        ### Parameters
        Get ``columns`` as list of keys to get from object and
        ``headers`` can be as mapping of column and label for file headers.

        ### Returns
        ``xlwt.Workbook`` object.

        ### Example
            >>> response = HttpResponse(....)
            qs = Users.objects.all()
            columns = ["first_name", "last_name"]
            headers = {"first_name": "First Name", "last_name": "Last Name"}
            wb = export_queryset_to_xls(qs, columns, headers)
            wb.save(response)

        """
        headers_name = kwargs.get("headers_name")
        queryset = kwargs.get("queryset")
        columns = kwargs.get("columns")
        cell_fn = kwargs.get("cell_fn")
        sheet_name = kwargs.get("sheet_name")
        
        required_args = ["queryset", "columns"]
        for arg in required_args:
            if arg not in kwargs:
                raise TypeError(f"missing required argument: '{arg}'")
        
        if headers_name is None:
            headers_name = {}
        workbook = xlwt.Workbook(encoding="utf-8")
        default_style = xlwt.XFStyle()
        sheet = workbook.add_sheet(sheet_name or str(nested_getattr(queryset, "model._meta.verbose_name_plural", "sheet")))

        for num, column in enumerate(columns):
            value = headers_name.get(column, column)
            style = default_style
            if cell_fn:
                style, value = cell_fn(obj=None, row_number=0, column=column, style=default_style, value=value)
            sheet.write(0, num, value, style)

        for x, obj in enumerate(queryset, start=1):
            for y, column in enumerate(columns):
                value = get_column_cell(obj, column)
                style = default_style
                for value_type, cell_style in REPORT_CELL_STYLE_MAP:
                    if isinstance(value, value_type):
                        if callable(cell_style):
                            style = default_style
                            value = cell_style(value)
                        else:
                            style = cell_style
                        break
                if cell_fn:
                    style, value = cell_fn(obj=obj, row_number=x, column=column, style=style, value=value)
                args = [x, y]
                if style:
                    args.extend([str(value), style])
                else:
                    args.append(value)
                sheet.write(*args)

        return workbook

    @classmethod
    def handle_response(cls, response, *args, **kwargs):
        wb = cls.handle(*args, **kwargs)
        wb.save(response)
        return response


@export_format.register
class ExportCsv(BaseExportFormat):
    format_slug = "csv"
    format_name = "CSV"

    @classmethod
    def handle(cls, *args, **kwargs):
        """
        Convert queryset or list rows as dict to CSV file.
        ### Parameters
        Get ``columns`` as list of keys to get from object and
        ``headers`` can be as mapping of column and label for file headers.

        ### Returns
        ``io.StringIO`` object.

        ### Example
            >>> response = HttpResponse(....)
            qs = Users.objects.all()
            columns = ["first_name", "last_name"]
            headers = {"first_name": "First Name", "last_name": "Last Name"}
            buff = export_queryset_to_csv(qs, columns, headers)
            response.write(buff.getvalue())

        """
        if not (queryset := kwargs.get("queryset", False)):
            raise TypeError("missing required argument: 'queryset'")

        if not (columns := kwargs.get("columns", False)):
            raise TypeError("missing required argument: 'columns'")

        if (headers := kwargs.get("headers")) is None:
            headers = {}
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([headers.get(column, column) for column in columns])
        writer.writerows(
            [[get_column_cell(obj, column) for column in columns] for obj in queryset]
        )
        return output

    @classmethod
    def handle_response(cls, response, *args, **kwargs):
        buff = cls.handle(*args, **kwargs)
        response.write(buff.getvalue())
        return response


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

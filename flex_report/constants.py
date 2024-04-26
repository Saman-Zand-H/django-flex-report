import datetime
from typing import Iterable, Any, List
from abc import abstractmethod

import django_filters
import xlwt

from .fields import FieldFileAbsoluteURL

META_REPORT_KEY = "use_for_report"
REPORT_FIELDS_KEY = "flex_report_search_fields"
REPORT_EXCULDE_KEY = "flex_report_search_exclude"
REPORT_COLUMNS_EXCULDE_KEY = "flex_report_columns_exclude"
REPORT_CUSTOM_FIELDS_KEY = "flex_report_custom_fields"

REPORT_CELL_STYLE_MAP = (
    (datetime.datetime, xlwt.easyxf(num_format_str="YYYY/MM/DD HH:MM")),
    (datetime.date, xlwt.easyxf(num_format_str="DD/MM/YYYY")),
    (datetime.time, xlwt.easyxf(num_format_str="HH:MM")),
    (bool, xlwt.easyxf(num_format_str="BOOLEAN")),
    (
        FieldFileAbsoluteURL,
        lambda v: xlwt.Formula(f'HYPERLINK("{v}","{v}")') if v else "",
    ),
)

FILTERSET_DATE_FILTERS = [
    django_filters.DateFilter,
    django_filters.TimeFilter,
    django_filters.DateTimeFilter,
]


class ReportModel:
    models = []

    @classmethod
    def register(cls, *models):
        cls.models.extend(models)
        return models[0]


class DynamicSubField:
    slug = None
    verbose_name = None

    def __init__(self, verbose_name=None):
        self.verbose_name = verbose_name or self.verbose_name

    def get_verbose_name(self):
        return str(self.verbose_name)

    @abstractmethod
    def get_value(cls, *args, **kwargs):
        pass


class BaseDynamicField:
    field_slug = None
    verbose_name = None
    model = None
    fields = {}

    @classmethod
    def get_by_slug(cls, slug):
        try:
            return cls.fields[slug]
        except KeyError as e:
            raise NotImplementedError(f"Field with slug {slug} not found") from e

    @classmethod
    def register(cls, field):
        assert issubclass(field, cls)
        cls.fields.update({field.field_slug: field})
        return field

    @classmethod
    @abstractmethod
    def unpack_field(cls, *args, **kwargs) -> List[DynamicSubField]:
        pass


class BaseExportFormat:
    formats = {}
    format_slug = None
    format_name = None
    format_ext = None
    export_headers = {}
    export_qs = []
    export_kwargs = {}
    export_filename = None

    def __init__(self, user=None, request=None):
        self.user = user
        self.request = request

    def get_export_headers(self):
        return self.export_headers

    def get_export_kwargs(self):
        return self.export_kwargs

    def get_export_filename(self):
        return f"{self.export_filename or self.format_slug}{self.format_ext}"

    def get_export_qs(self):
        return self.export_qs

    def check_auth(self):
        return True

    def __str__(self):
        return self.format_name

    @classmethod
    @property
    @abstractmethod
    def format_slug(cls):
        raise NotImplementedError

    @classmethod
    @property
    @abstractmethod
    def format_name(cls):
        raise NotImplementedError

    @classmethod
    def register(cls, format_):
        assert issubclass(format_, BaseExportFormat)
        cls.formats.update({format_.format_slug: format_})
        return format_

    @classmethod
    def register_formats(cls, formats: dict):
        cls.formats.update(formats)

    @abstractmethod
    def handle(cls):
        raise NotImplementedError

    @abstractmethod
    def handle_response(self, *args, **kwargs):
        raise NotImplementedError


class FieldTypes:
    field = "field"
    property = "property"
    custom = "custom"
    dynamic = "dynamic"


class BaseDynamicColumn:
    columns = {}

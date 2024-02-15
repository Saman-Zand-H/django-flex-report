import datetime
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
        lambda v: xlwt.Formula(f'HYPERLINK("{v}";"{v}")') if v else "",
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


class BaseExportFormat:
    formats = {}
    format_slug = None
    format_name = None

    @classmethod
    def __str__(cls):
        return cls.format_name

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
        return cls.formats.update({format_.format_slug: format_})

    @classmethod
    def register_formats(cls, formats: dict):
        cls.formats.update(formats)

    @classmethod
    @abstractmethod
    def handle(cls, *args, **kwargs):
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def handle_response(cls, *args, **kwargs):
        raise NotImplementedError


class FieldTypes:
    field = "field"
    property = "property"
    custom = "custom"

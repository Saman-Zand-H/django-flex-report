import importlib

from django_jalali.db import models as jmodels
from phonenumber_field.modelfields import PhoneNumberField

from django.apps import apps
from django.conf import settings
from django.db import models


def import_attribute(path):
    assert isinstance(path, str)
    pkg, attr = path.rsplit(".", 1)
    ret = getattr(importlib.import_module(pkg), attr)
    return ret


def import_callable(path_or_callable):
    if not hasattr(path_or_callable, "__call__"):
        ret = import_attribute(path_or_callable)
    else:
        ret = path_or_callable
    return ret


def get_setting(name, dflt):
    getter = getattr(
        settings,
        "REPORT_SETTING_GETTER",
        lambda name, dflt: getattr(settings, name, dflt),
    )
    getter = import_callable(getter)
    return getter(name, dflt)


class AppSettings(object):
    def __init__(self, prefix="REPORT_"):
        self.prefix = prefix

    def _settings(self, name, dflt):
        return get_setting(self.prefix + name, dflt)

    @property
    def DATETIME_FIELD(self):
        return import_callable(self._settings("DATETIME_FIELD_CALLBACK", "django.db.models.DateTimeField"))

    @property
    def DATE_FIELD_(self):
        return self._settings("DATE_FIELD_CALLBACK", "django.db.models.DateField")

    @property
    def FILTERSET_CLASS(self):
        return import_callable(self._settings("FILTERSET_CLASS", "flex_report.filterset.FilterSet"))

    @property
    def FORMS(self):
        dflt = forms = {
            "CREATE_COLUMN": lambda form: form,
            "CREATE_TEMPLATE": lambda form: form,
        }
        if FORMS := self._settings("FORMS", False):
            forms = {k: FORMS.get(k, v) for k, v in dflt.items()}

        return {k: import_callable(v) for k, v in forms.items()}

    @property
    def BASE_VIEW(self):
        base_view = self._settings("BASE_VIEW", False)
        return import_callable(base_view) if base_view else None

    @property
    def DEFAULT_CELL_VALUE(self):
        return self._settings("DEFAULT_CELL_VALUE", "&mdash;")

    @property
    def EDITORS_GROUP_NAME(self):
        return self._settings("EDITORS_GROUP_NAME", "report_editors")

    @property
    def TIME_FORMATS(self):
        dflt = time_formats = {
            models.DateTimeField: "%H:%M %Y/%m/%d",
            models.DateField: "%Y/%m/%d",
            models.TimeField: "%H:%M:%S",
            jmodels.jDateField: "%H:%M:%S",
            jmodels.jDateTimeField: "%H:%M %Y/%m/%d",
        }

        if FORMATS := self._settings("TIME_FORMATS", False):
            assert isinstance(FORMATS, dict)
            time_formats = {k: FORMATS.get(k, v) for k, v in dflt.items()}

        return time_formats

    @property
    def DATA_TAGS(self):
        dflt = data_tags = {
            models.ImageField: lambda v: f'<img src="{v}" height="100" loading="lazy">',
            models.URLField: lambda v: f'<a href="{v}" target="_blank">مشاهده</a>',
            models.FileField: lambda v: f'<a href="{v}" download="{v.split('/')[-1]}">مشاهده</a>',
            models.BooleanField: lambda v: f'<i class="material-icons-outlined">{v and 'check_circle' or 'cancel'}</i>',
            "default": lambda v: f"<span>{v}</span>",
            PhoneNumberField: lambda v: f"<span>{v.replace(' ', '-')}</span>",
        }

        if DATA_TAGS := self._settings("DATA_TAGS", False):
            assert isinstance(DATA_TAGS, dict)
            data_tags = {k: DATA_TAGS.get(k, v) for k, v in dflt.items()}

        return data_tags

    @property
    def MODEL_USER_PATH_FUNC_NAME(self):
        return self._settings("MODEL_USER_PATH_FUNC_NAME", "report_user_path")

    @property
    def VIEWS(self):
        dflt = views = {
            "TEMPLATE_LIST": "flex_report.views.template_list_view",
            "GENERAL_QS_EXPORT": "flex_report.views.general_qs_export_view",
            "TEMPLATE_CREATE_INIT": "flex_report.views.template_create_init_view",
            "TEMPLATE_CREATE_COMPLETE": "flex_report.views.template_create_complete_view",
            "TEMPLATE_DELETE": "flex_report.views.template_delete_view",
            "TEMPLATE_UPDATE": "flex_report.views.template_update_view",
            "TEMPLATE_CLONE": "flex_report.views.template_clone_view",
            "TEMPLATE_TOGGLE_DEFAULT": "flex_report.views.template_toggle_default_view",
            "COLUMN_LIST": "flex_report.views.column_list_view",
            "COLUMN_CREATE": "flex_report.views.column_create_view",
            "COLUMN_UPDATE": "flex_report.views.column_update_view",
            "COLUMN_DELETE": "flex_report.views.column_delete_view",
            "REPORT": "flex_report.views.report_view",
            "REPORT_EXPORT": "flex_report.views.report_export_view",
        }
        if VIEWS := self._settings("VIEWS", False):
            assert isinstance(VIEWS, dict)
            views = {k: VIEWS.get(k, v) for k, v in dflt.items()}

        return {k: import_callable(v) for k, v in views.items()}

    @property
    def REALTIME_QUICKSEARCH(self):
        return self._settings("REALTIME_QUICKSEARCH", True)

    @property
    def MODEL_EXPORT_KWARGS_FUNC_NAME(self):
        return self._settings("MODEL_EXPORT_KWARGS_FUNC_NAME", "flex_export_kwargs")

    @property
    def MODEL_ADMINS(self):
        dflt = model_admins = {
            "Template": "flex_report.defaults.admin.TemplateAdmin",
            "Column": "flex_report.defaults.admin.ColumnAdmin",
            "TableButton": "flex_report.defaults.admin.TableButtonAdmin",
            "TablePage": "flex_report.defaults.admin.TablePageAdmin",
            "TableButtonColor": "flex_report.defaults.admin.TableButtonColorAdmin",
            "TemplateSavedFilter": "flex_report.defaults.admin.TemplateSavedFilterAdmin",
        }
        if ADMINS := self._settings("MODEL_ADMINS", False):
            assert isinstance(ADMINS, dict)
            model_admins = {k: ADMINS.get(k, v) for k, v in dflt.items()}

        return {apps.get_model("flex_report", k): import_callable(v) for k, v in model_admins.items()}


app_settings = AppSettings()

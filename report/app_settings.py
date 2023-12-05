from .utils import get_setting, import_callable


class AppSettings(object):
    def __init__(self, prefix="REPORT_"):
        self.prefix = prefix

    def _settings(self, name, dflt):
        return get_setting(self.prefix + name, dflt)

    @property
    def FILTERSET_CLASS(self):
        return import_callable(self._settings("FILTERSET_CLASS", "filterset.Filterset"))

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
    def EDITORS_GROUP_NAME(self):
        return self._settings("EDITORS_GROUP_NAME", "report_editors")

    @property
    def VIEWS(self):
        dflt = views = {
            "TEMPLATE_LIST": "report.views.template_list_view",
            "TEMPLATE_CREATE_INIT": "report.views.template_create_init_view",
            "TEMPLATE_CREATE_COMPLETE": "report.views.template_create_complete_view",
            "TEMPLATE_DELETE": "report.views.template_delete_view",
            "TEMPLATE_UPDATE": "report.views.template_update_view",
            "TEMPLATE_CLONE": "report.views.template_clone_view",
            "TEMPLATE_TOGGLE_DEFAULT": "report.views.template_toggle_default_view",
            "COLUMN_LIST": "report.views.column_list_view",
            "COLUMN_CREATE": "report.views.column_create_view",
            "COLUMN_UPDATE": "report.views.column_update_view",
            "COLUMN_DELETE": "report.views.column_delete_view",
            "REPORT": "report.views.report_view",
            "REPORT_EXPORT": "report.views.report_export_view",
        }
        if VIEWS := self._settings("VIEWS", False):
            assert isinstance(VIEWS, dict)
            views = {k: VIEWS.get(k, v) for k, v in dflt.items()}

        return {k: import_callable(v) for k, v in views.items()}

    @property
    def REALTIME_QUICKSEARCH(self):
        return self._settings("REALTIME_QUICKSEARCH", True)


app_settings = AppSettings()

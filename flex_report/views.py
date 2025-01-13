from .app_settings import app_settings
from .defaults.views import (
    BaseView,
    ColumnCreateView,
    ColumnDeleteView,
    ColumnListView,
    ColumnUpdateView,
    GeneralQuerySetExportView,
    ReportExportView,
    ReportView,
    TemplateCloneView,
    TemplateCreateCompleteView,
    TemplateCreateInitView,
    TemplateDeleteView,
    TemplateListView,
    TemplateToggleDefaultView,
    TemplateUpdateView,
)

BaseView = app_settings.BASE_VIEW or BaseView


column_create_view = ColumnCreateView.as_view()


column_list_view = ColumnListView.as_view()


column_update_view = ColumnUpdateView.as_view()


column_delete_view = ColumnDeleteView.as_view()


template_list_view = TemplateListView.as_view()


template_delete_view = TemplateDeleteView.as_view()


template_create_init_view = TemplateCreateInitView.as_view()


template_clone_view = TemplateCloneView.as_view()


template_toggle_default_view = TemplateToggleDefaultView.as_view()


template_create_complete_view = TemplateCreateCompleteView.as_view()


template_update_view = TemplateUpdateView.as_view()


report_view = ReportView.as_view()


general_qs_export_view = GeneralQuerySetExportView.as_view()


report_export_view = ReportExportView.as_view()

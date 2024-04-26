from django.urls import include, path

from . import views
from .app_settings import app_settings

VIEWS = app_settings.VIEWS


app_name = "flex_report"
template_urls = [
    path("", VIEWS["TEMPLATE_LIST"], name="index"),
    path("<int:pk>/export", VIEWS["REPORT_EXPORT"], name="export"),
    path(
        "new/",
        VIEWS["TEMPLATE_CREATE_INIT"],
        name="create",
    ),
    path(
        "new/<int:pk>/",
        VIEWS["TEMPLATE_CREATE_COMPLETE"],
        name="create_complete",
    ),
    path(
        "<int:pk>/delete/",
        VIEWS["TEMPLATE_DELETE"],
        name="delete",
    ),
    path(
        "<int:pk>/edit/",
        VIEWS["TEMPLATE_UPDATE"],
        name="edit",
    ),
    path(
        "<int:pk>/clone/",
        VIEWS["TEMPLATE_CLONE"],
        name="clone",
    ),
    path(
        "<int:pk>/toggle-default/",
        VIEWS["TEMPLATE_TOGGLE_DEFAULT"],
        name="toggle-default",
    ),
]

column_urls = [
    path(
        route="",
        view=VIEWS["COLUMN_LIST"],
        name="index",
    ),
    path(
        route="new/",
        view=VIEWS["COLUMN_CREATE"],
        name="create",
    ),
    path(
        route="<int:pk>/edit",
        view=VIEWS["COLUMN_UPDATE"],
        name="edit",
    ),
    path(
        route="<int:pk>/delete",
        view=VIEWS["COLUMN_DELETE"],
        name="delete",
    ),
]

urlpatterns = [
    path("<int:pk>/", VIEWS["REPORT"], name="view"),
    path("export/", VIEWS["GENERAL_QS_EXPORT"], name="export"),
    path("columns/", include((column_urls, "column"), namespace="column")),
    path(
        "template/",
        include((template_urls, "template"), namespace="template"),
    ),
]

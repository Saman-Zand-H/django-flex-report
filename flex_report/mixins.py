import ast
import contextlib
import mimetypes
from logging import getLogger

from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, Paginator
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import HttpResponse
from django.utils.translation import gettext_lazy as _
from django.views.generic import View
from flex_report import BaseExportFormat, export_format

from .app_settings import app_settings
from .filterset import (
    generate_filterset_from_model,
    generate_quicksearch_filterset_from_model,
)
from .forms import SavedFilterSelectForm
from .models import Template
from .utils import (
    FieldTypes,
    generate_filterset_form,
    get_choice_field_choices,
    get_col_verbose_name,
    get_template_columns,
    string_to_q,
)

logger = getLogger(__file__)


class PaginationMixin(View):
    pages = [25, 75, 100, 200]
    default_page = pages[0]
    pagination = None
    page_keyword = "page"
    per_page_ketyword = "per_page"

    def get_page(self):
        page = self.request.GET.get(self.page_keyword, 1)
        per_page = (
            p
            if (p := self.request.GET.get(self.per_page_ketyword, self.default_page)) and p in map(str, self.pages)
            else self.default_page
        )

        with contextlib.suppress(EmptyPage):
            paginator = Paginator(self.get_paginate_qs(), per_page)
            return paginator.page(page)

        return paginator.page(1)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = self.get_page()
        context["pagination"] = self.pagination = {
            "pages": self.pages,
            "qs": page,
            "paginator": page.paginator,
            "page_keyword": self.page_keyword,
            "per_page_keyword": self.per_page_ketyword,
        }
        return context

    def get_paginate_qs(self):
        return []


class TemplateObjectMixin(View):
    template_object = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        try:
            self.template_object = self.get_template()
        except PermissionDenied:
            return HttpResponseForbidden()

    def dispatch(self, *args, **kwargs):
        from .models import Template

        handler = None
        match self.template_object and self.template_object.status:
            case Template.Status.complete:
                handler = self.template_ready()
            case Template.Status.pending:
                handler = self.template_not_ready()
        return handler or super().dispatch(*args, **kwargs)

    def get_context_data(self, *args, **kwargs):
        return {
            "realtime_quicksearch": app_settings.REALTIME_QUICKSEARCH,
            "has_export": self.template_object.has_export,
        }

    def get_template(self):
        return self.get_object()

    def template_ready(self):
        pass

    def template_not_ready(self):
        pass


class QuerySetExportMixin(View):
    export_qs = []
    export_headers = {}
    export_columns = []
    export_kwargs = {}
    export_filename = None

    def get_export_filename(self):
        return self.export_filename

    def get_export_columns(self):
        return self.export_columns

    def get_export_headers(self):
        return self.export_headers

    def get_export_qs(self):
        return self.export_qs

    def get_export_kwargs(self):
        return self.export_kwargs

    def get_handle_qs(self):
        return {
            "export_qs": self.get_export_qs(),
            "export_headers": self.get_export_headers(),
            "export_columns": self.get_export_columns(),
            "export_kwargs": self.get_export_kwargs(),
        }

    def check_auth(self):
        if not hasattr((exporter := self.get_exporter()), "check_auth"):
            return

        if exporter.check_auth():
            return

        raise HttpResponseForbidden(content="403 Forbidden")

    def dispatch(self, *args, **kwargs):
        if not (format_ := self.request.GET.get("format", "").lower()) or format_ not in export_format.formats.keys():
            return HttpResponseBadRequest()

        self.export_format = format_
        self.check_auth()

        return super().dispatch(*args, **kwargs)

    def get_exporter(self) -> BaseExportFormat:
        try:
            format_ = export_format.formats[self.export_format]
            if any(self.get_handle_qs().values()):
                return type("DynamicExporter", (format_,), self.get_handle_qs())(
                    request=self.request, user=self.request.user
                )
            return format_(request=self.request, user=self.request.user)
        except KeyError as e:
            raise NotImplementedError(f"The wanted format '{self.export_format}' isn't handled.") from e

    def get(self, *args, **kwargs):
        format_ = self.get_exporter()
        filename = str(format_.get_export_filename())

        response = HttpResponse(
            content_type=mimetypes.types_map.get(
                f".{format_.format_ext}",
                "application/octet-stream",
            ),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
        response = format_.handle_response(
            response=response,
        )

        return response


class TablePageMixin(PaginationMixin, TemplateObjectMixin):
    page_keyword = "report_page"
    per_page_keyword = "report_per_page"
    page_template_keyword = "report_template"
    saved_filter_keyword = "saved_filter"

    is_page_table = True
    have_template = True

    template_columns = None
    template_searchable_fields = None
    report_qs = None
    filters = None
    quicksearch = None
    used_filters = None
    ignore_search_values = ["unknown"]
    ignore_search_keys = ["report_template"]

    def get_template(self):
        templates = self.get_page_templates()
        default_template = templates.filter(is_page_default=True).first() or templates.first()
        if not (page_template := self.request.GET.get(self.page_template_keyword)):
            return default_template

        if template := templates.filter(pk=page_template).first():
            return template

        return default_template

    def setup_filters(self):
        saved_filters = getattr(self.get_saved_filter(), "filters", {})
        initials = saved_filters | self.get_initials()
        form_classes = self.get_form_classes()

        self.template_filters = generate_filterset_from_model(self.report_model, form_classes)(
            self.template_object.filters or {}
        )
        self.filters = generate_filterset_from_model(self.report_model, form_classes)(initials)
        self.quicksearch = generate_quicksearch_filterset_from_model(
            self.report_model,
            self.template_searchable_fields.values(),
        )(initials)

    def _has_logical_operator(self, filter_path):
        LOGICAL_OPERATORS = ["(", ")", "&", "|", "!="]
        return any(op in filter_path for op in LOGICAL_OPERATORS)

    def apply_user_path(self, report_qs):
        access_handler = getattr(self.report_model, app_settings.MODEL_USER_PATH_FUNC_NAME, lambda request: {})
        accessed_paths = {
            name: {path: access_handler(self.request).get(name)}
            for name, path in (self.template_object.model_user_path or {}).items()
            if access_handler(self.request).get(name)
        }

        matches_paths = next(iter(accessed_paths.keys()), "__all__")
        if not (accessed_paths and matches_paths):
            return report_qs

        filter_path, filter_value = next(iter(accessed_paths[matches_paths].items()))
        filter_func = self._has_logical_operator(filter_path) and string_to_q or report_qs.filter

        return filter_func(**{filter_path: filter_value}).distinct()

    def _format_used_filter(self, col_name, val):
        formats = {**{k: _("Yes") for k in ["true", "True", True]}, **{k: "خیر" for k in ["false", "False", False]}}
        return formats.get(val, dict(get_choice_field_choices(self.report_model, col_name) or []).get(val, str(val)))

    def used_filter_format(self, col_name, val):
        return (
            ", ".join(map(lambda v: self._format_used_filter(col_name, v), val))
            if isinstance(val, list)
            else self._format_used_filter(col_name, val)
        )

    def validate_filters(self, *filters_list):
        return all(f.get_filters() and f.data and f.is_valid() for f in filters_list)

    def get_saved_filter_form(self):
        return SavedFilterSelectForm(
            self.request.GET,
            template=self.template_object,
        )

    def get_saved_filter(self):
        if not self.get_template():
            return {}

        if not (saved_filter_form := self.get_saved_filter_form()).is_valid():
            return saved_filter_form.initial.get(self.saved_filter_keyword, {})

        return getattr(saved_filter_form, "cleaned_data", {}).get(self.saved_filter_keyword) or {}

    def get_report_qs(self):
        self.setup_filters()

        report_qs = (
            self.template_filters.qs.distinct()
            if self.template_filters.get_filters()
            else self.report_model.objects.all()
        )
        report_qs = self.apply_user_path(report_qs)

        if self.validate_filters(self.filters, self.quicksearch, self.template_filters):
            report_qs = (
                report_qs.distinct()
                .filter(pk__in=(self.quicksearch.qs.distinct() & self.filters.qs.distinct()).values("pk"))
                .order_by(*self.report_model._meta.ordering or ["pk"])
            )
            cleaned_data = self.quicksearch.form.cleaned_data | self.filters.form.cleaned_data
            self.used_filters = self.get_used_filters(
                {
                    get_col_verbose_name(self.report_model, k): self.used_filter_format(k, v)
                    for k, v in cleaned_data.items()
                    if v
                }
            )

        return report_qs

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)

        if not (obj := self.template_object):
            self.have_template = False
            return

        self.report_model = obj.model.model_class()
        self.template_columns = get_template_columns(obj, as_dict=False)
        self.template_searchable_fields = get_template_columns(obj, searchables=True)
        self.report_qs = self.get_report_qs()

    def get_used_filters(self, cleaned_data):
        return _(" and ").join(
            f'{k} = {", ".join(map(str, v)) if isinstance(v, list) else v}'
            for k, v in cleaned_data.items()
            if k.lower() != "search"
        )

    def _prepare_initial(self, initial):
        if initial.lower() in ["true", "false"]:
            return initial.lower() == "true"
        if initial.startswith("[") and initial.endswith("]") or (initial.isnumeric() and not initial.startswith("0")):
            return ast.literal_eval(initial)
        return initial

    def get_initial_value(self, initial, *, key=""):
        return (
            list(map(self._prepare_initial, self.request.GET.getlist(key)))
            if key.endswith("__in")
            else self._prepare_initial(str(initial))
        )

    def get_initials(self):
        return {
            k: self.get_initial_value(v, key=k)
            for k, v in self.request.GET.dict().items()
            if v.strip() and v not in self.ignore_search_values and k not in self.ignore_search_keys
        }

    def get_form_classes(self):
        if not self.template_object:
            return []
        return [generate_filterset_form(self.report_model)]

    def get_paginate_qs(self):
        return self.get_report_qs()

    def get_context_data(self, **kwargs):
        if not self.have_template:
            return super(TemplateObjectMixin, self).get_context_data(**kwargs)

        context = super().get_context_data(**kwargs)
        context["report"] = {
            "columns": self.template_columns,
            "columns_count": len(self.template_columns)
            + self.template_object.buttons.count()
            + sum(
                len(field.get_dynamic_obj().unpack_field())
                for field in self.template_columns.filter(column_type=FieldTypes.dynamic).only("pk")
            )
            + 1,
            "filters": self.filters,
            "buttons": self.template_object.buttons.all(),
            "searchable_fields": self.template_searchable_fields,
            "quicksearch": self.quicksearch,
            "used_filters": self.used_filters,
            "template": self.template_object,
            "templates": self.get_page_templates(),
            "initials": self.get_initials(),
            "pagination": self.pagination,
            "page_template_keyword": self.page_template_keyword,
            "saved_filter_form": self.get_saved_filter_form(),
            "is_page_table": self.is_page_table,
            "have_template": self.have_template,
            "export_formats": [
                {"name": format_.format_name, "slug": format_.format_slug} for format_ in export_format.formats.values()
            ],
            "page_title": getattr(self.template_object.page, "title", self.template_object.title),
        }
        return context

    def get_page_templates(self):
        return Template.objects.filter(page__url_name=self.request.resolver_match.view_name).order_by(
            "-is_page_default"
        )

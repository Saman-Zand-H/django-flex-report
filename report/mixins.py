import ast
import mimetypes
from operator import call
from logging import getLogger

from django.core.exceptions import FieldError, PermissionDenied
from django.core.paginator import EmptyPage, Paginator
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import HttpResponse, redirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from report import export_format

from .app_settings import app_settings
from .filterset import generate_filterset_from_model, generate_quicksearch_filterset_from_model
from .models import Template
from .utils import generate_filterset_form, get_template_columns

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
        try:
            paginator = Paginator(self.get_paginate_qs(), per_page)
            page_obj = paginator.page(page)
        except EmptyPage:
            page_obj = paginator.page(1)
        return page_obj

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
    valid_file_exports = ["xls", "csv", "pdf"]
    export_format = None
    export_file_name = None
    export_qs = None
    export_columns = None
    export_headers = None
    sheet_name = None

    def get_export_qs(self):
        return self.export_qs or []

    def get_export_columns(self):
        return self.export_columns or [*self.get_export_headers().values()] or []

    def get_export_headers(self):
        return self.export_headers or []

    def get_handle_kwargs(self):
        return {
            "queryset": self.get_export_qs(),
            "columns": self.get_export_columns(),
            "headers": self.get_export_headers(),
        }

    def dispatch(self, *args, **kwargs):
        if not self.export_format and (
            not (format_ := self.request.GET.get("format", "").lower()) or format_ not in self.valid_file_exports
        ):
            return HttpResponseBadRequest()
        self.export_format = self.export_format or format_
        return super().dispatch(*args, **kwargs)

    def get(self, *args, **kwargs):
        filename = f"{self.export_file_name and f'{self.export_file_name}.' or ''}{self.export_format}"
        response = HttpResponse(
            content_type=mimetypes.types_map.get(
                f".{self.export_format}",
                "application/octet-stream",
            ),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

        try:
            format_ = export_format.formats[self.export_format]
        except KeyError:
            logger.critical(f"The wanted format '{self.export_format}' isn't handled.")
            return redirect(self.request.META.get("HTTP_REFERER", "/"))

        print(self.get_handle_kwargs())
        response = format_.handle_response(
            response=response,
            **self.get_handle_kwargs(),
        )

        return response


class TablePageMixin(PaginationMixin, TemplateObjectMixin):
    page_keyword = "report_page"
    per_page_keyword = "report_per_page"
    page_template_keyword = "report_template"

    is_page_table = True
    have_template = True

    template_columns = None
    template_searchable_fields = None
    report_qs = None
    filters = None
    quicksearch = None
    used_filters = None

    def get_template(self):
        page_template = self.request.GET.get(self.page_template_keyword)
        if page_template and (template := self.get_page_templates().filter(pk=page_template)):
            return template.first()
        template = self.get_page_templates().filter(is_page_default=True) or self.get_page_templates()
        return template.first()

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        obj = self.template_object
        if not obj:
            self.have_template = False
            return

        model = obj.model.model_class()
        self.template_columns = get_template_columns(obj)
        self.template_searchable_fields = get_template_columns(obj, searchables=True)
        self.filters = generate_filterset_from_model(
            model,
            self.get_form_classes(),
        )(self.get_initials())

        self.quicksearch = generate_quicksearch_filterset_from_model(
            model, [*self.template_searchable_fields.values()]
        )(self.get_initials())

        self.report_qs = (self.quicksearch.qs.distinct() & self.filters.qs.distinct()).order_by("pk")
        if self.template_object.model_user_path:
            try:
                val = self.request.user
                if hasattr(model, app_settings.MODEL_USER_PATH_FUNC_NAME):
                    val = call(getattr(model, app_settings.MODEL_USER_PATH_FUNC_NAME), request=self.request)

                self.report_qs = self.report_qs.filter(**{self.template_object.model_user_path: val})
            except FieldError:
                pass

        if self.filters.is_valid() and self.quicksearch.is_valid():
            cleaned_data = self.quicksearch.form.cleaned_data | self.filters.form.cleaned_data
            self.used_filters = self.get_used_filters({k: v for k, v in cleaned_data.items() if bool(v)})

    def get_used_filters(self, cleaned_data):
        return _(" and ").join(
            [f'{k} = {",".join(map(str, v)) if isinstance(v, list) else v}' for k, v in cleaned_data.items()]
        )

    def get_initial_value(self, initial):
        match type(initial):
            case str:
                if initial.startswith("[") and initial.endswith("]"):
                    return ast.literal_eval(initial)
        return initial

    def get_initials(self):
        return {k: self.get_initial_value(v) for k, v in self.request.GET.dict().items() if bool(v)}

    def get_form_classes(self):
        if not (obj := self.template_object):
            return []
        return [generate_filterset_form(obj.model.model_class())]

    def get_paginate_qs(self):
        return self.report_qs

    def get_context_data(self, **kwargs):
        if self.have_template:
            context = super().get_context_data(**kwargs)
        else:
            return super(TemplateObjectMixin, self).get_context_data(**kwargs)

        context["report"] = {
            "columns": self.template_columns,
            "columns_count": len(self.template_columns) + self.template_object.buttons.count() + 1,
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

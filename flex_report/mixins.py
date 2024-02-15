import ast
import contextlib
from operator import attrgetter
import mimetypes
from operator import call
from logging import getLogger

from django.core.exceptions import FieldError, PermissionDenied
from django.db.models import Subquery
from django.core.paginator import EmptyPage, Paginator
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import HttpResponse, redirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from flex_report import export_format

from .app_settings import app_settings
from .templatetags.flex_report_filters import get_column_verbose_name
from .filterset import (
    generate_filterset_from_model,
    generate_quicksearch_filterset_from_model,
)
from .models import Template
from .utils import generate_filterset_form, get_template_columns, get_choice_field_choices

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
            if (p := self.request.GET.get(self.per_page_ketyword, self.default_page))
            and p in map(str, self.pages)
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
            not (format_ := self.request.GET.get("format", "").lower())
            or format_ not in self.valid_file_exports
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
    ignore_search_values = [
        "unknown",
    ]

    def get_template(self):
        page_template = self.request.GET.get(self.page_template_keyword)
        if page_template and (
            template := self.get_page_templates().filter(pk=page_template)
        ):
            return template.first()
        template = (
            self.get_page_templates().filter(is_page_default=True)
            or self.get_page_templates()
        )
        return template.first()
    
    def apply_filters(self):
        initials = self.get_initials()
        
        self.template_filters = generate_filterset_from_model(
            self.model, self.get_form_classes()
        )(self.template_object.filters or {})
        self.filters = generate_filterset_from_model(
            self.model,
            self.get_form_classes(),
        )(initials)
        self.quicksearch = generate_quicksearch_filterset_from_model(
            self.model, list(self.template_searchable_fields.values())
        )(initials)
    
    def apply_user_path(self, model):
        paths = self.template_object.model_user_path or {}
        
        for path_name, path in paths.items():
            with contextlib.suppress(FieldError):
                val = False
                if (
                    method_name := getattr(
                        model, app_settings.MODEL_USER_PATH_FUNC_NAME
                    ),
                    False,
                ):
                    assert callable(method_name), f"{method_name} is not callable"
                    
                    val = call(
                        method_name,
                        request=self.request,
                    )
                    
                if not val:
                    continue

                self.report_qs = self.report_qs.filter(
                    **{path: (val or {}).get(path_name)}
                ).order_by(*model._meta.ordering or ["pk"])
                
    def used_filter_format(self, col_name, val):
        formats = {
            **{k: "بله" for k in ["true", "True", True]},
            **{k: "خیر" for k in ["false", "False", False]},
        }
        if (formatted_val := formats.get(val, False)):
            return formatted_val
        
        if (choices := get_choice_field_choices(self.model, col_name)):
            return dict(choices).get(val, val)
        
        return formatted_val or val

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        
        obj = self.template_object
        if not obj:
            self.have_template = False
            return

        self.model = obj.model.model_class()
        self.template_columns = get_template_columns(obj)
        self.template_searchable_fields = get_template_columns(obj, searchables=True)

        self.apply_filters()
        filters_valid = lambda: self.template_filters.is_valid() and self.quicksearch.is_valid() and self.filters.is_valid()
        
        self.report_qs = self.model.objects.none()
        if filters_valid():
            self.report_qs = self.template_filters.qs.distinct().filter(
                pk__in=Subquery((self.quicksearch.qs.distinct() & self.filters.qs.distinct()).values("pk"))
            ).order_by(*self.model._meta.ordering or ["pk"])

            self.apply_user_path(self.model)        

        if self.filters.is_valid() and self.quicksearch.is_valid():
            cleaned_data = (
                self.quicksearch.form.cleaned_data | self.filters.form.cleaned_data
            )
            self.used_filters = self.get_used_filters(
                {get_column_verbose_name(self.model, k): self.used_filter_format(k, v) for k, v in cleaned_data.items() if bool(v)}
            )

    def get_used_filters(self, cleaned_data):
        return _(" and ").join(
            [
                f'{k} = {",".join(map(str, v)) if isinstance(v, list) else v}'
                for k, v in cleaned_data.items()
            ]
        )

    def get_initial_value(self, initial):
        initial = str(initial)

        if initial.lower() in ["true", "false"]:
            return initial.lower() == "true"

        if (initial.startswith("[") and initial.endswith("]")) or initial.isnumeric():
            return ast.literal_eval(initial)

        return initial

    def get_initials(self):
        return {
            k: self.get_initial_value(v)
            for k, v in self.request.GET.dict().items()
            if str(v) and v.strip() not in self.ignore_search_values
        }

    def get_form_classes(self):
        if not self.template_object:
            return []
        return [generate_filterset_form(self.model)]

    def get_paginate_qs(self):
        return self.report_qs

    def get_context_data(self, **kwargs):
        if self.have_template:
            context = super().get_context_data(**kwargs)
        else:
            return super(TemplateObjectMixin, self).get_context_data(**kwargs)

        context["report"] = {
            "columns": self.template_columns,
            "columns_count": len(self.template_columns)
            + self.template_object.buttons.count()
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
            "is_page_table": self.is_page_table,
            "have_template": self.have_template,
            "export_formats": [
                {"name": format_.format_name, "slug": format_.format_slug}
                for format_ in export_format.formats.values()
            ],
            "page_title": getattr(
                self.template_object.page, "title", self.template_object.title
            ),
        }
        return context

    def get_page_templates(self):
        return Template.objects.filter(
            page__url_name=self.request.resolver_match.view_name
        ).order_by("-is_page_default")

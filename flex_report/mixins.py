import ast
import mimetypes
from operator import call, ne, methodcaller, attrgetter
from functools import partial
from logging import getLogger

from django.core.exceptions import PermissionDenied
from django.db.models import Subquery
from django.core.paginator import EmptyPage, Paginator
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import HttpResponse
from django.utils.translation import gettext_lazy as _
from django.views.generic import View

from flex_report import export_format, BaseExportFormat

from .app_settings import app_settings
from .templatetags.flex_report_filters import get_column_verbose_name
from .filterset import (
    generate_filterset_from_model,
    generate_quicksearch_filterset_from_model,
)
from .models import Template
from .utils import (
    generate_filterset_form,
    get_template_columns,
    get_choice_field_choices,
    string_to_q,
    FieldTypes,
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
        if (
            not (format_ := self.request.GET.get("format", "").lower())
            or format_ not in export_format.formats.keys()
        ):
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
            raise NotImplementedError(
                f"The wanted format '{self.export_format}' isn't handled."
            ) from e

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

    def get_filters(self):
        initials = self.get_initials()

        self.template_filters = generate_filterset_from_model(
            self.report_model, self.get_form_classes()
        )(self.template_object.filters or {})
        self.filters = generate_filterset_from_model(
            self.report_model,
            self.get_form_classes(),
        )(initials)
        
        self.quicksearch = generate_quicksearch_filterset_from_model(
            self.report_model, list(self.template_searchable_fields.values())
        )(initials)

    def apply_user_path(self):
        LOGICAL_OPERATORS = ["()", "&", "|", "!="]
        paths = self.template_object.model_user_path or {}
        path_func = getattr(
            self.report_model,
            app_settings.MODEL_USER_PATH_FUNC_NAME,
            lambda request: {},
        )

        accessed_paths = {
            path_name: path_dict
            for path_name, path in paths.items()
            if (
                path_dict := {
                    path: call(path_func, request=self.request).get(path_name)
                }
            ).get(path)
        }

        if not len(accessed_paths):
            return

        accessed_path = (
            list(accessed_paths.keys())[0]
            if len(accessed_paths) == 1
            else list(filter(partial(ne, "__all__"), accessed_paths))[0]
        )
        if accessed_path == "__all__":
            return

        accessed_path, accessed_val = accessed_paths[accessed_path].popitem()
        if not any(map(lambda op: op in accessed_path, LOGICAL_OPERATORS)):
            self.report_qs = self.report_qs.filter(
                **{accessed_path: accessed_val}
            ).distinct()
            return

        self.report_qs = self.report_qs.filter(
            string_to_q(accessed_path, accessed_val)
        ).distinct()

    def _format_used_filter(self, col_name, val):
        formats = {
            **{k: "بله" for k in ["true", "True", True]},
            **{k: "خیر" for k in ["false", "False", False]},
        }

        if formatted_val := formats.get(val, False):
            return formatted_val

        if choices := get_choice_field_choices(self.report_model, col_name):
            return dict(choices).get(val, val)

        return str(val)

    def used_filter_format(self, col_name, val):
        if isinstance(val, list):
            return ", ".join(
                map(
                    lambda v: self._format_used_filter(col_name, v),
                    val,
                )
            )

        return self._format_used_filter(col_name, val) or val

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)

        obj = self.template_object
        if not obj:
            self.have_template = False
            return

        self.report_model = obj.model.model_class()
        self.template_columns = get_template_columns(obj, as_dict=False)
        self.template_searchable_fields = get_template_columns(obj, searchables=True)

        self.get_filters()
        self.report_qs = (
            self.template_filters.qs.distinct()
            if self.template_filters.get_filters()
            else self.report_model.objects.all()
        )
        self.apply_user_path()

        if (
            all(
                map(
                    methodcaller("get_filters"),
                    [self.filters, self.quicksearch, self.template_filters],
                )
            )
            and all(
                map(
                    attrgetter("data"),
                    [self.filters, self.quicksearch, self.template_filters],
                )
            )
            and all(
                map(
                    methodcaller("is_valid"),
                    [self.filters, self.quicksearch, self.template_filters],
                )
            )
        ):
            self.report_qs = self.template_filters.qs.distinct().filter(
                pk__in=Subquery(
                    (
                        self.quicksearch.qs.distinct() & self.filters.qs.distinct()
                    ).values("pk")
                )
            )

            self.report_qs = self.report_qs.distinct().order_by(
                *self.report_model._meta.ordering or ["pk"]
            )

            cleaned_data = (
                self.quicksearch.form.cleaned_data | self.filters.form.cleaned_data
            )
            self.used_filters = self.get_used_filters(
                {
                    get_column_verbose_name(
                        self.report_model, k
                    ): self.used_filter_format(k, v)
                    for k, v in cleaned_data.items()
                    if bool(v)
                }
            )

    def get_used_filters(self, cleaned_data):
        return _(" and ").join(
            [
                f'{k} = {",".join(map(str, v)) if isinstance(v, list) else v}'
                for k, v in cleaned_data.items()
                if str(k).lower() != "search"
            ]
        )

    def _prepare_initial(self, initial):
        if initial.lower() in ["true", "false"]:
            return initial.lower() == "true"

        if (initial.startswith("[") and initial.endswith("]")) or (
            not initial.startswith("0") and initial.isnumeric()
        ):
            return ast.literal_eval(initial)
        
        return initial

    def get_initial_value(self, initial, *, key=""):
        initial = str(initial)

        if key.endswith("__in"):
            return list(map(self._prepare_initial, self.request.GET.getlist(key)))

        return self._prepare_initial(initial)

    def get_initials(self):
        return {
            k: self.get_initial_value(v, key=k)
            for k, v in self.request.GET.dict().items()
            if str(v)
            and v.strip() not in self.ignore_search_values
        }

    def get_form_classes(self):
        if not self.template_object:
            return []
        return [generate_filterset_form(self.report_model)]

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
            + sum(
                len(field.get_dynamic_obj().unpack_field())
                for field in self.template_columns.filter(
                    column_type=FieldTypes.dynamic
                ).only("pk")
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

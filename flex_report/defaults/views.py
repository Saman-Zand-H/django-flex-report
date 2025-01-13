import contextlib
from collections import OrderedDict

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic.detail import DetailView, SingleObjectMixin
from django.views.generic.edit import (
    CreateView,
    DeleteView,
    FormMixin,
    FormView,
    ModelFormMixin,
    UpdateView,
)
from django.views.generic.list import ListView

from ..app_settings import app_settings
from ..choices import TemplateTypeChoices
from ..filterset import generate_filterset_from_model
from ..forms import (
    generate_column_create_form,
    generate_report_create_form,
    generate_report_saved_filter_form,
    generate_template_create_form,
)
from ..mixins import QuerySetExportMixin, TablePageMixin, TemplateObjectMixin
from ..models import Column, Template, TemplateSavedFilter
from ..templatetags.flex_report_filters import get_column_verbose_name
from ..utils import (
    FieldTypes,
    clean_request_data,
    get_column_type,
    get_report_filename,
    increment_string_suffix,
    set_template_as_page_default,
)


class BaseView(LoginRequiredMixin, View):
    def get_object(self):
        qs = super().get_object(self.model.objects.all())
        if not qs:
            raise Http404
        with contextlib.suppress(Http404):
            filtered_qs = super().get_object()
            return filtered_qs

        raise PermissionDenied("You don't have permission to access this page")


class ColumnCreateView(BaseView, CreateView):
    model = Column
    fields = ["title", "searchable", "model"]
    template_name_suffix = "_form"
    success_url = reverse_lazy("flex_report:column:index")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return generate_column_create_form(form)

    def form_valid(self, form):
        cleaned_form = form.save(commit=False)
        cleaned_form.creator = self.request.user
        cleaned_form.save()
        return redirect(self.success_url)


class ColumnListView(BaseView, ListView):
    model = Column
    ordering = ("model_id", "title")


class ColumnUpdateView(BaseView, UpdateView):
    model = Column
    fields = ["title", "searchable", "model"]
    template_name_suffix = "_form"
    success_url = reverse_lazy("flex_report:column:index")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return generate_column_create_form(form)


class ColumnDeleteView(BaseView, DeleteView):
    model = Column
    success_url = reverse_lazy("flex_report:column:index")


class TemplateListView(BaseView, ListView):
    model = Template
    ordering = ("-modified_date",)


class TemplateDeleteView(BaseView, DeleteView):
    model = Template
    success_url = reverse_lazy("flex_report:template:index")


class TemplateCreateInitView(BaseView, CreateView):
    model = Template
    fields = ["title", "model", "page"]
    template_name_suffix = "_create"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return generate_template_create_form(form)

    def form_valid(self, form):
        form.instance.creator = self.request.user
        if form.cleaned_data["type"] != TemplateTypeChoices.page:
            form.instance.page = None

        form.instance.save(force_insert=True)
        self.object = form.instance

        return super(ModelFormMixin, self).form_valid(form)

    def get_success_url(self):
        return reverse("flex_report:template:create_complete", kwargs={"pk": self.object.pk})


class TemplateCloneView(BaseView, FormMixin, SingleObjectMixin):
    model = Template
    http_method_names = ["get"]

    @transaction.atomic
    def get(self, *args, **kwargs):
        object = self.get_object()
        clone = Template.objects.create(
            title=increment_string_suffix(object.title),
            creator=self.request.user,
            model=object.model,
            page=object.page,
            is_page_default=False,
            filters=object.filters,
            model_user_path=object.model_user_path,
            status=object.status,
            has_export=object.has_export,
        )
        clone.columns.add(*object.columns.all())
        return self.form_valid(None)

    def get_success_url(self):
        return self.request.headers.get("Referer", reverse_lazy("flex_report:template:index"))


class TemplateToggleDefaultView(BaseView, FormMixin, SingleObjectMixin):
    model = Template
    http_method_names = ["get"]

    def get(self, *args, **kwargs):
        object = self.get_object()
        if object.is_page_default:
            object.is_page_default = False
            object.save()
        else:
            set_template_as_page_default(object)
        return self.form_valid(None)

    def get_success_url(self):
        return reverse("flex_report:template:index")


class TemplateUpsertViewBase(BaseView, TemplateObjectMixin, DetailView):
    model = Template
    template_model = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.object = self.get_object()
        self.template_model = model = self.object.model.model_class()
        self.filter_class = generate_filterset_from_model(model, self.get_form_classes())
        self.filter = self.filter_class(self.get_initial())
        self.columns = self.template_object.columns.all()

    def get_initial(self):
        return self.request.POST

    def get_form_classes(self):
        return []

    def get_form_class(self):
        form = self.filter.get_form_class()
        old_clean = form.clean

        def clean(self):
            cleaned_data = old_clean(self)
            if hasattr(self, "instance") and cleaned_data.get("page") != self.instance.page:
                self.instance.is_page_default = False
            return cleaned_data

        form.clean = clean
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object"] = self.object
        context["filter"] = self.filter
        return context

    def form_valid(self, form):
        cleaned_form = super().form_valid(form)
        data = clean_request_data(form.cleaned_data, self.filter_class)
        self.object.filters = data["filters"]

        self.template_object.columns.clear()
        self.template_object.columns.add(*data["columns"])
        self.object.status = Template.Status.complete
        self.object.save()

        return cleaned_form


class TemplateCreateCompleteView(FormView, TemplateUpsertViewBase):
    template_name_suffix = "_create_complete"

    def get_context_data(self, **kwargs):
        return {
            "meta_fields_name": ["columns"],
            **super().get_context_data(**kwargs),
        }

    def get_form_classes(self):
        return [generate_report_create_form(self.template_model)]

    def get_success_url(self):
        return reverse("flex_report:template:index")

    def template_ready(self):
        return redirect("flex_report:template:edit", pk=self.template_object.pk)


class TemplateSavedFilterCreateView(FormView, TemplateUpsertViewBase):
    template_name_suffix = "_saved_filter_create"

    def get_form_classes(self):
        return [generate_report_saved_filter_form(self.template_object)]

    def get_success_url(self):
        return reverse("flex_report:template:edit", kwargs={"pk": self.template_object.pk})

    def form_valid(self, form):
        cleaned_form = super(TemplateUpsertViewBase, self).form_valid(form)
        data = clean_request_data(form.cleaned_data, self.filter_class)

        TemplateSavedFilter.objects.create(
            template=self.template_object,
            title=form.cleaned_data.get("title"),
            filters=data.get("filters"),
            creator=self.request.user if self.request.user.is_authenticated else None,
        )
        return cleaned_form


class TemplateUpdateView(UpdateView, TemplateUpsertViewBase):
    fields = ["title", "page"]
    template_name_suffix = "_form"

    def get_form_classes(self):
        return [
            super(TemplateUpsertViewBase, self).get_form_class(),
            generate_report_create_form(
                self.template_model, tuple(self.template_object.columns.values_list("id", flat=True))
            ),
        ]

    def get_initial(self):
        return self.request.POST or {
            **self.object.filters,
            **{f: getattr(self.object, f) for f in self.fields},
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update(
            {
                "object": self.object,
                "meta_fields_name": self.fields,
            }
        )

        return context

    def get_success_url(self):
        return reverse("flex_report:template:index")

    def template_not_ready(self):
        return redirect("flex_report:template:create_complete", pk=self.template_object.pk)


class ReportViewBase(TablePageMixin, BaseView, DetailView):
    model = Template
    is_page_table = False

    def get_template(self) -> Template:
        return self.get_object()


class ReportView(ReportViewBase):
    template_name = "flex_report/view_page.html"

    def template_not_ready(self):
        return redirect("flex_report:template:create_complete", pk=self.template_object.pk)


class GeneralQuerySetExportView(QuerySetExportMixin):
    pass


class ReportExportView(QuerySetExportMixin, ReportViewBase):
    def get(self, *args, **kwargs):
        if not self.template_object.has_export:
            return Http404("Export is not allowed for this template")

        self.export_filename = get_report_filename(self.template_object)

        columns = OrderedDict()
        for col in self.template_columns:
            if get_column_type(self.report_model, col.title) != FieldTypes.dynamic:
                columns[col.title] = str(get_column_verbose_name(self.report_model, col.title))
                continue

            columns.update(
                {subfield: str(subfield.get_verbose_name()) for subfield in col.get_dynamic_obj().unpack_field()}
            )

        self.export_headers = columns
        self.export_kwargs = getattr(
            self.report_model, app_settings.MODEL_EXPORT_KWARGS_FUNC_NAME, lambda *args, **kwargs: {}
        )()

        return super().get(*args, **kwargs)

    def get_export_qs(self):
        return self.get_report_qs()

    def template_not_ready(self):
        raise Http404

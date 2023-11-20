from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
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

from .app_settings import app_settings
from .choices import TemplateTypeChoices
from .filterset import generate_filterset_from_model
from .forms import (
    generate_column_create_form,
    generate_report_create_form,
    generate_template_create_form,
)
from .mixins import QuerySetExportMixin, TablePageMixin, TemplateObjectMixin
from .models import Column, Template
from .utils import (
    clean_request_data,
    get_report_filename,
    increment_string_suffix,
    set_template_as_page_default,
)

BaseView = app_settings.BASE_VIEW or type("BaseView", (LoginRequiredMixin, View), {})


class ColumnCreateView(CreateView, BaseView):
    model = Column
    fields = ["title", "searchable", "model"]
    template_name_suffix = "_form"
    success_url = reverse_lazy("report:column:index")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return generate_column_create_form(form)


column_create_view = ColumnCreateView.as_view()


class ColumnListView(ListView, BaseView):
    model = Column
    ordering = ("model_id", "title")


column_list_view = ColumnListView.as_view()


class ColumnUpdateView(UpdateView, BaseView):
    model = Column
    fields = ["title", "searchable", "model"]
    template_name_suffix = "_form"
    success_url = reverse_lazy("report:column:index")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return generate_column_create_form(form)


column_update_view = ColumnUpdateView.as_view()


class ColumnDeleteView(DeleteView, BaseView):
    model = Column
    success_url = reverse_lazy("report:column:index")


column_delete_view = ColumnDeleteView.as_view()


class TemplateListView(ListView, BaseView):
    model = Template
    ordering = ("-modified_date",)


template_list_view = TemplateListView.as_view()


class TemplateDeleteView(DeleteView, BaseView):
    model = Template
    success_url = reverse_lazy("report:template:index")


template_delete_view = TemplateDeleteView.as_view()


class TemplateCreateInitView(CreateView, BaseView):
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
        return reverse("report:template:create_complete", kwargs={"pk": self.object.pk})


template_create_init_view = TemplateCreateInitView.as_view()


class TemplateCloneView(FormMixin, SingleObjectMixin, BaseView):
    model = Template
    http_method_names = ["get"]

    def get(self, *args, **kwargs):
        object = self.get_object()
        object.pk = None
        object.title = increment_string_suffix(object.title)
        object.creator = self.request.user
        object.is_page_default = False
        object.save()
        return self.form_valid(None)

    def get_success_url(self):
        return reverse("report:template:index")


template_clone_view = TemplateCloneView.as_view()


class TemplateToggleDefaultView(FormMixin, SingleObjectMixin, BaseView):
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
        return reverse("report:template:index")


template_toggle_default_view = TemplateToggleDefaultView.as_view()


class TemplateUpsertViewBase(TemplateObjectMixin, DetailView, BaseView):
    model = Template
    template_model = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.object = self.get_object()
        self.template_model = model = self.object.model.model_class()
        self.filter_class = generate_filterset_from_model(
            model, self.get_form_classes()
        )
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
            if (
                hasattr(self, "instance")
                and cleaned_data.get("page") != self.instance.page
            ):
                self.instance.is_page_default = False
            return cleaned_data

        form.clean = clean
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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

    def get_form_classes(self):
        return [generate_report_create_form(self.template_model)]

    def get_success_url(self):
        return reverse("report:template:index")

    def template_ready(self):
        return redirect("report:template:edit", pk=self.template_object.pk)


template_create_complete_view = TemplateCreateCompleteView.as_view()


class TemplateUpdateView(UpdateView, TemplateUpsertViewBase):
    fields = ["title", "page"]
    template_name_suffix = "_form"

    def get_form_classes(self):
        return [
            super(TemplateUpsertViewBase, self).get_form_class(),
            generate_report_create_form(
                self.template_model,
                list(self.template_object.columns.values_list("id", flat=True)),
            ),
        ]

    def get_initial(self):
        return self.request.POST or {
            "columns": [*self.template_object.columns.values_list("id", flat=True)],
            **self.object.filters,
            **{f: getattr(self.object, f) for f in self.fields},
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context.update(
            {"object": self.object, "meta_fields_name": [*self.fields, "columns"]}
        )

        return context

    def get_success_url(self):
        return reverse("report:template:index")

    def template_not_ready(self):
        return redirect("report:template:create_complete", pk=self.template_object.pk)


template_update_view = TemplateUpdateView.as_view()


class ReportViewBase(TablePageMixin, DetailView, BaseView):
    model = Template
    is_page_table = False

    def get_template(self):
        return self.get_object()


class ReportView(ReportViewBase):
    template_name = "report/view_page.html"

    def template_not_ready(self):
        return redirect("report:template:create_complete", pk=self.template_object.pk)


report_view = ReportView.as_view()


class ReportExportView(QuerySetExportMixin, ReportViewBase):
    def get(self, *args, **kwargs):
        self.export_file_name = get_report_filename(self.template_object)

        columns = self.template_columns
        self.export_qs = self.report_qs
        self.export_columns = columns.values()
        self.export_headers = columns

        return super().get(*args, **kwargs)

    def template_not_ready(self):
        raise Http404


report_export_view = ReportExportView.as_view()

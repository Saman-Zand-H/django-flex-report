import contextlib
from operator import call
from collections import OrderedDict

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.core.exceptions import FieldError, PermissionDenied
from django.db.models import Q
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
    model_user_path_formset,
)
from .mixins import QuerySetExportMixin, TablePageMixin, TemplateObjectMixin
from .templatetags.flex_report_filters import get_column_verbose_name
from .models import Column, Template
from .utils import (
    clean_request_data,
    get_report_filename,
    increment_string_suffix,
    set_template_as_page_default,
    get_column_type,
    FieldTypes,
)


class BaseView(LoginRequiredMixin, View):
    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_superuser:
            return qs

        return qs.filter(
            Q(creator=self.request.user)
            | Q(users=self.request.user)
            | Q(groups__in=self.request.user.groups.all())
            | (Q(groups__isnull=True) & Q(users__isnull=True))
        ).distinct()

    def get_object(self):
        qs = super().get_object(self.model.objects.all())
        if not qs:
            raise Http404
        with contextlib.suppress(Http404):
            filtered_qs = super().get_object()
            return filtered_qs

        raise PermissionDenied("You don't have permission to access this page")


BaseView = app_settings.BASE_VIEW or BaseView


class ColumnCreateView(BaseView, CreateView):
    model = Column
    fields = ["title", "searchable", "model", "users", "groups"]
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


column_create_view = ColumnCreateView.as_view()


class ColumnListView(BaseView, ListView):
    model = Column
    ordering = ("model_id", "title")


column_list_view = ColumnListView.as_view()


class ColumnUpdateView(BaseView, UpdateView):
    model = Column
    fields = ["title", "searchable", "model", "users", "groups"]
    template_name_suffix = "_form"
    success_url = reverse_lazy("flex_report:column:index")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        return generate_column_create_form(form)


column_update_view = ColumnUpdateView.as_view()


class ColumnDeleteView(BaseView, DeleteView):
    model = Column
    success_url = reverse_lazy("flex_report:column:index")


column_delete_view = ColumnDeleteView.as_view()


class TemplateListView(BaseView, ListView):
    model = Template
    ordering = ("-modified_date",)


template_list_view = TemplateListView.as_view()


class TemplateDeleteView(BaseView, DeleteView):
    model = Template
    success_url = reverse_lazy("flex_report:template:index")


template_delete_view = TemplateDeleteView.as_view()


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
        return reverse(
            "flex_report:template:create_complete", kwargs={"pk": self.object.pk}
        )


template_create_init_view = TemplateCreateInitView.as_view()


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
        return reverse("flex_report:template:index")


template_clone_view = TemplateCloneView.as_view()


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


template_toggle_default_view = TemplateToggleDefaultView.as_view()


class TemplateUpsertViewBase(BaseView, TemplateObjectMixin, DetailView):
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
        context["object"] = self.object
        context["model_user_path"] = model_user_path_formset()
        context["filter"] = self.filter
        return context

    def filter_model_user_path(self, model_user_path):
        val = self.request.user
        if hasattr(self.object.model, app_settings.MODEL_USER_PATH_FUNC_NAME):
            val = call(
                getattr(self.object.model, app_settings.MODEL_USER_PATH_FUNC_NAME),
                {"request": self.request},
            )

        try:
            self.object.model.model_class().objects.filter(**{model_user_path: val})
            self.object.model_user_path = model_user_path
        except FieldError:
            pass

    def form_valid(self, form):
        cleaned_form = super().form_valid(form)
        data = clean_request_data(form.cleaned_data, self.filter_class)
        model_user_path_forms = model_user_path_formset(data=self.request.POST)
        if model_user_path_forms.is_valid():
            model_user_path = "__".join(
                [i.cleaned_data.get("title", "") for i in model_user_path_forms]
            )
            self.filter_model_user_path(model_user_path)
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
            "meta_fields_name": ["columns", "users", "groups"],
            **super().get_context_data(**kwargs),
        }

    def get_form_classes(self):
        return [generate_report_create_form(self.template_model)]

    def get_success_url(self):
        return reverse("flex_report:template:index")

    def template_ready(self):
        return redirect("flex_report:template:edit", pk=self.template_object.pk)


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
            {
                "object": self.object,
                "meta_fields_name": self.fields,
            }
        )

        return context

    def get_success_url(self):
        return reverse("flex_report:template:index")

    def template_not_ready(self):
        return redirect(
            "flex_report:template:create_complete", pk=self.template_object.pk
        )


template_update_view = TemplateUpdateView.as_view()


class ReportViewBase(BaseView, TablePageMixin, DetailView):
    model = Template
    is_page_table = False

    def get_template(self):
        return self.get_object()


class ReportView(ReportViewBase):
    template_name = "flex_report/view_page.html"

    def template_not_ready(self):
        return redirect(
            "flex_report:template:create_complete", pk=self.template_object.pk
        )


report_view = ReportView.as_view()


class GeneralQuerySetExportView(QuerySetExportMixin):
    pass


general_qs_export_view = GeneralQuerySetExportView.as_view()


class ReportExportView(QuerySetExportMixin, ReportViewBase):
    def get(self, *args, **kwargs):
        self.export_file_name = get_report_filename(self.template_object)

        columns = OrderedDict()
        for col in self.template_columns:
            if get_column_type(self.report_model, col.title) != FieldTypes.dynamic:
                columns[col.title] = str(
                    get_column_verbose_name(self.report_model, col.title)
                )
                continue

            columns.update(
                {
                    subfield: str(subfield.get_verbose_name())
                    for subfield in col.get_dynamic_obj().unpack_field()
                }
            )

        self.export_qs = self.report_qs
        self.export_headers = columns

        return super().get(*args, **kwargs)

    def template_not_ready(self):
        raise Http404


report_export_view = ReportExportView.as_view()

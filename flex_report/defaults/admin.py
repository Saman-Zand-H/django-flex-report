from django_better_admin_arrayfield.admin.mixins import DynamicArrayMixin

from django import forms
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.utils.html import format_html

from ..models import (
    Column,
    TableButton,
    TableButtonColor,
    TablePage,
    Template,
    TemplateSavedFilter,
)
from ..utils import fields_join, get_table_page_choices, get_table_page_optional_choices


class TableButtonColorAdmin(admin.ModelAdmin):
    list_display = [
        TableButtonColor.title.field.name,
        TableButtonColor.color.field.name,
    ]
    search_fields = [
        TableButtonColor.title.field.name,
        TableButtonColor.color.field.name,
    ]


class TemplateAdmin(admin.ModelAdmin):
    list_display = [
        Template.title.field.name,
        Template.creator.field.name,
        Template.model.field.name,
        Template.created_date.field.name,
        Template.modified_date.field.name,
        Template.status.field.name,
        Template.is_page_default.field.name,
        Template.columns_count.fget.__name__,
    ]
    raw_id_fields = [
        Template.creator.field.name,
        Template.model.field.name,
    ]
    search_fields = [
        Template.title.field.name,
        fields_join(Template.model.field.name, ContentType.model.field.name),
    ]
    list_filter = [
        Template.is_page_default.field.name,
        Template.status.field.name,
    ]


class TablePageAdmin(admin.ModelAdmin):
    @admin.display(description="URL Name")
    def url(self, obj):
        return format_html(f"<a href='{obj.url}'>{obj.url_name}</a>")

    readonly_fields = (url.__name__,)
    list_display = (TablePage.title.field.name, url.__name__)
    search_fields = readonly_fields + list_display

    def get_form(self, request, obj=None, **kwargs):
        kwargs["widgets"] = {TablePage.url_name.field.name: forms.Select(choices=get_table_page_choices())}
        return super().get_form(request, obj, **kwargs)

    def get_readonly_fields(self, _, obj=None):
        return self.readonly_fields if obj else ()


class ColumnAdmin(admin.ModelAdmin):
    list_display = [
        Column.title.field.name,
        Column.model.field.name,
    ]
    search_fields = [
        Column.title.field.name,
        fields_join(Column.model.field.name, ContentType.model.field.name),
    ]
    list_filter = [
        Column.searchable.field.name,
        Column.column_type.field.name,
    ]


class TableButtonAdmin(admin.ModelAdmin, DynamicArrayMixin):
    @admin.display(description="URL Name")
    def url(self, obj):
        return format_html(f"<a href='{obj.url}'>{obj.url_name}</a>")

    list_readonly_fields = [url.__name__, TableButton.title.field.name]
    list_display = [
        TableButton.title.field.name,
        TableButton.display_name.field.name,
        TableButton.icon.field.name,
        url.__name__,
        TableButton.color.field.name,
    ]
    search_fields = [
        TableButton.url_name.field.name,
        TableButton.title.field.name,
        TableButton.display_name.field.name,
        TableButton.color.field.name,
    ]
    list_editable = list(set(list_display) - set(list_readonly_fields))

    def get_form(self, request, obj=None, **kwargs):
        kwargs["widgets"] = {TableButton.url_name.field.name: forms.Select(choices=get_table_page_optional_choices())}
        return super().get_form(request, obj, **kwargs)

    def get_readonly_fields(self, _, obj=None):
        return self.readonly_fields if obj else ()


class TemplateSavedFilterAdmin(admin.ModelAdmin):
    list_display = [
        TemplateSavedFilter.template.field.name,
        TemplateSavedFilter.title.field.name,
        TemplateSavedFilter.creator.field.name,
        TemplateSavedFilter.created.field.name,
        TemplateSavedFilter.modified.field.name,
    ]
    autocomplete_fields = [
        TemplateSavedFilter.template.field.name,
        TemplateSavedFilter.creator.field.name,
    ]
    search_fields = [
        TemplateSavedFilter.title.field.name,
        fields_join(TemplateSavedFilter.template.field.name, Template.title.field.name),
    ]

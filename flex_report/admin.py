from django_better_admin_arrayfield.admin.mixins import DynamicArrayMixin

from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .models import Column, TableButton, TablePage, Template, TableButtonColor
from .utils import get_table_page_choices, get_table_page_optional_choices


@admin.register(TableButtonColor)
class TableButtonColorAdmin(admin.ModelAdmin):
    list_display = ["title", "color"]
    search_fields = ["title", "color"]


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "creator",
        "model",
        "created_date",
        "modified_date",
        "status",
        "is_page_default",
        "columns_count",
    ]
    raw_id_fields = ["creator"]
    search_fields = ["title", "creator", "model"]
    list_filter = ["is_page_default", "status"]


@admin.register(TablePage)
class TablePageAdmin(admin.ModelAdmin):
    readonly_fields = ("url",)
    list_display = ("title", "url")
    search_fields = readonly_fields + list_display

    @admin.display(description="URL Name")
    def url(self, obj):
        return format_html(f"<a href='{obj.url}'>{obj.url_name}</a>")

    def get_form(self, request, obj=None, **kwargs):
        kwargs["widgets"] = {"url_name": forms.Select(choices=get_table_page_choices())}
        return super().get_form(request, obj, **kwargs)

    def get_readonly_fields(self, _, obj=None):
        return self.readonly_fields if obj else ()


@admin.register(Column)
class ColumnAdmin(admin.ModelAdmin):
    search_fields = ["title"]
    list_display = ["title", "model"]


@admin.register(TableButton)
class TableButtonAdmin(admin.ModelAdmin, DynamicArrayMixin):
    list_readonly_fields = ["url", "title"]
    list_display = ["title", "display_name", "icon", "url", "color"]
    search_fields = ["url", "color"]
    list_editable = list(set(list_display) - set(list_readonly_fields))

    @admin.display(description="URL Name")
    def url(self, obj):
        return format_html(f"<a href='{obj.url}'>{obj.url_name}</a>")

    def get_form(self, request, obj=None, **kwargs):
        kwargs["widgets"] = {
            "url_name": forms.Select(choices=get_table_page_optional_choices())
        }
        return super().get_form(request, obj, **kwargs)

    def get_readonly_fields(self, _, obj=None):
        return self.readonly_fields if obj else ()

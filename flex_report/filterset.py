from functools import reduce
from operator import or_

import django_filters
from django_filters.filters import LOOKUP_SEP
from django_filters import FilterSet as FilterSetBase

from django_filters.conf import DEFAULTS
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from .app_settings import app_settings
from .utils import (
    generate_filterset_form,
    get_fields_lookups,
    get_model_filters,
    get_quicksearch_fields_lookups,
    get_annotated_fields_lookups,
    get_annotated_fields,
    get_field,
)


class FilterSetMeta:
    def __init__(self, model, fields=[]):
        self.model = model
        self.searchable_fields = fields
        
        
class CustomModelMultipleChoiceFilter(django_filters.ModelMultipleChoiceFilter):
    def get_filter_predicate(self, v):
        name = self.field_name
        if name:
            name = LOOKUP_SEP.join([name, self.lookup_expr])
        predicate = super().get_filter_predicate(v)
        predicate[name] = [v]
        return predicate


class FilterSet(FilterSetBase):
    form_classes = []
    
    @classmethod
    def get_fields(cls):
        model = cls._meta.model
        fields, exclude = get_model_filters(model)
        cls._meta.fields = fields and get_fields_lookups(model, fields)
        cls._meta.exclude = exclude and get_fields_lookups(model, exclude)
        
        for annotation_name, field_type in get_annotated_fields(model).items():
            annotation_field = get_field(model, annotation_name).output_field
            for lookup in get_annotated_fields_lookups(model).get(annotation_name, ["exact"]):
                field_name = LOOKUP_SEP.join([annotation_name, lookup])
                defaults = {
                    "field_name": annotation_name,
                    "label": " ".join(str(DEFAULTS.get("VERBOSE_LOOKUPS", {}).get(field_name_part, field_name_part)) for field_name_part in field_name.split(LOOKUP_SEP)).replace("_", " ").title(),
                    "lookup_expr": lookup,
                }
                filter_class, opts = cls.filter_for_lookup(annotation_field, field_type)
                defaults.update(opts)
                cls.declared_filters[field_name] = filter_class(**defaults)
                
        return super().get_fields()

    @classmethod
    def filter_for_lookup(cls, f, lookup_type):
        filter_, opts = super().filter_for_lookup(f, lookup_type)

        match filter_:
            case django_filters.ModelMultipleChoiceFilter if "choices" in opts:
                filter_ = django_filters.MultipleChoiceFilter
                opts.update(widget=filter_.field_class.widget())
            case django_filters.ModelChoiceFilter:
                filter_ = django_filters.ModelMultipleChoiceFilter
                opts.update(widget=filter_.field_class.widget())
            case _ if issubclass(filter_, django_filters.BaseInFilter):
                filter_ = CustomModelMultipleChoiceFilter
                opts.update(widget=filter_.field_class.widget())
        return filter_, opts

    def get_form_class(self):
        base_form_class = super().get_form_class()
        return (
            generate_filterset_form(
                self._meta.model,
                form_classes=self.form_classes + [base_form_class],
            )
            if self.form_classes
            else base_form_class
        )


class QuicksearchFilterset(FilterSet):
    search = django_filters.CharFilter(
        method="quick_search",
        label=_("Quick Search"),
        widget=forms.TextInput(
            attrs={
                "hx-trigger": "keyup changed delay:700ms",
                "onkeypress": "return event.keyCode != 13;",
                "class": "form-control",
            }
        ),
    )

    def quick_search(self, queryset, name, value):
        if not value.strip():
            return queryset
        fields = self.Meta.searchable_fields or []
        q_object = reduce(
            or_, [(Q(**{f"{field}__icontains": value})) for field in fields]
        )
        return queryset.filter(q_object) if q_object else queryset.none()

    @classmethod
    def get_fields(cls):
        model = cls._meta.model
        _, exclude = get_model_filters(model)
        cls._meta.fields = ["search"]
        cls._meta.exclude = exclude and get_quicksearch_fields_lookups(model, exclude)
        return super(FilterSet, cls).get_fields()


def generate_quicksearch_filterset_from_model(model, fields=[], form_classes=None):
    return type(
        f"{getattr(model, '__name__', '')}DynamicQuicksearchFilterset",
        (QuicksearchFilterset,),
        {"Meta": FilterSetMeta(model, fields), "form_classes": form_classes},
    )


def generate_filterset_from_model(model, form_classes=None):
    if form_classes is None:
        form_classes = []

    return type(
        f"{getattr(model, '__name__', '')}DynamicFilterSet",
        (app_settings.FILTERSET_CLASS,),
        {"Meta": FilterSetMeta(model), "form_classes": form_classes},
    )

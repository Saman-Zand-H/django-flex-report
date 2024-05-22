from django import forms
from collections import OrderedDict
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext as _
from djangoformsetjs.utils import formset_media_js

from .app_settings import app_settings, import_callable
from .choices import TemplateTypeChoices
from .utils import generate_filterset_form, get_model_columns, get_report_models


class ModelUserPathForm(forms.Form):
    title = forms.CharField(label=_("Title"), max_length=100)

    class Media:
        js = formset_media_js


model_user_path_formset = forms.formset_factory(
    ModelUserPathForm, extra=1, max_num=20, can_delete=True
)


class OrderedModelMultipleChoiceField(forms.MultipleChoiceField):
    def _fix_choices(self, values):
        choices_dict = OrderedDict(self.choices)
        values = list(values or [])
        new_choices = map(int, values + list(dict(self.choices).keys()))
        
        self.choices = (
            [(int(v), choices_dict.get(int(v))) for v in new_choices]
            or self.choices
        )

    def prepare_value(self, value):
        value = value or self.initial
        
        self._fix_choices(value)
        return super().prepare_value(value)

    def clean(self, value):
        value = value or self.initial
        
        qs = super().clean(value)
        self._fix_choices(qs)
        return qs


def get_form(form_name: str):
    try:
        return import_callable(app_settings.FORMS[form_name])
    except KeyError:
        raise ImproperlyConfigured(_("form_name isn't defined in settings."))


def generate_report_create_form(model, col_initial=None):
    choices = list((k, v) for k, v in get_model_columns(model, verbose=True).items())
    print(col_initial)
    
    return generate_filterset_form(
        model,
        fields={
            "columns": OrderedModelMultipleChoiceField(
                widget=forms.MultipleChoiceField.widget(
                    attrs={"class": "selectize-field"}
                ),
                required=True,
                label=_("Columns"),
                initial=col_initial,
                choices=choices,
            ),
        },
    )


def generate_column_create_form(form):
    form.fields["model"].queryset = ContentType.objects.filter(
        pk__in=[m.pk for m in get_report_models().values()]
    )
    return get_form("CREATE_COLUMN")(form)


def generate_template_create_form(form, order=None):
    form.fields["model"].queryset = ContentType.objects.filter(
        pk__in=[m.pk for m in get_report_models().values()]
    )
    form.fields["type"] = forms.ChoiceField(
        label="نوع قالب",
        choices=TemplateTypeChoices.choices,
        initial=TemplateTypeChoices.report.value,
    )
    return get_form("CREATE_TEMPLATE")(form)

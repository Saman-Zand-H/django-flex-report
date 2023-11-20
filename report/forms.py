from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext as _

from .app_settings import app_settings
from .choices import TemplateTypeChoices
from .utils import generate_filterset_form, get_model_columns, get_report_models, import_callable


class OrderedModelMultipleChoiceField(forms.MultipleChoiceField):
    def _fix_choices(self, values):
        self.choices = values or self.choices

    def prepare_value(self, value):
        self._fix_choices(value)
        return super().prepare_value(value)

    def clean(self, value):
        qs = super().clean(value)
        self._fix_choices(qs)
        return qs


def get_form(form_name: str):
    try:
        return import_callable(app_settings.FORMS[form_name])
    except KeyError:
        raise ImproperlyConfigured(_("form_name isn't defined in settings."))


def generate_report_create_form(model, col_initial=None):
    return generate_filterset_form(
        model,
        fields={
            "columns": forms.MultipleChoiceField(
                widget=forms.MultipleChoiceField.widget(attrs={"id": "columns"}),
                required=True,
                label=_("columns"),
                initial=col_initial,
                choices=list(get_model_columns(model).items()),
            )
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

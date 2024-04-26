from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F
from django.template.defaultfilters import truncatechars
from django.utils.translation import gettext_lazy as _
from django_better_admin_arrayfield.models.fields import ArrayField
from django_jalali.db.models import jDateTimeField
from sortedm2m.fields import SortedManyToManyField

from flex_report import report_model, dynamic_field, BaseDynamicField

from .managers import ColumnManager
from .utils import get_view_name_url, is_field_valid, get_column_type
from .constants import FieldTypes


class TablePage(models.Model):
    title = models.CharField(max_length=200, verbose_name=_("Title"))
    url_name = models.CharField(max_length=200, verbose_name=_("URL Name"))
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="accessed_pages",
        blank=True,
    )
    groups = models.ManyToManyField(
        Group,
        related_name="accessed_pages",
        blank=True,
    )

    @property
    def url(self):
        url = get_view_name_url(self.url_name)
        return f"/{url}" if url else ""

    def __str__(self):
        return f"{self.title}"


class Column(models.Model):
    class COLUMN_TYPES(models.TextChoices):
        model = "model", _("Model")
        dynamic = "dynamic", _("Dynamic")

    title = models.CharField(verbose_name=_("Title"), max_length=150, db_index=True)
    searchable = models.BooleanField(default=False)
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_columns",
        blank=True,
        null=True,
    )
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="accessed_columns",
        blank=True,
    )
    groups = models.ManyToManyField(
        Group,
        related_name="accessed_columns",
        blank=True,
    )
    model = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="flex_columns",
    )
    column_type = models.CharField(
        choices=COLUMN_TYPES.choices,
        verbose_name=_("Column Type"),
        default=COLUMN_TYPES.model,
    )

    objects = ColumnManager()

    def __str__(self):
        return f"{self.model}: {self.title}"

    def get_dynamic_obj(self) -> None | BaseDynamicField:
        if self.column_type != self.COLUMN_TYPES.dynamic:
            return

        return dynamic_field.get_by_slug(self.title)

    def clean(self):
        if (
            (column_type := get_column_type(self.model, self.title))
            == FieldTypes.dynamic
            and (dynamic_model := self.get_dynamic_obj().model)
            and self.model.model_class() != dynamic_model
        ):
            raise ValidationError(
                {
                    "title": _(
                        "This dynamic column has been registered for another model, which is %(title)s."
                    )
                    % {"title": dynamic_model}
                }
            )

        if column_type and not is_field_valid(self.model.model_class(), self.title):
            raise ValidationError(
                {
                    "title": _(
                        "The field name is not valid. It should be a field on the model."
                    )
                }
            )
        if self.searchable and not is_field_valid(
            self.model.model_class(), self.title, as_filter=True
        ):
            raise ValidationError(
                {
                    "searchable": _(
                        "This field is a non-db field and is not allowed to be used for searching."
                    )
                }
            )

    class Meta:
        unique_together = [("model", "title")]


class TableButtonColor(models.Model):
    title = models.CharField(
        verbose_name=_("title"),
        max_length=50,
        default="",
        unique=True,
    )
    color = models.CharField(max_length=50, verbose_name=_("Color"))

    def __str__(self):
        return f"{self.title} - {self.color}"


class TableButton(models.Model):
    title = models.CharField(
        verbose_name=_("title"),
        max_length=50,
        default="",
        unique=True,
    )
    icon = models.CharField(
        verbose_name=_("Icon"),
        max_length=30,
        blank=True,
        null=True,
    )
    display_name = models.CharField(
        verbose_name=_("Display Name"),
        max_length=40,
        blank=True,
        null=True,
    )
    event = models.CharField(
        max_length=50,
        verbose_name=_("Event"),
        blank=True,
        null=True,
    )
    exposed_fields = ArrayField(
        models.CharField(max_length=50),
        verbose_name=_("Exposed Fields"),
        default=list,
        blank=True,
    )
    url_name = models.CharField(
        max_length=200,
        verbose_name=_("URL Name"),
        blank=True,
        null=True,
    )
    url_kwargs = models.JSONField(
        verbose_name=_("URL Parameters"),
        default=dict,
        blank=True,
    )
    query_strings = models.JSONField(
        verbose_name=_("Query String"),
        default=dict,
        blank=True,
    )
    color = models.ForeignKey(
        TableButtonColor,
        on_delete=models.SET_NULL,
        null=True,
        related_name="buttons",
    )
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="accessed_buttons",
        blank=True,
    )
    groups = models.ManyToManyField(
        Group,
        related_name="accessed_buttons",
        blank=True,
    )

    @property
    def url(self):
        url = get_view_name_url(self.url_name)
        return f"/{url}" if url else ""

    def clean(self):
        if not (self.title or self.icon):
            raise ValidationError({"title": "Title or icon is required."})

        if not (bool(self.event) ^ bool(self.url_name)):
            raise ValidationError(
                {"event": "Filling either of Event or URL Name is required."}
            )

    def __str__(self):
        return (
            f"{self.title} - {self.color.title} -> "
            f"{self.url_name or truncatechars(self.event, 15)}"
        )


@report_model.register
class Template(models.Model):
    class Status(models.TextChoices):
        complete = "c", _("Completed")
        pending = "p", _("Pending")

    title = models.CharField(max_length=200, verbose_name=_("Title"))
    filters = models.JSONField(verbose_name=_("Filters"), default=dict, blank=True)
    columns = SortedManyToManyField(
        Column,
        blank=True,
        limit_choices_to={"model": F("model")},
        verbose_name=_("Columns"),
    )
    buttons = SortedManyToManyField(
        TableButton, blank=True, related_name="templates", verbose_name=_("Buttons")
    )
    has_export = models.BooleanField(default=True, verbose_name=_("Has Export"))
    model_user_path = models.JSONField(
        max_length=200,
        verbose_name=_("Model User Path"),
        blank=True,
        null=True,
        default=dict,
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="templates",
    )
    model = models.ForeignKey(
        ContentType,
        verbose_name=_("Model"),
        on_delete=models.CASCADE,
        related_name="flex_templates",
    )
    page = models.ForeignKey(
        TablePage,
        verbose_name=_("Page"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    is_page_default = models.BooleanField(
        verbose_name=_("Page Default"),
        default=False,
    )
    created_date = jDateTimeField(
        auto_now_add=True,
        verbose_name=_("Created Date"),
    )
    users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="accessed_templates",
        blank=True,
    )
    groups = models.ManyToManyField(
        Group,
        related_name="accessed_templates",
        blank=True,
    )
    modified_date = jDateTimeField(auto_now=True, verbose_name=_("Modified Date"))
    status = models.CharField(
        max_length=1,
        verbose_name=_("Status"),
        choices=Status.choices,
        default=Status.pending,
    )

    @property
    def is_completed(self):
        return self.status == self.Status.complete

    @property
    def columns_count(self):
        return self.columns.count()

    @property
    def filters_count(self):
        return len(list(filter(None, (self.filters or {}).values())))

    @property
    def user_fullname(self):
        return getattr(self.creator, "full_name", _("Not Set"))

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = _("Template")
        verbose_name_plural = _("Templates")

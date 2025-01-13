from django.db import models
from django.utils.translation import gettext_lazy as _


class TemplateTypeChoices(models.TextChoices):
    report = "report", _("This template is related to a report")
    page = "page", _("The template is related to one of the pages in the system")

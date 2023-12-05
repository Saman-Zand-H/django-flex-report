from django.db import models


class TemplateTypeChoices(models.TextChoices):
    report = "report", "این قالب مربوط به یک گزارش است"
    page = "page", "قالب مربوط به یکی از صفحات موجود سیستم است"

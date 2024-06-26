# Generated by Django 4.2 on 2023-11-22 03:44

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django_better_admin_arrayfield.models.fields
import django_jalali.db.models
import sortedm2m.fields


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Column",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        db_index=True, max_length=150, verbose_name="title"
                    ),
                ),
                ("searchable", models.BooleanField(default=False)),
                (
                    "model",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="contenttypes.contenttype",
                    ),
                ),
            ],
            options={
                "unique_together": {("model", "title")},
            },
        ),
        migrations.CreateModel(
            name="TableButton",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        default="", max_length=50, unique=True, verbose_name="title"
                    ),
                ),
                (
                    "icon",
                    models.CharField(
                        blank=True, max_length=30, null=True, verbose_name="Icon"
                    ),
                ),
                (
                    "display_name",
                    models.CharField(
                        blank=True,
                        max_length=40,
                        null=True,
                        verbose_name="Display Name",
                    ),
                ),
                (
                    "event",
                    models.CharField(
                        blank=True, max_length=50, null=True, verbose_name="Event"
                    ),
                ),
                (
                    "exposed_fields",
                    django_better_admin_arrayfield.models.fields.ArrayField(
                        base_field=models.CharField(max_length=50),
                        blank=True,
                        default=list,
                        size=None,
                        verbose_name="Exposed Fields",
                    ),
                ),
                (
                    "url_name",
                    models.CharField(
                        blank=True, max_length=200, null=True, verbose_name="URL Name"
                    ),
                ),
                (
                    "url_kwargs",
                    models.JSONField(
                        blank=True, default=dict, verbose_name="URL Parameters"
                    ),
                ),
                (
                    "color",
                    models.CharField(
                        choices=[
                            ("btn-green", "Success"),
                            ("btn-azure", "Azure"),
                            ("btn-blue", "Primary"),
                            ("btn-pink", "Pink"),
                            ("btn-purple", "Purple"),
                            ("btn-red", "Danger"),
                            ("btn-orange", "Orange"),
                            ("btn-yellow", "Warning"),
                            ("btn-lime", "Lime"),
                            ("btn-teal", "Teal"),
                            ("btn-cyan", "Cyan"),
                            ("btn-vk", "Secondary"),
                            ("btn-github", "Dark"),
                        ],
                        max_length=50,
                        verbose_name="Color",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="TablePage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=200, verbose_name="Title")),
                ("url_name", models.CharField(max_length=200, verbose_name="URL Name")),
            ],
        ),
        migrations.CreateModel(
            name="Template",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=200, verbose_name="Title")),
                (
                    "filters",
                    models.JSONField(blank=True, default=dict, verbose_name="Filters"),
                ),
                (
                    "has_export",
                    models.BooleanField(default=True, verbose_name="Has Export"),
                ),
                (
                    "is_page_default",
                    models.BooleanField(default=False, verbose_name="Page Default"),
                ),
                (
                    "created_date",
                    django_jalali.db.models.jDateTimeField(
                        auto_now_add=True, verbose_name="Created Date"
                    ),
                ),
                (
                    "modified_date",
                    django_jalali.db.models.jDateTimeField(
                        auto_now=True, verbose_name="Modified Date"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("c", "Completed"), ("p", "Pending")],
                        default="p",
                        max_length=1,
                        verbose_name="Status",
                    ),
                ),
                (
                    "buttons",
                    models.ManyToManyField(
                        blank=True,
                        related_name="templates",
                        to="flex_report.tablebutton",
                        verbose_name="Buttons",
                    ),
                ),
                (
                    "columns",
                    sortedm2m.fields.SortedManyToManyField(
                        blank=True,
                        help_text=None,
                        limit_choices_to={"model": models.F("model")},
                        to="flex_report.column",
                    ),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="templates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "model",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="contenttypes.contenttype",
                        verbose_name="Model",
                    ),
                ),
                (
                    "page",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="flex_report.tablepage",
                        verbose_name="Page",
                    ),
                ),
            ],
            options={
                "verbose_name": "Template",
                "verbose_name_plural": "Templates",
            },
        ),
    ]

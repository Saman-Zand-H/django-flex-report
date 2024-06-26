# Generated by Django 5.0 on 2024-02-15 12:31

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("flex_report", "0011_alter_template_model_user_path"),
    ]

    operations = [
        migrations.CreateModel(
            name="TableButtonColor",
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
                ("color", models.CharField(max_length=50, verbose_name="Color")),
            ],
        ),
        migrations.AlterField(
            model_name="tablebutton",
            name="color",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="buttons",
                to="flex_report.tablebuttoncolor",
            ),
        ),
    ]

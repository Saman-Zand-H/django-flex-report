# Generated by Django 5.0 on 2024-02-08 12:34

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("flex_report", "0010_alter_column_model_alter_template_model_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="template",
            name="model_user_path",
            field=models.JSONField(
                blank=True,
                default=dict,
                max_length=200,
                null=True,
                verbose_name="Model User Path",
            ),
        ),
    ]

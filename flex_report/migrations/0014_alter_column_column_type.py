# Generated by Django 5.0.4 on 2024-04-10 17:59

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("flex_report", "0013_column_column_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="column",
            name="column_type",
            field=models.CharField(
                choices=[("dynamic", "Dynamic"), ("model", "model")],
                default="model",
                max_length=10,
                verbose_name="Column Type",
            ),
        ),
    ]

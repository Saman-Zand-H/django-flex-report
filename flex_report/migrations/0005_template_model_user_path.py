# Generated by Django 4.2.7 on 2023-12-10 11:43

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("flex_report", "0004_column_creator"),
    ]

    operations = [
        migrations.AddField(
            model_name="template",
            name="model_user_path",
            field=models.CharField(
                blank=True, max_length=200, null=True, verbose_name="Model User Path"
            ),
        ),
    ]

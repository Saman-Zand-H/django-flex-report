# Generated by Django 5.0.4 on 2024-04-10 18:02

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("flex_report", "0014_alter_column_column_type"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="column",
            name="column_type",
        ),
    ]
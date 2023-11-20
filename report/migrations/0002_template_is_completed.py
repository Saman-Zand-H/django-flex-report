# Generated by Django 5.0b1 on 2023-11-14 01:20

import django.db.models.lookups
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("report", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="template",
            name="is_completed",
            field=models.GeneratedField(
                db_persist=True,
                expression=django.db.models.lookups.Exact(
                    models.F("status"), models.Value("c")
                ),
            ),
        ),
    ]

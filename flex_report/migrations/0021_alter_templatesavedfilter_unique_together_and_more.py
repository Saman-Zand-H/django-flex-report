# Generated by Django 5.1.4 on 2025-01-12 21:01

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('flex_report', '0020_templatesavedfilter_created_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='templatesavedfilter',
            unique_together={('title', 'template')},
        ),
        migrations.AlterField(
            model_name='templatesavedfilter',
            name='creator',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='saved_filters', to=settings.AUTH_USER_MODEL),
        ),
        migrations.RemoveField(
            model_name='templatesavedfilter',
            name='slug',
        ),
    ]

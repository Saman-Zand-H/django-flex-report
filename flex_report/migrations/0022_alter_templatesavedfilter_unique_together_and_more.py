# Generated by Django 5.1.4 on 2025-01-12 21:11

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('flex_report', '0021_alter_templatesavedfilter_unique_together_and_more'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='templatesavedfilter',
            unique_together={('title', 'template')},
        ),
        migrations.AddField(
            model_name='templatesavedfilter',
            name='slug',
            field=models.SlugField(default='default', max_length=100, verbose_name='Slug'),
            preserve_default=False,
        ),
        migrations.AlterUniqueTogether(
            name='templatesavedfilter',
            unique_together={('slug', 'template'), ('title', 'template')},
        ),
    ]
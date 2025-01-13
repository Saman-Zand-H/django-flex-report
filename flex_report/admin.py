from django.contrib import admin

from .app_settings import app_settings
from .models import (
    Column,
    TableButton,
    TableButtonColor,
    TablePage,
    Template,
    TemplateSavedFilter,
)

for model in [Column, TableButton, TableButtonColor, TablePage, Template, TemplateSavedFilter]:
    admin.site.register(model, app_settings.MODEL_ADMINS[model])

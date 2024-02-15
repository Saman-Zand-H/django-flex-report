from dataclasses import dataclass

from django.db.models.fields.files import FieldFile
from django.utils.translation import gettext_lazy as _


@dataclass
class FieldFileAbsoluteURL:
    file: FieldFile
    absolute: bool = False

    @property
    def url(self) -> str:
        from django.contrib.sites.shortcuts import get_current_site

        _url = (self.file and self.file.url) or ""
        try:
            currnet_url = get_current_site(None)
        except AttributeError:
            currnet_url = ""
        return f"{currnet_url}{_url}" if _url and self.absolute else _url

    def __repr__(self) -> str:
        return self.url

    def __bool__(self) -> bool:
        return bool(self.file)

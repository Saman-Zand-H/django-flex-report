from django.db.models import Manager, QuerySet


class ColumnQuerySet(QuerySet):
    def searchables(self):
        return self.filter(searchable=True)


class ColumnManager(Manager.from_queryset(ColumnQuerySet)):
    pass

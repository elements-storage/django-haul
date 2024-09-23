'''
Haul uses DRF ``ModelSerializer`` as a base for its serialization.

This means you can use custom ``Field`` and ``Serializer`` objects to serialize and deserialize fields.
'''

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .policy import ExportPolicy
from .types import ID, Ref


class DummyField(serializers.Field):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, read_only=True, allow_null=True, required=False)

    def run_validation(self, data=None):
        return None

    def get_attribute(self, instance):
        return None

    def to_representation(self, value):
        return None

    def to_internal_value(self, data):
        return None


class ForeignKey(serializers.Field):
    export_policy: ExportPolicy

    def __init__(self, *args, queryset=None, many=False, **kwargs):
        super().__init__(*args, read_only=False, **kwargs)
        self._many = many

    def bind(self, field_name, parent):
        super().bind(field_name, parent)
        self.export_policy = self.context.get('export_policy')

    def get_attribute(self, instance):
        return getattr(instance, self.source)

    def to_representation(self, value):
        if self._many:
            return [
                ID.from_object(instance)
                for instance in value
                if self.export_policy.should_export_object(instance)
            ]
        return ID.from_object(value) if self.export_policy.should_export_object(value) else None

    def to_internal_value(self, data):
        if self._many:
            return Ref(ids=data, field=self.source, nullable=self.allow_null)
        else:
            return Ref(ids=[data], field=self.source, nullable=self.allow_null)


class _BaseM2X(serializers.Field):
    weak = False
    export_policy: ExportPolicy

    def bind(self, field_name, parent):
        super().bind(field_name, parent)
        self.export_policy = self.context.get('export_policy')

    def get_attribute(self, instance):
        return getattr(instance, self.source).all()

    def to_representation(self, value):
        return [
            ID.from_object(instance)
            for instance in value
            if self.export_policy.should_export_object(instance)
        ]

    def to_internal_value(self, data):
        return Ref(data, field=self.source, nullable=True, weak=self.weak)


class ManyToMany(_BaseM2X):
    weak = False


class ReverseForeignKey(_BaseM2X):
    weak = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, allow_null=True, **kwargs)


class Exporter(serializers.ModelSerializer):
    serializer_related_field = DummyField

    def build_standard_field(self, field_name, model_field):
        cls, kwargs = super().build_standard_field(field_name, model_field)
        if 'validators' in kwargs:
            kwargs['validators'] = [x for x in kwargs['validators'] if not isinstance(x, UniqueValidator)]
        kwargs.pop('read_only', None)
        kwargs['required'] = False
        return cls, kwargs

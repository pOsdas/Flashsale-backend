from rest_framework import serializers


class HealthCheckDetailsSerializer(serializers.Serializer):
    status = serializers.CharField()
    details = serializers.DictField()


class SystemHealthSerializer(serializers.Serializer):
    status = serializers.CharField()
    checks = serializers.DictField(
        child=HealthCheckDetailsSerializer(),
    )


class ParserHealthSerializer(serializers.Serializer):
    status = serializers.CharField()
    checks = serializers.DictField()

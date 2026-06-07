from rest_framework import serializers


class FetchProductRequestSerializer(serializers.Serializer):
    marketplace = serializers.ChoiceField(choices=["wb", "ozon"])
    url = serializers.URLField(max_length=2000)
    role = serializers.ChoiceField(
        choices=["own", "competitor"],
        default="competitor",
    )
    check_interval_minutes = serializers.IntegerField(
        min_value=15,
        max_value=1440,
        default=60,
    )


class FetchProductResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    target_id = serializers.UUIDField()
    snapshot_id = serializers.UUIDField()
    alerts_count = serializers.IntegerField()
    product = serializers.DictField()


class FetcherImportItemSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=128)
    title = serializers.CharField(max_length=255)
    price_cents = serializers.IntegerField(min_value=0)
    currency = serializers.CharField(max_length=3)
    available = serializers.IntegerField(min_value=0)
    is_active = serializers.BooleanField(default=True)

    def validate_sku(self, value: str) -> str:
        value = value.strip()

        if not value:
            raise serializers.ValidationError("SKU cannot be empty.")

        return value.upper()

    def validate_name(self, value: str) -> str:
        value = value.strip()

        if not value:
            raise serializers.ValidationError("Product name cannot be empty.")

        return value

    def validate_currency(self, value: str) -> str:
        value = value.strip().upper()

        if len(value) != 3:
            raise serializers.ValidationError("Currency must be a 3-letter code.")

        if not value.isalpha():
            raise serializers.ValidationError("Currency must contain only letters.")

        return value


class FetcherImportSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=64)
    batch_id = serializers.CharField(max_length=128)
    items = FetcherImportItemSerializer(many=True)

    def validate_source(self, value: str) -> str:
        value = value.strip()

        if not value:
            raise serializers.ValidationError("Source cannot be empty.")

        return value

    def validate_batch_id(self, value: str) -> str:
        value = value.strip()

        if not value:
            raise serializers.ValidationError("Batch id cannot be empty.")

        return value

    def validate_items(self, value: list[dict]) -> list[dict]:
        if not value:
            raise serializers.ValidationError("Items list cannot be empty")

        seen_skus = set()

        for item in value:
            sku = item["sku"]

            if sku in seen_skus:
                raise serializers.ValidationError(f"Duplicate SKU in payload: {sku}")

            seen_skus.add(sku)

        return value

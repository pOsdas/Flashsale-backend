from app.api.v1.monitoring.models import MonitoringTarget


TELEGRAM_CHECK_INTERVAL_OPTIONS: tuple[int, ...] = (
    60,
    180,
    360,
    720,
    1440,
)


def build_target_interval_text(
    *,
    target: MonitoringTarget,
) -> str:
    title = target.title or target.external_id or target.url

    return (
        "⏱ Интервал проверки\n\n"
        f"{title}\n\n"
        f"Текущий интервал: {_format_interval(target.check_interval_minutes)}\n"
        "Минимальный интервал: 60 минут.\n\n"
        "Выберите новый интервал проверки."
    )


def format_interval_option(minutes: int) -> str:
    return _format_interval(minutes)


def _format_interval(minutes: int) -> str:
    if minutes == 60:
        return "1 час"

    if minutes == 180:
        return "3 часа"

    if minutes == 360:
        return "6 часов"

    if minutes == 720:
        return "12 часов"

    if minutes == 1440:
        return "24 часа"

    return f"{minutes} минут"

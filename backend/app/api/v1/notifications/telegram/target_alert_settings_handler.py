from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.api.v1.monitoring.services.alert_rule_service import (
    AlertRuleSettingsValidationError,
    AlertRuleTargetNotFoundError,
    EffectiveAlertRule,
    get_target_alert_settings,
)
from app.api.v1.monitoring.services.alert_rule_update_service import (
    set_target_alert_rule_cooldown,
    set_target_alert_rule_enabled,
    set_target_alert_rule_threshold,
)
from app.api.v1.notifications.telegram.client import TelegramBotClient
from app.api.v1.notifications.telegram.keyboards import (
    TARGET_ALERTS_BACK_CALLBACK_PREFIX,
    TARGET_ALERTS_COOLDOWN_CALLBACK_PREFIX,
    TARGET_ALERTS_DETAIL_CALLBACK_PREFIX,
    TARGET_ALERTS_OPEN_CALLBACK_PREFIX,
    TARGET_ALERTS_SET_CALLBACK_PREFIX,
    TARGET_ALERTS_THRESHOLD_CALLBACK_PREFIX,
    TARGET_SETTINGS_CALLBACK_PREFIX,
    build_target_alert_rule_detail_keyboard,
    build_target_alert_settings_keyboard,
)
from app.api.v1.notifications.telegram.products_handler import (
    TelegramProductsHandler,
)
from app.api.v1.notifications.telegram.target_alert_rule_options import (
    get_cooldown_option_by_minutes,
    get_threshold_kind,
    get_threshold_option_by_code,
)
from app.api.v1.notifications.telegram.target_alert_settings_presenter import (
    CALLBACK_CODE_TO_ALERT_TYPE,
    build_target_alert_rule_detail_text,
    build_target_alert_settings_text,
)
from app.api.v1.notifications.telegram.target_callback import (
    extract_target_callback_envelope,
    parse_target_and_page,
)
from app.api.v1.notifications.telegram.user_context import (
    TelegramUserContext,
    TelegramUserContextResolver,
)
from app.core.logging import get_logger


logger = get_logger(__name__)

MESSAGE_CALLBACK_EXPIRED = (
    "Это действие устарело. Откройте список заново командой /products."
)
MESSAGE_CALLBACK_FORBIDDEN = (
    "Это действие относится к другому пользователю."
)
MESSAGE_CONNECT_REQUIRED = (
    "Telegram не подключён к аккаунту."
)
MESSAGE_TARGET_NOT_FOUND = (
    "Товар не найден или уже был удалён."
)
MESSAGE_RULE_NOT_FOUND = (
    "Правило уведомлений не найдено."
)


@dataclass(frozen=True, slots=True)
class ParsedTargetAlertCallback:
    action: str
    target_id: UUID
    page: int
    alert_type: str | None = None
    desired_state: bool | None = None
    threshold_code: str | None = None
    cooldown_minutes: int | None = None
    return_to_detail: bool = False


class TelegramTargetAlertSettingsHandler:
    def __init__(
        self,
        *,
        client: TelegramBotClient,
        user_context_resolver: TelegramUserContextResolver,
        products_handler: TelegramProductsHandler,
    ) -> None:
        self.client = client
        self.user_context_resolver = user_context_resolver
        self.products_handler = products_handler

    def can_handle(
        self,
        *,
        callback_data: str,
    ) -> bool:
        return callback_data.startswith(
            (
                TARGET_ALERTS_OPEN_CALLBACK_PREFIX,
                TARGET_ALERTS_SET_CALLBACK_PREFIX,
                TARGET_ALERTS_BACK_CALLBACK_PREFIX,
                TARGET_ALERTS_DETAIL_CALLBACK_PREFIX,
                TARGET_ALERTS_THRESHOLD_CALLBACK_PREFIX,
                TARGET_ALERTS_COOLDOWN_CALLBACK_PREFIX,
                TARGET_SETTINGS_CALLBACK_PREFIX,
            )
        )

    def handle(
        self,
        *,
        callback_query: dict[str, Any],
    ) -> None:
        envelope = extract_target_callback_envelope(
            callback_query=callback_query,
        )

        if envelope is None:
            callback_query_id = str(
                callback_query.get("id") or ""
            ).strip()

            if callback_query_id:
                self._answer_expired(callback_query_id)
            return

        if not envelope.belongs_to_chat_user:
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
                text=MESSAGE_CALLBACK_FORBIDDEN,
                show_alert=True,
            )
            return

        user_context = self.user_context_resolver.resolve(
            telegram_chat_id=envelope.chat_id,
        )

        if user_context is None:
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
                text=MESSAGE_CONNECT_REQUIRED,
                show_alert=True,
            )
            return

        parsed = self._parse_callback_data(
            callback_data=envelope.callback_data,
        )

        if parsed is None:
            self._answer_expired(envelope.callback_query_id)
            return

        if parsed.action == "back":
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
            )
            self.products_handler.edit_page(
                chat_id=envelope.chat_id,
                message_id=envelope.message_id,
                user_context=user_context,
                page=parsed.page,
            )
            return

        if parsed.action == "open":
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
            )
            self._render_settings(
                chat_id=envelope.chat_id,
                message_id=envelope.message_id,
                user_context=user_context,
                target_id=parsed.target_id,
                page=parsed.page,
            )
            return

        if parsed.action == "detail":
            assert parsed.alert_type is not None
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
            )
            self._render_rule_detail(
                chat_id=envelope.chat_id,
                message_id=envelope.message_id,
                user_context=user_context,
                target_id=parsed.target_id,
                page=parsed.page,
                alert_type=parsed.alert_type,
            )
            return

        try:
            result = self._apply_update(
                user_context=user_context,
                parsed=parsed,
            )
        except AlertRuleTargetNotFoundError:
            self._answer_not_found(
                callback_query_id=envelope.callback_query_id,
                chat_id=envelope.chat_id,
                message_id=envelope.message_id,
                user_context=user_context,
                page=parsed.page,
            )
            return
        except AlertRuleSettingsValidationError as exc:
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
                text=str(exc),
                show_alert=True,
            )
            return
        except Exception as exc:
            logger.exception(
                "Telegram target alert rule update failed",
                extra={
                    "service": "telegram_bot",
                    "user_id": str(user_context.user.pk),
                    "target_id": str(parsed.target_id),
                    "alert_type": parsed.alert_type,
                    "action": parsed.action,
                    "error": str(exc),
                },
            )
            self.client.answer_callback_query(
                callback_query_id=envelope.callback_query_id,
                text="Не удалось изменить правило уведомлений.",
                show_alert=True,
            )
            return

        self.client.answer_callback_query(
            callback_query_id=envelope.callback_query_id,
            text=self._build_update_confirmation(
                parsed=parsed,
                result=result,
            ),
        )

        if parsed.return_to_detail or parsed.action in {
            "threshold",
            "cooldown",
        }:
            assert parsed.alert_type is not None
            self._render_rule_detail(
                chat_id=envelope.chat_id,
                message_id=envelope.message_id,
                user_context=user_context,
                target_id=parsed.target_id,
                page=parsed.page,
                alert_type=parsed.alert_type,
            )
            return

        self._render_settings(
            chat_id=envelope.chat_id,
            message_id=envelope.message_id,
            user_context=user_context,
            target_id=parsed.target_id,
            page=parsed.page,
        )

    def _apply_update(
        self,
        *,
        user_context: TelegramUserContext,
        parsed: ParsedTargetAlertCallback,
    ):
        assert parsed.alert_type is not None

        if parsed.action == "set":
            assert parsed.desired_state is not None
            return set_target_alert_rule_enabled(
                user=user_context.user,
                target_id=parsed.target_id,
                alert_type=parsed.alert_type,
                is_enabled=parsed.desired_state,
            )

        if parsed.action == "threshold":
            assert parsed.threshold_code is not None
            option = get_threshold_option_by_code(
                alert_type=parsed.alert_type,
                code=parsed.threshold_code,
            )

            if option is None:
                raise AlertRuleSettingsValidationError(
                    "Unsupported threshold option."
                )

            threshold_kind = get_threshold_kind(
                alert_type=parsed.alert_type,
            )

            if threshold_kind == "percent":
                threshold_percent = option.value
                threshold_absolute = None
            elif threshold_kind == "absolute":
                threshold_percent = None
                threshold_absolute = option.value
            else:
                raise AlertRuleSettingsValidationError(
                    "Threshold is not supported for this alert type."
                )

            return set_target_alert_rule_threshold(
                user=user_context.user,
                target_id=parsed.target_id,
                alert_type=parsed.alert_type,
                threshold_percent=threshold_percent,
                threshold_absolute=threshold_absolute,
            )

        if parsed.action == "cooldown":
            assert parsed.cooldown_minutes is not None
            option = get_cooldown_option_by_minutes(
                minutes=parsed.cooldown_minutes,
            )

            if option is None:
                raise AlertRuleSettingsValidationError(
                    "Unsupported silence period."
                )

            return set_target_alert_rule_cooldown(
                user=user_context.user,
                target_id=parsed.target_id,
                alert_type=parsed.alert_type,
                cooldown_minutes=option.minutes,
            )

        raise AlertRuleSettingsValidationError(
            "Unsupported alert settings action."
        )

    def _render_settings(
        self,
        *,
        chat_id: str,
        message_id: int,
        user_context: TelegramUserContext,
        target_id: UUID,
        page: int,
    ) -> None:
        try:
            target, rules = get_target_alert_settings(
                user=user_context.user,
                target_id=target_id,
            )
        except AlertRuleTargetNotFoundError:
            self.client.send_message(
                chat_id=chat_id,
                text=MESSAGE_TARGET_NOT_FOUND,
            )
            self.products_handler.edit_page(
                chat_id=chat_id,
                message_id=message_id,
                user_context=user_context,
                page=page,
            )
            return

        self.client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_target_alert_settings_text(
                target=target,
                rules=rules,
            ),
            reply_markup=build_target_alert_settings_keyboard(
                target_id=str(target.id),
                page=page,
                rules=rules,
            ),
        )

    def _render_rule_detail(
        self,
        *,
        chat_id: str,
        message_id: int,
        user_context: TelegramUserContext,
        target_id: UUID,
        page: int,
        alert_type: str,
    ) -> None:
        try:
            target, rules = get_target_alert_settings(
                user=user_context.user,
                target_id=target_id,
            )
        except AlertRuleTargetNotFoundError:
            self.client.send_message(
                chat_id=chat_id,
                text=MESSAGE_TARGET_NOT_FOUND,
            )
            self.products_handler.edit_page(
                chat_id=chat_id,
                message_id=message_id,
                user_context=user_context,
                page=page,
            )
            return

        rule = self._find_rule(
            rules=rules,
            alert_type=alert_type,
        )

        if rule is None:
            self.client.send_message(
                chat_id=chat_id,
                text=MESSAGE_RULE_NOT_FOUND,
            )
            self._render_settings(
                chat_id=chat_id,
                message_id=message_id,
                user_context=user_context,
                target_id=target_id,
                page=page,
            )
            return

        self.client.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=build_target_alert_rule_detail_text(
                target=target,
                rule=rule,
            ),
            reply_markup=build_target_alert_rule_detail_keyboard(
                target_id=str(target.id),
                page=page,
                rule=rule,
            ),
        )

    def _answer_not_found(
        self,
        *,
        callback_query_id: str,
        chat_id: str,
        message_id: int,
        user_context: TelegramUserContext,
        page: int,
    ) -> None:
        self.client.answer_callback_query(
            callback_query_id=callback_query_id,
            text=MESSAGE_TARGET_NOT_FOUND,
            show_alert=True,
        )
        self.products_handler.edit_page(
            chat_id=chat_id,
            message_id=message_id,
            user_context=user_context,
            page=page,
        )

    def _answer_expired(self, callback_query_id: str) -> None:
        self.client.answer_callback_query(
            callback_query_id=callback_query_id,
            text=MESSAGE_CALLBACK_EXPIRED,
            show_alert=True,
        )

    @staticmethod
    def _find_rule(
        *,
        rules: list[EffectiveAlertRule],
        alert_type: str,
    ) -> EffectiveAlertRule | None:
        return next(
            (
                rule
                for rule in rules
                if rule.alert_type == alert_type
            ),
            None,
        )

    @staticmethod
    def _build_update_confirmation(
        *,
        parsed: ParsedTargetAlertCallback,
        result,
    ) -> str:
        if not result.changed:
            return "Это значение уже выбрано."

        if parsed.action == "set":
            return (
                "Правило включено."
                if result.rule.is_enabled
                else "Правило выключено."
            )

        if parsed.action == "threshold":
            return "Порог обновлён."

        if parsed.action == "cooldown":
            return "Период тишины обновлён."

        return "Настройки обновлены."

    @staticmethod
    def _parse_callback_data(
        *,
        callback_data: str,
    ) -> ParsedTargetAlertCallback | None:
        for prefix in (
            TARGET_ALERTS_OPEN_CALLBACK_PREFIX,
            TARGET_SETTINGS_CALLBACK_PREFIX,
        ):
            if callback_data.startswith(prefix):
                parsed = parse_target_and_page(
                    payload=callback_data[len(prefix):],
                )

                if parsed is None:
                    return None

                target_id, page = parsed
                return ParsedTargetAlertCallback(
                    action="open",
                    target_id=target_id,
                    page=page,
                )

        if callback_data.startswith(TARGET_ALERTS_BACK_CALLBACK_PREFIX):
            parsed = parse_target_and_page(
                payload=callback_data[
                    len(TARGET_ALERTS_BACK_CALLBACK_PREFIX):
                ],
            )

            if parsed is None:
                return None

            target_id, page = parsed
            return ParsedTargetAlertCallback(
                action="back",
                target_id=target_id,
                page=page,
            )

        if callback_data.startswith(TARGET_ALERTS_DETAIL_CALLBACK_PREFIX):
            return TelegramTargetAlertSettingsHandler._parse_rule_value_callback(
                callback_data=callback_data,
                prefix=TARGET_ALERTS_DETAIL_CALLBACK_PREFIX,
                action="detail",
                has_value=False,
            )

        if callback_data.startswith(TARGET_ALERTS_THRESHOLD_CALLBACK_PREFIX):
            return TelegramTargetAlertSettingsHandler._parse_rule_value_callback(
                callback_data=callback_data,
                prefix=TARGET_ALERTS_THRESHOLD_CALLBACK_PREFIX,
                action="threshold",
                has_value=True,
            )

        if callback_data.startswith(TARGET_ALERTS_COOLDOWN_CALLBACK_PREFIX):
            parsed = TelegramTargetAlertSettingsHandler._parse_rule_value_callback(
                callback_data=callback_data,
                prefix=TARGET_ALERTS_COOLDOWN_CALLBACK_PREFIX,
                action="cooldown",
                has_value=True,
            )

            if parsed is None or parsed.threshold_code is None:
                return None

            try:
                cooldown_minutes = int(parsed.threshold_code)
            except ValueError:
                return None

            return ParsedTargetAlertCallback(
                action="cooldown",
                target_id=parsed.target_id,
                page=parsed.page,
                alert_type=parsed.alert_type,
                cooldown_minutes=cooldown_minutes,
                return_to_detail=True,
            )

        if callback_data.startswith(TARGET_ALERTS_SET_CALLBACK_PREFIX):
            payload = callback_data[
                len(TARGET_ALERTS_SET_CALLBACK_PREFIX):
            ]
            parts = payload.split(":")

            if len(parts) not in {4, 5}:
                return None

            code, desired_raw, target_id_raw, page_raw = parts[:4]
            alert_type = CALLBACK_CODE_TO_ALERT_TYPE.get(code)

            if alert_type is None or desired_raw not in {"0", "1"}:
                return None

            parsed = parse_target_and_page(
                payload=f"{target_id_raw}:{page_raw}",
            )

            if parsed is None:
                return None

            target_id, page = parsed
            return ParsedTargetAlertCallback(
                action="set",
                target_id=target_id,
                page=page,
                alert_type=alert_type,
                desired_state=desired_raw == "1",
                return_to_detail=(
                    len(parts) == 5 and parts[4] == "d"
                ),
            )

        return None

    @staticmethod
    def _parse_rule_value_callback(
        *,
        callback_data: str,
        prefix: str,
        action: str,
        has_value: bool,
    ) -> ParsedTargetAlertCallback | None:
        payload = callback_data[len(prefix):]

        if has_value:
            try:
                code, value_code, target_and_page = payload.split(
                    ":",
                    maxsplit=2,
                )
            except ValueError:
                return None
        else:
            try:
                code, target_and_page = payload.split(
                    ":",
                    maxsplit=1,
                )
            except ValueError:
                return None
            value_code = None

        alert_type = CALLBACK_CODE_TO_ALERT_TYPE.get(code)

        if alert_type is None:
            return None

        parsed = parse_target_and_page(payload=target_and_page)

        if parsed is None:
            return None

        target_id, page = parsed
        return ParsedTargetAlertCallback(
            action=action,
            target_id=target_id,
            page=page,
            alert_type=alert_type,
            threshold_code=value_code,
            return_to_detail=(action in {"threshold", "cooldown"}),
        )

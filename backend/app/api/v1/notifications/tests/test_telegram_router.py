from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase

from app.api.v1.notifications.telegram.router import (
    MESSAGE_CALLBACK_NOT_AVAILABLE,
    MESSAGE_OPEN_CONNECT_LINK,
    MESSAGE_PRIVATE_CHAT_ONLY,
    TelegramUpdateRouter,
)


class TelegramUpdateRouterTests(SimpleTestCase):
    def setUp(self) -> None:
        self.client = Mock()
        self.replies = Mock()
        self.start_handler = Mock()
        self.user_context_resolver = Mock()
        self.product_link_handler = Mock()
        self.product_callback_handler = Mock()
        self.products_handler = Mock()
        self.router = TelegramUpdateRouter(
            client=self.client,
            replies=self.replies,
            start_handler=self.start_handler,
            user_context_resolver=self.user_context_resolver,
            product_link_handler=self.product_link_handler,
            product_callback_handler=(
                self.product_callback_handler
            ),
            products_handler=self.products_handler,
        )

    def test_routes_start_command_with_token(self) -> None:
        self.router.handle_update(
            update={
                "update_id": 1,
                "message": {
                    "chat": {
                        "id": 123,
                        "type": "private",
                    },
                    "text": "/start signed-token",
                },
            }
        )

        self.start_handler.handle.assert_called_once_with(
            chat_id="123",
            token="signed-token",
        )

    def test_rejects_group_chat(self) -> None:
        self.router.handle_update(
            update={
                "update_id": 1,
                "message": {
                    "chat": {
                        "id": -100123,
                        "type": "supergroup",
                    },
                    "text": "/start",
                },
            }
        )

        self.replies.send_message.assert_called_once_with(
            chat_id="-100123",
            text=MESSAGE_PRIVATE_CHAT_ONLY,
        )
        self.start_handler.handle.assert_not_called()

    def test_unconnected_user_receives_connect_message(self) -> None:
        self.user_context_resolver.resolve.return_value = None

        self.router.handle_update(
            update={
                "update_id": 1,
                "message": {
                    "chat": {
                        "id": 123,
                        "type": "private",
                    },
                    "text": "https://www.ozon.ru/product/123",
                },
            }
        )

        self.replies.send_message.assert_called_once_with(
            chat_id="123",
            text=MESSAGE_OPEN_CONNECT_LINK,
        )

    def test_connected_user_product_link_is_routed(self) -> None:
        user_context = SimpleNamespace(user=object())
        self.user_context_resolver.resolve.return_value = user_context

        self.router.handle_update(
            update={
                "update_id": 1,
                "message": {
                    "chat": {
                        "id": 123,
                        "type": "private",
                    },
                    "text": "https://www.ozon.ru/product/123",
                },
            }
        )

        self.product_link_handler.handle.assert_called_once_with(
            user_context=user_context,
            text="https://www.ozon.ru/product/123",
        )

    def test_products_command_is_routed(self) -> None:
        user_context = SimpleNamespace(user=object())
        self.user_context_resolver.resolve.return_value = user_context

        self.router.handle_update(
            update={
                "update_id": 1,
                "message": {
                    "chat": {
                        "id": 123,
                        "type": "private",
                    },
                    "text": "/products",
                },
            }
        )

        self.products_handler.handle_command.assert_called_once_with(
            user_context=user_context,
        )

    def test_product_preview_callback_is_routed(self) -> None:
        self.product_callback_handler.can_handle.return_value = True
        callback_query = {
            "id": "callback-1",
            "message": {
                "chat": {
                    "id": 123,
                    "type": "private",
                }
            },
            "data": "product:add:token",
        }

        self.router.handle_update(
            update={
                "update_id": 1,
                "callback_query": callback_query,
            }
        )

        self.product_callback_handler.handle.assert_called_once_with(
            callback_query=callback_query,
        )

    def test_products_callback_is_routed(self) -> None:
        self.product_callback_handler.can_handle.return_value = False
        self.products_handler.can_handle_callback.return_value = True
        callback_query = {
            "id": "callback-1",
            "message": {
                "chat": {
                    "id": 123,
                    "type": "private",
                }
            },
            "data": "products:page:2",
        }

        self.router.handle_update(
            update={
                "update_id": 1,
                "callback_query": callback_query,
            }
        )

        self.products_handler.handle_callback.assert_called_once_with(
            callback_query=callback_query,
        )

    def test_unknown_callback_query_is_answered(self) -> None:
        self.product_callback_handler.can_handle.return_value = False
        self.products_handler.can_handle_callback.return_value = False

        self.router.handle_update(
            update={
                "update_id": 1,
                "callback_query": {
                    "id": "callback-1",
                    "message": {
                        "chat": {
                            "id": 123,
                            "type": "private",
                        }
                    },
                    "data": "unknown",
                },
            }
        )

        self.client.answer_callback_query.assert_called_once_with(
            callback_query_id="callback-1",
            text=MESSAGE_CALLBACK_NOT_AVAILABLE,
            show_alert=False,
        )

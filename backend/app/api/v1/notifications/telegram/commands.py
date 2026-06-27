from typing import Final


TELEGRAM_BOT_COMMANDS: Final[tuple[dict[str, str], ...]] = (
    {
        "command": "start",
        "description": "Главное меню",
    },
    {
        "command": "products",
        "description": "Отслеживаемые товары",
    },
    {
        "command": "help",
        "description": "Список команд",
    },
)

COMMANDS_LIST_TEXT: Final[str] = (
    "/start — главное меню\n"
    "/products — отслеживаемые товары\n"
    "/help — список команд"
)

HELP_MESSAGE: Final[str] = (
    "📋 Команды Flashsale Signals\n\n"
    f"{COMMANDS_LIST_TEXT}\n\n"
    "Чтобы добавить товар, отправьте ссылку "
    "на товар Wildberries или Ozon."
)

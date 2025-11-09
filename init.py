import os
import sys
import json
import time
import logging
from telegram import Bot
import asyncio

retry_delay = 5

# Настройки из переменных окружения
envs = dict(
    # base_url="https://edu2-api.21-school.ru/services/21-school/api",
    base_url="https://platform.21-school.ru/services/21-school/api",
    api_version="v1",
    test=False,  # Включить режим тестирования для логирования

    limit_query=100,
    max_retries=3,  # Максимальное количество попыток
    RETRY_DELAY=retry_delay,  # Задержка между попытками (в секундах)
    main_delay=5 * retry_delay,

    # Общие настройки
    BASE_KEY=os.getenv('BASE_KEY'),

    # Настройки базы данных
    DATABASE_HOST=os.getenv('DATABASE_HOST'),
    DATABASE_PORT=os.getenv('DATABASE_PORT'),
    DATABASE_USERNAME=os.getenv('DATABASE_USERNAME'),
    DATABASE_PASSWORD=os.getenv('DATABASE_PASSWORD'),
    DATABASE_NAME=os.getenv('DATABASE_NAME'),

    # Alerts для Telegram
    TELEGRAM_CHAT_ID=os.getenv('TELEGRAM_CHAT_ID'),
    TELEGRAM_TOKEN=os.getenv('TELEGRAM_TOKEN')
)

def init_envs():
    # Проверка, установлены ли все необходимые переменные окружения
    missing_env_vars = [var for var in envs if os.getenv(var) is None]

    if missing_env_vars:
        # Если какие-то переменные не установлены, выводим ошибку и останавливаем скрипт
        logging.error(f"Следующие переменные окружения не установлены: {', '.join(missing_env_vars)}")
        time.sleep(600)
        sys.exit(1)

    # Если все переменные окружения установлены, продолжаем выполнение скрипта
    logging.info("Все необходимые переменные окружения установлены.")

class TelegramLoggingHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.send_telegram_alert(log_entry))
        loop.close()

    async def send_telegram_alert(self, message):
        chat_id = envs['TELEGRAM_CHAT_ID']
        token = envs['TELEGRAM_TOKEN']

        if not all([token, chat_id]):
            logging.warning("LOGGER_CONFIG: Отсутствует одна или несколько необходимых переменных окружения")
            logging.warning(f"LOGGER_CONFIG: {chat_id} {token}")
            return

        bot = Bot(token=token)
        await bot.send_message(chat_id=chat_id, text=message)

def escape_markdown(text):
    # Экранирование символов для MarkdownV2
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text

def format_json_message(json_obj):
    json_str = json.dumps(json_obj, ensure_ascii=False, indent=2)
    escaped_json_str = escape_markdown(json_str)
    return f"```json\n{escaped_json_str}\n```"
logger_initialized = False

def init_logging():
    global logger_initialized
    if logger_initialized:
        return
    logger_initialized = True

    level = logging.INFO

    logger = logging.getLogger()

    if not logger.handlers:
        logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d %(funcName)s] :  %(message)s",
        datefmt="%d.%m.%Y %H:%M:%S"
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    telegram_handler = TelegramLoggingHandler()
    telegram_handler.setLevel(logging.ERROR)
    telegram_handler.setFormatter(formatter)
    logger.addHandler(telegram_handler)

async def telega_json(message):
    chat_id = envs['TELEGRAM_CHAT_ID']
    token = envs['TELEGRAM_TOKEN']
    bot = Bot(token=token)
    await bot.send_message(chat_id=chat_id, text=format_json_message(message), parse_mode='MarkdownV2')

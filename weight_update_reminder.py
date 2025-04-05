import json
import logging
import os
import re
from datetime import datetime, date, timedelta, timezone

from pika import BlockingConnection, URLParameters
from pika.spec import BasicProperties
from pymongo import MongoClient

from fatsecret import FatSecretContext
from fatsecret.fatsecret_client import FatSecretProfile

logger = logging.getLogger(__name__)


def calc_client_now(client_timezone_offset) -> datetime:
    """
    Возвращает текущее время пользователя в его часовом поясе
    :param client_timezone_offset: смещение часового пояса, например +05:00
    :return: время
    """
    match = re.search(r'([+-])(\d{2}):(\d{2})', client_timezone_offset)
    sign = match.group(1)
    hour = int(match.group(2))
    minutes = int(match.group(3))
    offset = hour * 60 + minutes
    client_timezone_minutes_offset = offset if sign == '+' else -offset
    client_timezone = timezone(timedelta(minutes=client_timezone_minutes_offset))
    return datetime.now(client_timezone)


def calc_client_notification_interval(instant) -> tuple:
    """
    Отправлять сообщения можно с 08:00 до 21:00 по часовому поясу пользователя
    (у каждого пользователя свой собственный часовой пояс)
    Расчет интервала выполняется следующим образом:
    в текущей дате-времени пользователя заменяем время на 08:00:00.000,
    чтобы получить начало интервала и на 21:00:00.000, чтобы получить конец интервала.
    :return: Кортеж из начала и конца интервала
    """
    start_interval = instant.replace(hour=8, minute=0, second=0, microsecond=0)
    end_interval = instant.replace(hour=21, minute=0, second=0, microsecond=0)
    return start_interval, end_interval


def main():
    fat_secret_context = FatSecretContext(os.getenv("CONSUMER_KEY"), os.getenv("CONSUMER_SECRET"))

    # получение списка пользователей, которым ещё не отправляли уведомление или когда-то в прошлом (не сегодня)
    db_client = MongoClient(os.getenv("DATABASE_URI"))
    clients = db_client.nutriciloid.clients
    clients_to_remind = clients.find({"$or": [
        {"remind_weight_send_date": {"$exists": False}},
        {"remind_weight_send_date": None},
        {"remind_weight_send_date": {"$lt": datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)}}
    ]}).to_list()

    if len(clients_to_remind) == 0:
        logger.info("There is no one client for sending notification")
        return

    broker_connection = BlockingConnection(URLParameters(os.getenv("RABBITMQ_URI")))
    broker_channel= broker_connection.channel()
    message_properties = BasicProperties(content_type="application/json", content_encoding="utf-8")

    for client in clients_to_remind:
        logger.debug(f"Handle client: {client['telegram_id']}")
        client_now = calc_client_now(client['timezone_offset'])
        client_notification_interval = calc_client_notification_interval(client_now)
        # проверяем, что в данный момент пользователю можно отправлять уведомление (сейчас у пользователя не ночь)
        if client_notification_interval[0] < client_now < client_notification_interval[1]:
            fat_secret_profile = FatSecretProfile(client['oauth']['access']['token'], client['oauth']['access']['secret'], fat_secret_context)
            profile = fat_secret_profile.get_status()
            logger.debug(f"client {client['telegram_id']} status is {profile}")
            weight_updated_date = (date(1970, 1, 1) + timedelta(days=float(profile['last_weight_date_int'])))
            # проверяем, что сегодня пользователь ещё не обновлял вес
            if weight_updated_date < client_now.date():
                message = {"telegram_id": client['telegram_id'], "status": False}
            else:
                message = {"telegram_id": client['telegram_id'], "status": True}

            logger.debug(f"Send notification to client {client['telegram_id']}")
            broker_channel.basic_publish('', "remind_weight",
                                         json.dumps(message),
                                         properties=message_properties)

        else:
            logger.debug(f"Skip client {client['telegram_id']}: not a good time to send notification")


if __name__ == "__main__":
    # Настройка базового конфигуратора логирования
    logging.basicConfig(
        level=logging.DEBUG,  # Уровень логирования
        format='%(asctime)s - %(levelname)s - %(message)s',  # Формат логов
        handlers=[
            logging.FileHandler('weight_update_reminder.log'),  # Запись в файл
            logging.StreamHandler()  # Вывод в консоль
        ]
    )

    main()

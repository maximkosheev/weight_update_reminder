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


def calc_user_now(user_timezone_offset) -> datetime:
    """
    Возвращает текущее время пользователя в его часовом поясе
    :param user_timezone_offset: смещение часового пояса, например +05:00
    :return: время
    """
    match = re.search(r'([+-])(\d{2}):(\d{2})', user_timezone_offset)
    sign = match.group(1)
    hour = int(match.group(2))
    minutes = int(match.group(3))
    offset = hour * 60 + minutes
    user_timezone_minutes_offset = offset if sign == '+' else -offset
    user_timezone = timezone(timedelta(minutes=user_timezone_minutes_offset))
    return datetime.now(user_timezone)


def calc_user_notification_interval(instant) -> tuple:
    """
    Отправлять сообщения можно с 08:00 до 21:00 по часовому поясу пользователя
    (у каждого пользователя свой собственный часовой пояс)
    Расчет интервала выполняется следующим образом:
    в текущей дате-времени пользователя заменяем время на 08:00:00.000,
    чтобы получить начало интервала и на 21:00:00.000, чтобы получить конец интервала.
    :return: Кортеж из начала и конца интервала
    """
    start_interval = instant.replace(hour=8, minute=0, second=0, microsecond=0)
    end_interval = instant.replace(hour=23, minute=59, second=59, microsecond=999)
    return start_interval, end_interval


def main():
    fat_secret_context = FatSecretContext(os.getenv("CONSUMER_KEY"), os.getenv("CONSUMER_SECRET"))

    # получение списка пользователей, которым ещё не отправляли уведомление или когда-то в прошлом (не сегодня)
    db_client = MongoClient(os.getenv("DATABASE_URI"))
    users = db_client.nutriciloid.users
    users_to_remind = users.find({"$or": [
        {"remind_weight_send_date": {"$exists": False}},
        {"remind_weight_send_date": None},
        {"remind_weight_send_date": {"$lt": datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)}}
    ]}).to_list()

    if len(users_to_remind) == 0:
        logger.info("There is no one user for sending notification")
        return

    broker_connection = BlockingConnection(URLParameters(os.getenv("AMQ_URL")))
    broker_channel= broker_connection.channel()
    message_properties = BasicProperties(content_type="application/json", content_encoding="utf-8")

    for user in users_to_remind:
        logger.debug(f"Handle user: {user['user_id']}")
        user_now = calc_user_now(user['timezone_offset'])
        user_notification_interval = calc_user_notification_interval(user_now)
        # проверяем, что в данный момент пользователю можно отправлять уведомление (сейчас у пользователя не ночь)
        if user_notification_interval[0] < user_now < user_notification_interval[1]:
            fat_secret_profile = FatSecretProfile(user['oauth']['access']['token'], user['oauth']['access']['secret'], fat_secret_context)
            profile = fat_secret_profile.get_status()
            logger.debug(f"User {user['user_id']} status is {profile}")
            weight_updated_date = (date(1970, 1, 1) + timedelta(days=float(profile['last_weight_date_int'])))
            # проверяем, что сегодня пользователь ещё не обновлял вес
            if weight_updated_date < user_now.date():
                message = {"user_id": user['user_id'], "status": False}
            else:
                message = {"user_id": user['user_id'], "status": True}

            logger.debug(f"Send notification to user {user['user_id']}")
            broker_channel.basic_publish('', "remind_weight",
                                         json.dumps(message),
                                         properties=message_properties)

        else:
            logger.debug(f"Skip user {user['user_id']}: not a good time to send notification")


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

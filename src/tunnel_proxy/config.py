import logging
from os import getenv
from dataclasses import dataclass


MIDDLEWARE_API_HOST = 'MIDDLEWARE_API_HOST'
MIDDLEWARE_API_PORT = 'MIDDLEWARE_API_PORT'
LOG_LEVEL = 'LOG_LEVEL'
USER_EVENTS_LOG_PATH = 'USER_EVENTS_LOG_PATH'
USER_EVENTS_LOG_SIZE = 'USER_EVENTS_LOG_SIZE'
USER_EVENTS_LOG_BACKUP = 'USER_EVENTS_LOG_BACKUP'
USER_EVENTS_LOG_FORMAT = 'USER_EVENTS_LOG_FORMAT'
USER_EVENTS_LOG_BUFFER_SIZE = 'USER_EVENTS_LOG_BUFFER_SIZE'
MESSAGE_LOAD_MAXIMUM_AMOUNT = 'MESSAGE_LOAD_MAXIMUM_AMOUNT'
MESSAGE_LOAD_INTERVAL_IN_SECONDS = 'MESSAGE_LOAD_INTERVAL_IN_SECONDS'
MESSAGE_LOAD_EXCEED_THRESHOLD = 'MESSAGE_LOAD_EXCEED_THRESHOLD'

@dataclass
class Config:
    log_level: str
    middleware_api_host: str
    middleware_api_port: str
    user_events_log_path: str
    user_events_log_size: int
    user_events_log_backup: int
    user_events_log_buffer_size: int
    message_load_maximum_amount: int
    message_load_interval_in_seconds: int
    message_load_exceed_threshold: int


class EnvConfig(Config):
    def __init__(self):
        log_level = getenv(LOG_LEVEL, logging.INFO)
        middleware_api_host = getenv(MIDDLEWARE_API_HOST, 'localhost')
        middleware_api_port = getenv(MIDDLEWARE_API_PORT, '80')
        user_events_log_path = getenv(USER_EVENTS_LOG_PATH, 'user-events')
        user_events_log_size = int(getenv(USER_EVENTS_LOG_SIZE, str(1024 * 50)))
        user_events_log_backup = int(getenv(USER_EVENTS_LOG_BACKUP, '20'))
        user_events_log_buffer_size = int(getenv(USER_EVENTS_LOG_BUFFER_SIZE, '500'))
        message_load_maximum_amount = int(getenv(MESSAGE_LOAD_MAXIMUM_AMOUNT, '800'))
        message_load_interval_in_seconds = int(getenv(MESSAGE_LOAD_INTERVAL_IN_SECONDS, '10'))
        message_load_exceed_threshold = int(getenv(MESSAGE_LOAD_EXCEED_THRESHOLD, '3'))
        return super().__init__(log_level=log_level,
            middleware_api_host=middleware_api_host,
            middleware_api_port=middleware_api_port,
            user_events_log_path=user_events_log_path,
            user_events_log_size=user_events_log_size,
            user_events_log_backup=user_events_log_backup,
            user_events_log_buffer_size=user_events_log_buffer_size,
            message_load_maximum_amount=message_load_maximum_amount,
            message_load_interval_in_seconds=message_load_interval_in_seconds,
            message_load_exceed_threshold=message_load_exceed_threshold
        )

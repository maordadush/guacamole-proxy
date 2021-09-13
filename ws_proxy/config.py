from os import getenv
from ..config import EnvConfig


USER_EVENTS_LOG_PATH = 'USER_EVENTS_LOG_PATH'
USER_EVENTS_LOG_SIZE = 'USER_EVENTS_LOG_SIZE'
USER_EVENTS_LOG_BACKUP = 'USER_EVENTS_LOG_BACKUP'

class WebsocketProxyConfig(EnvConfig):
    def __init__(self):
        self.user_events_log_path = getenv(USER_EVENTS_LOG_PATH, 'logs')
        self.user_events_log_size = int(getenv(USER_EVENTS_LOG_SIZE, str(1024 * 50)))
        self.user_events_log_backup = int(getenv(USER_EVENTS_LOG_BACKUP, '20'))
        super().__init__()

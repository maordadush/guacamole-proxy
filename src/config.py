import logging
from os import getenv
from dataclasses import dataclass

MIDDLEWARE_API_HOST = 'MIDDLEWARE_API_HOST'
MIDDLEWARE_API_PORT = 'MIDDLEWARE_API_PORT'
GUACAMOLE_SERVER_HOST = 'GUACAMOLE_SERVER_HOST'
GUACAMOLE_SERVER_PORT = 'GUACAMOLE_SERVER_PORT'
LOG_LEVEL = 'LOG_LEVEL'

@dataclass
class Config:
    log_level: str
    guacamole_server_host: str
    guacamole_server_port: str
    middleware_api_host: str
    middleware_api_port: str


class EnvConfig(Config):
    def __init__(self):
        log_level = getenv(LOG_LEVEL, logging.INFO)
        guacamole_server_host = getenv(GUACAMOLE_SERVER_HOST, 'localhost')
        guacamole_server_port = getenv(GUACAMOLE_SERVER_PORT, '80')
        middleware_api_host = getenv(MIDDLEWARE_API_HOST, 'localhost')
        middleware_api_port = getenv(MIDDLEWARE_API_PORT, '80')
        return super().__init__(log_level=log_level,
            guacamole_server_host=guacamole_server_host,
            guacamole_server_port=guacamole_server_port,
            middleware_api_host=middleware_api_host,
            middleware_api_port=middleware_api_port
        )

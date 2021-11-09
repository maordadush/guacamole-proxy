import logging
from os import getenv
from dataclasses import dataclass

MIDDLEWARE_API_HOST = 'MIDDLEWARE_API_HOST'
MIDDLEWARE_API_PORT = 'MIDDLEWARE_API_PORT'
LOG_LEVEL = 'LOG_LEVEL'

@dataclass
class Config:
    log_level: str
    middleware_api_host: str
    middleware_api_port: str


class EnvConfig(Config):
    def __init__(self):
        log_level = getenv(LOG_LEVEL, logging.INFO)
        middleware_api_host = getenv(MIDDLEWARE_API_HOST, 'localhost')
        middleware_api_port = getenv(MIDDLEWARE_API_PORT, '80')
        return super().__init__(log_level=log_level,
            middleware_api_host=middleware_api_host,
            middleware_api_port=middleware_api_port
        )

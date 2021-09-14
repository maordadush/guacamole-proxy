from pathlib import Path
import logging
from datetime import datetime
from typing import Tuple

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect
import websockets
import asyncio
import aiohttp

from config import EnvConfig
from custom_loggers import ReverseRotatingFileHandler

config = EnvConfig()

logging.basicConfig(level=config.log_level)

# User events logging

user_events_queue = asyncio.Queue()
Path(config.user_events_log_path).mkdir(parents=True, exist_ok=True)
reverse_rotating_handler = ReverseRotatingFileHandler(
    f'{config.user_events_log_path}/user_events.log', 'a', config.user_events_log_size, config.user_events_log_backup)
message_only_formatter = logging.Formatter('%(message)s')
reverse_rotating_handler.setFormatter(message_only_formatter)
user_events_logger = logging.getLogger('user-events')
user_events_logger.addHandler(reverse_rotating_handler)
user_events_logger.propagate = False

app = FastAPI()

origins = ['*']

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket('/ws')
async def ws_proxy(client_socket: WebSocket):
    await client_socket.accept('guacamole')
    logging.info(f'Accepted client connection. token: {client_socket.query_params.get("token")}')
    guacamole_websocket_uri = f'ws://{config.guacamole_server_host}:{config.guacamole_server_port}\
        /guacamole/websocket-tunnel?{str(client_socket.query_params)}'
    async with websockets.connect(guacamole_websocket_uri, subprotocols=['guacamole'], max_size=None,
        extra_headers=client_socket.headers.raw, compression=None, max_queue=None) as server_socket:

        logging.info(f'Successfully connected to webserver. token: {client_socket.query_params.get("token")}')
        try:
            async def handle_websocket_input():
                while True:
                    input_message = await client_socket.receive_text()
                    message_type = input_message.split(',')[0].split('.')[1]
                    if message_type == 'put':
                        asyncio.create_task(handle_file_put(input_message, server_socket))
                    elif message_type == 'custom-message':
                        user_events_queue.put_nowait(input_message)
                    else:
                        await server_socket.send(input_message)
            
            async def handle_websocket_output():
                async for output_message in server_socket:
                    await client_socket.send_bytes(output_message)

            # Blocks while running asynchronously
            await asyncio.gather(handle_websocket_input(), handle_websocket_output(), log_user_events())

        except websockets.exceptions.ConnectionClosed:
            logging.info(f'Webserver connection closed, terminating connection with client socket. token: {client_socket.query_params.get("token")}')
            await client_socket.close()
        except WebSocketDisconnect:
            logging.info(f'Client conneection closed, terminating connection with webserver socket. token: {client_socket.query_params.get("token")}')
            await server_socket.close()


async def log_user_events():
    while True:
        input_message = await user_events_queue.get()
        event_type = get_part(input_message, 1)
        if event_type == 'key':
            keycode = int(get_part(input_message, 2))
            pressed = int(get_part(input_message, 3)) == 1
            timestamp = datetime.fromtimestamp(int(get_part(input_message, 4)) / 1000)
            user_events_logger.info(f'{event_type},{timestamp},{keycode},{pressed}')
        elif event_type == 'mouse':
            x = int(get_part(input_message, 2))
            y = int(get_part(input_message, 3))
            pressed = int(get_part(input_message, 4)) == 1
            timestamp = datetime.fromtimestamp(int(get_part(input_message, 5)) / 1000)
            user_events_logger.info(f'{event_type},{timestamp},{x},{y},{pressed}')

async def handle_file_put(input_message: str, websocket: WebSocket):
    filepart_index, filepart_content = get_filepart_from_put_message(input_message)
    filepath = filepart_content[filepart_content.find('.') + 1:]
    filepath_extension_index = filepath.rfind('.')

    if filepath_extension_index == -1:
        await websocket.send(input_message)
    file_extension = filepath[filepath_extension_index + 1:-1]
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f'http://{config.middleware_api_host}:{config.middleware_api_port}/file_extension', data=file_extension) as response:
            if response.status == 200:
                new_file_extension = await response.text()
                filepath_without_extension = filepath[:filepath_extension_index]
                filepath_with_new_extension = f'{filepath_without_extension}.{new_file_extension}'
                input_message_without_file_part = input_message[:filepart_index]
                new_input_message = f'{input_message_without_file_part}{str(len(filepath_with_new_extension))}.{filepath_with_new_extension};'
                await websocket.send(new_input_message)
            else:
                if response.status != 204:
                    logging.warn(f'Middleware API file extension endpoint returned an unknown status code: {response.status}. Sending original file extension')
                await websocket.send(input_message)

def get_filepart_from_put_message(input_message: str) -> Tuple[int, str]:
    """
    Extracts the filepath part from a put message (5th part)
    returns: A tuple containing the index of the file path part within the message, and the filepath part itself
    """
    file_part_index = 0
    for _ in range(4):
        part_index = input_message.find(',') + 1
        input_message = input_message[part_index:]
        file_part_index += part_index
    return file_part_index, input_message

def get_part(input_message: str, index: int) -> str:
    """
    Get a guacamole message part content, by index
    """
    input_message = input_message[:-1]  # Remove the semicolon at the end of the message
    return input_message.split(',')[index].split('.')[1]


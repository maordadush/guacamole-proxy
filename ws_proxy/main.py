import logging
import logging.handlers
from datetime import datetime
from typing import Tuple

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect
import websockets
import asyncio
import aiohttp

from config import EnvConfig

config = EnvConfig()

logging.basicConfig(level=config.log_level)

# Keystrokes
keystrokes_queue = asyncio.Queue()
keystrokes_logger = logging.getLogger('keystrokes')

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
                    elif message_type == 'keyTimestamp':
                        keystrokes_queue.put_nowait(input_message)
                    else:
                        await server_socket.send(input_message)
            
            async def handle_websocket_output():
                async for output_message in server_socket:
                    await client_socket.send_bytes(output_message)

            # Blocks while both run simultaneously
            await asyncio.gather(handle_websocket_input(), handle_websocket_output(), log_keystrokes())

        except websockets.exceptions.ConnectionClosed:
            logging.info(f'Webserver connection closed, terminating connection with client socket. token: {client_socket.query_params.get("token")}')
            await client_socket.close()
        except WebSocketDisconnect:
            logging.info(f'Client conneection closed, terminating connection with webserver socket. token: {client_socket.query_params.get("token")}')
            await server_socket.close()


async def log_keystrokes():
    while True:
        input_message = await keystrokes_queue.get()
        timestamp, keystroke, pressed = parse_keystroke_message(input_message)
        keystrokes_logger.info(f'{timestamp} - {keystroke}:{pressed}')

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

def parse_keystroke_message(input_message: str) -> Tuple[datetime, int, bool]:
    input_message = input_message[:-1] # Remove the semicolon at the end of the message
    parts = input_message.split(',')
    keycode = int(parts[1].split('.')[1])
    pressed = int(parts[2].split('.')[1]) == 1
    timestamp = datetime.fromtimestamp(int(parts[3].split('.')[1]) / 1000)
    return timestamp, keycode, pressed

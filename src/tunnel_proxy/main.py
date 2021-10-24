from pathlib import Path
import logging
from datetime import datetime
import base64


from fastapi import FastAPI, WebSocket, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse
from starlette.websockets import WebSocketDisconnect
import websockets
import asyncio
import aiohttp

from config import EnvConfig
from custom_loggers import ReverseRotatingFileHandler
from guac_message import get_part, get_part_content, remove_datetime_from_modified_message, split_multimessage

config = EnvConfig()

logging.basicConfig(level=config.log_level)

# User events logging

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


@app.get('/proxy/tunnel/_health')
async def health_check():
    return Response(status_code=200)

@app.post('/proxy/tunnel/http')
async def http_tunnel_proxy(request: Request):
    action = list(request._query_params._dict.keys())[0]
    original_request = f'http://{config.guacamole_server_host}:{config.guacamole_server_port}{request.headers["x-original-uri"]}?{action}'
    request_body = await request.body()
    username = request.headers.get('x-username')
    async with aiohttp.ClientSession() as session:
        request_body = request_body.decode('utf-8')
        if action.startswith('write'):
            messages = ''
            split_messages = split_multimessage(request_body)
            for message in split_messages:
                message_type = get_part_content(message, 0)
                if message_type == 'put':
                    message = await get_modified_file_extension(message)
                elif message_type == 'mouse' or message_type == 'key':
                    asyncio.create_task(log_user_event(username, message))
                    message = remove_datetime_from_modified_message(message)
                messages += message

            request_body = messages

        headers = request.headers.mutablecopy()
        headers['content-length'] = str(len(request_body))
        async with session.post(original_request, data=request_body, headers=headers) as response:
            response_body = await response.read()
            return Response(content=response_body, status_code=response.status)


@app.get('/proxy/tunnel/http')
async def http_tunnel_proxy(request: Request):
    original_request = f'http://{config.guacamole_server_host}:{config.guacamole_server_port}{request.headers["x-original-uri"]}?{list(request._query_params._dict.keys())[0]}'
    request_body = await request.body()

    async def response_iterator():
        async with aiohttp.ClientSession() as session:
            async with session.get(original_request, data=request_body) as response:
                async for chunk, _ in response.content.iter_chunks():
                    yield chunk
    return StreamingResponse(response_iterator())


@app.websocket('/proxy/tunnel/ws')
async def ws_tunnel_proxy(client_socket: WebSocket):
    await client_socket.accept('guacamole')
    username = client_socket.query_params.get('username')
    token = client_socket.query_params.get('token')
    logging.info(f'Accepted client connection. username: {username}, token: {token}')
    guacamole_websocket_uri = f'ws://{config.guacamole_server_host}:{config.guacamole_server_port}\
        /websocket-tunnel?{str(client_socket.query_params)}'
    async with websockets.connect(guacamole_websocket_uri, subprotocols=['guacamole'], max_size=None,
                                  extra_headers=client_socket.headers.raw, compression=None, max_queue=None) as server_socket:

        logging.info(
            f'Successfully connected to webserver. token: {client_socket.query_params.get("token")}')
        try:
            async def handle_websocket_input():
                while True:
                    input_message = await client_socket.receive_text()
                    message_type = get_part_content(input_message, 0)
                    if message_type == 'put':
                        asyncio.create_task(handle_websocket_put(
                            input_message, server_socket))
                    else:
                        if message_type == 'mouse' or message_type == 'key':
                            asyncio.create_task(log_user_event(username, input_message))
                            input_message = remove_datetime_from_modified_message(input_message)
                        await server_socket.send(input_message)

            async def handle_websocket_output():
                async for output_message in server_socket:
                    await client_socket.send_bytes(output_message)

            # Blocks while running asynchronously
            await asyncio.gather(handle_websocket_input(), handle_websocket_output())

        except websockets.exceptions.ConnectionClosed:
            logging.info(
                f'Webserver connection closed, terminating connection with client socket. username: {username}, token: {token}')
            await client_socket.close()
        except WebSocketDisconnect:
            logging.info(
                f'Client conneection closed, terminating connection with webserver socket. username: {username}, token: {token}')
            await server_socket.close()


async def log_user_event(username: str, input_message: str):
    event_type = get_part_content(input_message, 0)
    if event_type == 'key':
        keycode = int(get_part_content(input_message, 1))
        pressed = int(get_part_content(input_message, 2)) == 1
        timestamp = datetime.fromtimestamp(
            int(get_part_content(input_message, 3)) / 1000)
        user_events_logger.info(
            f'{username},{event_type},{timestamp},{keycode},{pressed}')
    elif event_type == 'mouse':
        x = int(get_part_content(input_message, 1))
        y = int(get_part_content(input_message, 2))
        pressed = int(get_part_content(input_message, 3)) == 1
        timestamp = datetime.fromtimestamp(
            int(get_part_content(input_message, 4)) / 1000)
        user_events_logger.info(
            f'{username},{event_type},{timestamp},{x},{y},{pressed}')


async def handle_websocket_put(input_message: str, websocket: WebSocket):
    input_message = await get_modified_file_extension(input_message)
    if websocket.open:
        await websocket.send(input_message)


async def get_modified_file_extension(input_message: str) -> str:
    filepath, filepart_index = get_part(input_message, 4)
    filepath_extension_index = filepath.rfind('.')
    if filepath_extension_index == -1:
        # file has no extension, no point in modifying it
        return input_message

    file_extension = filepath[filepath_extension_index + 1:]
    async with aiohttp.ClientSession() as session:
        async with session.post(
                f'http://{config.middleware_api_host}:{config.middleware_api_port}/validations/file_extension', data=file_extension) as response:
            if response.status == 200:
                new_file_extension = await response.text()
                filepath_without_extension = filepath[:filepath_extension_index]
                filepath_with_new_extension = f'{filepath_without_extension}.{new_file_extension}'
                input_message_without_file_part = input_message[:filepart_index]
                new_input_message = f'{input_message_without_file_part}{str(len(filepath_with_new_extension))}.{filepath_with_new_extension};'
                return new_input_message
            else:
                if response.status != 204:
                    logging.warn(
                        f'Middleware API file extension endpoint returned an unknown status code: {response.status}. Sending original file extension')
                return input_message

from pathlib import Path
import logging
from datetime import datetime

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect
import websockets
import asyncio
import aiohttp

from config import EnvConfig
from custom_loggers import ReverseRotatingFileHandler
from guac_message import get_part, get_part_content, remove_datetime_from_modified_message, \
    GuacamoleClipboardHandler, MiddlewareClipboardError


config = EnvConfig()

logging.basicConfig(level=config.log_level, format='%(asctime)s %(levelname)s %(message)s')

# User events logging

Path(config.user_events_log_path).mkdir(parents=True, exist_ok=True)
reverse_rotating_handler = ReverseRotatingFileHandler(
    f'{config.user_events_log_path}/user_events.log', 'a', config.user_events_log_size, config.user_events_log_backup)
message_only_formatter = logging.Formatter('%(message)s')
reverse_rotating_handler.setFormatter(message_only_formatter)
user_events_logger = logging.getLogger('user-events')
user_events_logger.addHandler(reverse_rotating_handler)
user_events_logger.propagate = False
user_events_log_buffer = []

app = FastAPI()

origins = ['*']

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket('/proxy/tunnel/ws')
async def ws_tunnel_proxy(client_socket: WebSocket):
    await client_socket.accept('guacamole')
    token = client_socket.query_params.get('token')
    guacamole_host = client_socket.headers["X-Guacamole-host"]
    username = await get_username_from_token(token, guacamole_host)
    logging.info(
        f'Accepted client connection. username: {username}, token: {token}')
    guacamole_websocket_uri = f'ws://{guacamole_host}/{client_socket.headers["X-Original-URI"]}'
    async with websockets.connect(guacamole_websocket_uri, subprotocols=['guacamole'], max_size=None,
                                  extra_headers=client_socket.headers.raw, compression=None, max_queue=None) as server_socket:

        # Get tunnel id sent in the first output message
        tunnel_id_message = await server_socket.recv()
        tunnel_id = get_part_content(tunnel_id_message, 1)
        await client_socket.send_bytes(tunnel_id_message)

        logging.info(
            f'Successfully connected to webserver. username: {username}, token: {token}, tunnel_id: {tunnel_id}')
        async def handle_websocket_input():
            clipboard_handler = GuacamoleClipboardHandler(
                True, 8000, config.middleware_api_host, config.middleware_api_port, server_socket.send)
            async for input_message in client_socket.iter_text():
                # input_message = await client_socket.receive_text()
                message_type = get_part_content(input_message, 0)
                if message_type == 'put':  # file upload
                    asyncio.create_task(handle_websocket_put(
                        input_message, server_socket))
                elif message_type == 'blob':  # clipboard blob
                    if not clipboard_handler.try_add_blob(input_message):
                        await server_socket.send(input_message)
                elif message_type == 'end':  # clipboard stream end
                    if clipboard_handler.clipboard_exists(input_message):
                        try:
                            asyncio.create_task(
                                clipboard_handler.send_clipboard(input_message))
                        except MiddlewareClipboardError as e:
                            logging.warn(
                                f'Error sending clipboard to server. Error: {e}')
                        except websockets.exceptions.ConnectionClosed:
                            # Websocket closed mid-transaction
                            pass
                    else:
                        await server_socket.send(input_message)
                else:
                    if message_type == 'mouse' or message_type == 'key':
                        asyncio.create_task(
                            log_user_event(username, tunnel_id, input_message))
                        input_message = remove_datetime_from_modified_message(
                            input_message)
                    if message_type == 'clipboard':  # clipboard stream start
                        clipboard_handler.create_clipboard(input_message)
                    await server_socket.send(input_message)

        async def handle_websocket_output():
            clipboard_handler = GuacamoleClipboardHandler(
                False, 5000, config.middleware_api_host, config.middleware_api_port, client_socket.send_bytes)
            message_sent_date_marker = datetime.now()
            messages_sent_in_interval = 0
            message_load_consecutive_exceeding_counter = 0
            async for output_message in server_socket:
                # messages sometime contain multiple messages
                messages = map(
                    lambda m: f'{m};', output_message.split(';')[:-1])
                modified_messages = ''
                for message in messages:
                    message_type = get_part_content(message, 0)
                    if message_type == 'clipboard':
                        modified_messages += message
                        clipboard_handler.create_clipboard(message)
                    elif message_type == 'blob':
                        if not clipboard_handler.try_add_blob(message):
                            modified_messages += message
                    elif message_type == 'end':
                        if clipboard_handler.clipboard_exists(message):
                            try:
                                asyncio.create_task(
                                    clipboard_handler.send_clipboard(message))
                            except MiddlewareClipboardError as e:
                                logging.warn(
                                    f'Error sending clipboard to client. Error: {e}')
                            except WebSocketDisconnect:
                                # Websocket closed mid-transaction
                                pass
                        else:
                            modified_messages += message
                    else:
                        modified_messages += message

                # Avoid sending empty strings on the channel
                if modified_messages:
                    messages_sent_in_interval += 1
                    # Check if a channel transfers too much data, if so, disconnect client
                    if messages_sent_in_interval > config.message_load_maximum_amount:
                        seconds_since_counter_started = (datetime.now() - message_sent_date_marker).total_seconds()
                        if seconds_since_counter_started <= config.message_load_interval_in_seconds:
                            message_load_consecutive_exceeding_counter += 1
                            allowed_exceeding = f'{message_load_consecutive_exceeding_counter}/{config.message_load_exceed_threshold}'
                            logging.warn(
                                f'Message load exceeded ({allowed_exceeding} times). username: {username}, token: {token}, tunnel_id: {tunnel_id}')
                            if message_load_consecutive_exceeding_counter >= config.message_load_exceed_threshold:
                                logging.warn(
                                    f'Message load exceeded {message_load_consecutive_exceeding_counter} times, disconnecting session. username: {username}, token: {token}, tunnel_id: {tunnel_id}')
                                await server_socket.close()
                        else:
                            message_load_consecutive_exceeding_counter = 0
                        messages_sent_in_interval = 0
                        message_sent_date_marker = datetime.now()

                    await client_socket.send_bytes(modified_messages)

        try:
            # Blocks while running asynchronously
            await asyncio.gather(handle_websocket_input(), handle_websocket_output())

        except websockets.exceptions.ConnectionClosed:
            logging.info(
                f'Webserver connection closed, terminating connection with client socket. username: {username}, token: {token}, tunnel_id: {tunnel_id}')
            await client_socket.close()
        except WebSocketDisconnect:
            logging.info(
                f'Client conneection closed, terminating connection with webserver socket. username: {username}, token: {token}, tunnel_id: {tunnel_id}')
            await server_socket.close()
        finally:
            flush_user_events_logs_buffer()


async def log_user_event(username: str, tunnel_id: str, input_message: str):
    event_type = get_part_content(input_message, 0)
    log_message = None
    if event_type == 'key':
        keycode = int(get_part_content(input_message, 1))
        pressed = int(get_part_content(input_message, 2)) == 1
        timestamp = datetime.fromtimestamp(
            int(get_part_content(input_message, 3)) / 1000)
        log_message = f'{username},{tunnel_id},{event_type},{timestamp},{keycode},{pressed}'
    elif event_type == 'mouse':
        x = int(get_part_content(input_message, 1))
        y = int(get_part_content(input_message, 2))
        pressed = int(get_part_content(input_message, 3)) == 1
        timestamp = datetime.fromtimestamp(
            int(get_part_content(input_message, 4)) / 1000)
        log_message = f'{username},{tunnel_id},{event_type},{timestamp},{x},{y},{pressed}'
    user_events_log_buffer.append(log_message)
    if len(user_events_log_buffer) > config.user_events_log_buffer_size:
        flush_user_events_logs_buffer()


def flush_user_events_logs_buffer():
    combined_log_message = '\n'.join(user_events_log_buffer)
    user_events_logger.info(combined_log_message)
    user_events_log_buffer.clear()

async def handle_websocket_put(input_message: str, websocket: WebSocket):
    input_message = await get_modified_filename(input_message)
    if websocket.open:
        await websocket.send(input_message)


async def get_modified_filename(input_message: str) -> str:
    filepath, filepart_index = get_part(input_message, 4)
    filename_index = filepath.rfind('/')

    filename = filepath[filename_index + 1:]
    async with aiohttp.ClientSession() as session:
        async with session.get(
                f'http://{config.middleware_api_host}:{config.middleware_api_port}/validations/upload/filename?filename={filename}') as response:
            if response.status == 200:
                new_filename = await response.text()
                filepath_without_filename = filepath[:filename_index + 1]
                filepath_with_new_filename = f'{filepath_without_filename}{new_filename}'
                input_message_without_file_part = input_message[:filepart_index]
                new_input_message = f'{input_message_without_file_part}{str(len(filepath_with_new_filename))}.{filepath_with_new_filename};'
                return new_input_message
            else:
                return input_message


async def get_username_from_token(token: str, guacamole_host: str) -> str:
    # This function is duplicated in tunnel_proxy, should be refactored to use a common module
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                    f'http://{guacamole_host}'
                    f'/api/session/data/mysql-shared/self/permissions?token={token}') as response:
                if response.status == 200:
                    response = await response.json()
                    username = list(response['userPermissions'].keys())[0]
                    return username
                else:
                    logging.warn(f'Failed to get username. token: {token}')
                    return ''
    except Exception as e:
        logging.warn(f'Failed to get username. token: {token}, exception: {e}')
        return ''

import base64
from typing import Dict, List, Tuple, Any, Callable, Coroutine

import aiohttp


def get_part(message: str, index: int) -> Tuple[str, int]:
    """
    Get a guacamole message part content & starting index
    """
    part_start_index = 0
    for _ in range(index, 0, -1):
        part_length = message[part_start_index:].split('.')[0]
        part_start_index += len(part_length) + int(part_length) + 2
    part_length = message[part_start_index:].split('.')[0]
    part_content = message[part_start_index + len(part_length) +
                           1: part_start_index + len(part_length) + 1 + int(part_length)]
    return part_content, part_start_index


def get_part_content(message: str, index: int) -> str:
    return get_part(message, index)[0]


def remove_datetime_from_modified_message(input_message: str) -> str:
    """
    In key/mouse messages, we append the client-side datetime for logging purposes.
    This value needs to be removed before we forward it to guacamole
    """
    message_type = get_part_content(input_message, 0)
    if message_type == 'mouse':
        timestamp_part_index = 4
    elif message_type == 'key':
        timestamp_part_index = 3

    _, part_index = get_part(input_message, timestamp_part_index)
    input_message = input_message[:part_index - 1]
    input_message += ';'
    return input_message

def split_multimessage(message: str) -> List[str]:
    """
    Guacamole messages sometimes arrive as multiple concatenated messages, separated by a semicolon.
    You cannot use split(';') to split them because a parts content may contain a semicolon
    """
    message_parts = []
    last_part_found = False
    current_part_index = 0
    while not last_part_found:
        part_content, part_index = get_part(message, current_part_index) 
        if part_index != 0 and message[part_index - 1] == ';':
            message_parts.append(message[0:part_index])
            message = message[part_index:]
            current_part_index = 0
        else:
            current_part_index += 1

        # if content length's length + dot + content length + semicolon == message length (guacamole message format)
        if part_index + len(str(len(part_content))) + 1 + len(part_content) + 1 == len(message):
            last_part_found = True
            message_parts.append(message[0:])
    return message_parts



class MiddlewareClipboardError(Exception):
    pass


class Clipboard:
    def __init__(self):
        self.data: str = ''

    def add_data(self, data: str):
        self.data += data

    async def send(self, middleware_api_host: str, middleware_api_port: str,
                   max_blob_size: int, is_input: bool, stream_index: int,
                   websocket_send_function: Callable[[str], Coroutine[Any, Any, None]]):
        async with aiohttp.ClientSession() as session:
            clipboard_endpoint = 'input_clipboard' if is_input else 'output_clipboard'
            async with session.post(
                    f'http://{middleware_api_host}:{middleware_api_port}/validations/{clipboard_endpoint}', data=self.data) as response:
                if response.status == 200:
                    new_clipboard = await response.text()
                    base64_encoded_clipboard = base64.b64encode(
                        new_clipboard.encode('utf-8')).decode('utf-8')
                    for i in range(0, len(base64_encoded_clipboard), max_blob_size):
                        clipboard_message_blob = base64_encoded_clipboard[i:i +
                                                                          max_blob_size]
                        blob_message = f'4.blob,{len(str(stream_index))}.{stream_index},{len(clipboard_message_blob)}.{clipboard_message_blob};'
                        await websocket_send_function(blob_message)
                    end_message = f'3.end,{len(str(stream_index))}.{stream_index};'
                    await websocket_send_function(end_message)
                else:
                    raise MiddlewareClipboardError(
                        f'Middleware API clipboard endpoint returned an unknown status code: {response.status}')


class GuacamoleClipboardHandler:
    def __init__(self, is_input: bool, max_blob_size: int,
                 middleware_api_host: str, middleware_api_port: str,
                 websocket_send_function: Callable[[str], Coroutine[Any, Any, None]]):
        self.clipboards: List[Clipboard] = []
        self.clipboards: Dict[int, Clipboard] = {}
        self.is_input = is_input
        self.max_blob_size = max_blob_size
        self.middleware_api_host = middleware_api_host
        self.middleware_api_port = middleware_api_port
        self.websocket_send_function = websocket_send_function

    def create_clipboard(self, message: str) -> None:
        stream_index = int(get_part_content(message, 1))
        self.clipboards[stream_index] = Clipboard()

    def try_add_blob(self, message: str) -> bool:
        """
        If the clipboard stream exists, add the blob to it. 
        Return True if the blob was added, False otherwise
        """
        stream_index = int(get_part_content(message, 1))
        if stream_index in self.clipboards:
            blob_content = base64.b64decode(get_part_content(
                message, 2)).decode('utf-8')
            self.clipboards[stream_index].add_data(blob_content)
            return True
        return False

    async def send_clipboard(self, message: str) -> None:
        """
        Return true if clipboard exists, false otherwise
        """
        stream_index = int(get_part_content(message, 1))
        clipboard = self.clipboards[stream_index]
        await clipboard.send(self.middleware_api_host, self.middleware_api_port,
                             self.max_blob_size, self.is_input, stream_index, self.websocket_send_function)
        try:
            del self.clipboards[stream_index]
        except KeyError:
            pass

    def clipboard_exists(self, message: str) -> bool:
        """
        Return true if clipboard exists, false otherwise
        """
        stream_index = int(get_part_content(message, 1))
        return stream_index in self.clipboards

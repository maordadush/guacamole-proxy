from typing import List, Tuple


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


def split_multimessage(multimessage: str) -> List[str]:
    """
    HTTP Proxy someimtes receives mulitple messages merged into one body, separated by semicolons
    `str.split(';')` is invalid here because the content might contain semicolon
    """
    messages = []
    message_start_index = 0
    i = 0
    while i < len(multimessage):
        if multimessage[i] == ';':
            # Found end of message, add the message to the list
            i += 1
            messages.append(multimessage[message_start_index:i])
            message_start_index = i
        elif multimessage[i] == ',':
            i += 1
        else:
            part_length = multimessage[i:].split('.')[0]
            i += len(part_length) + 1 + int(part_length)
    return messages

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

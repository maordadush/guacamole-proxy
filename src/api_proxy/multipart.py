from typing import AsyncGenerator, Generator
from uuid import uuid4


def generate_boundary() -> str:
    return str(uuid4()).replace('-', '')

def get_multipart_body_generator(generator: Generator[str, None, None], bounary: str, filename: str) -> Generator[str, None, None]:
    yield f"--{bounary}\r\n".encode()
    yield f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n".encode()
    yield f"Content-Type: text/plain\r\n\r\n".encode()
    for line in generator:
        yield line
    yield f"\r\n--{bounary}--\r\n".encode()

async def get_multipart_body_async_generator(generator: AsyncGenerator[str, None], bounary: str, filename: str) -> AsyncGenerator[str, None]:
    yield f"--{bounary}\r\n".encode()
    yield f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n".encode()
    yield f"Content-Type: text/plain\r\n\r\n".encode()
    async for line in generator:
        yield line
    yield f"\r\n--{bounary}--\r\n".encode()

import logging

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect
import websockets
import asyncio
from fastapi.middleware.cors import CORSMiddleware

from config import EnvConfig

config = EnvConfig()
config.guacamole_server_port = 8080
config.middleware_api_port = 8084

logging.basicConfig(level=config.log_level)

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
            async def handle_put_input(input_message):
                filepath_part_index = input_message.rfind(',') + 1
                filepath_part = input_message[filepath_part_index:]
                filename = filepath_part[filepath_part.rfind('/') + 1:-1]
                if len(filename.split('.')) > 1 and filename.split('.')[1] == 'doc':
                    input_message = input_message[:-5]
                    input_message += '.pdf;'
                    await asyncio.sleep(15)
                if server_socket.open:
                    await server_socket.send(input_message)

            async def handle_websocket_input():
                while True:
                    input_message = await client_socket.receive_text()
                    if 'put' in input_message:
                        asyncio.create_task(handle_put_input(input_message))
                    else:
                        await server_socket.send(input_message)
            
            async def handle_websocket_output():
                async for output_message in server_socket:
                    await client_socket.send_bytes(output_message)

            # Blocks while both run simultaneously
            await asyncio.gather(handle_websocket_input(), handle_websocket_output())

        except websockets.exceptions.ConnectionClosed:
            logging.info(f'Webserver connection closed, terminating connection with client socket. token: {client_socket.query_params.get("token")}')
            await client_socket.close()
        except WebSocketDisconnect:
            logging.info(f'Client conneection closed, terminating connection with webserver socket. token: {client_socket.query_params.get("token")}')
            await server_socket.close()
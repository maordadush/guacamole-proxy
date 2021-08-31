
import logging
from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect
import websockets
import asyncio
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)

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
async def ws_proxy(websocket: WebSocket):
    await websocket.accept('guacamole')
    logging.info(f'Accepted client connection. token: {websocket.query_params.get("token")}')
    async with websockets.connect(f'ws://host.docker.internal:8080/guacamole/websocket-tunnel?{str(websocket.query_params)}',
        subprotocols=['guacamole'], max_size=None, extra_headers=websocket.headers.raw,
        compression=None, max_queue=None) as webserver_client:

        logging.info(f'Successfully connected to webserver. token: {websocket.query_params.get("token")}')
        try:
            async def handle_put_input(input_message):
                filepath_part_index = input_message.rfind(',') + 1
                filepath_part = input_message[filepath_part_index:]
                filename = filepath_part[filepath_part.rfind('/') + 1:-1]
                if len(filename.split('.')) > 1 and filename.split('.')[1] == 'doc':
                    input_message = input_message[:-5]
                    input_message += '.pdf;'
                    await asyncio.sleep(15)
                if webserver_client.is_open:
                    await webserver_client.send(input_message)

            async def handle_websocket_input():
                while True:
                    input_message = await websocket.receive_text()
                    if 'put' in input_message:
                        asyncio.create_task(handle_put_input(input_message))
                    else:
                        await webserver_client.send(input_message)
            
            async def handle_websocket_output():
                async for output_message in webserver_client:
                    await websocket.send_bytes(output_message)

            # Blocks while both run simultaneously
            await asyncio.gather(handle_websocket_input(), handle_websocket_output())

        except websockets.exceptions.ConnectionClosed:
            logging.info(f'Webserver connection closed, terminating connection with client socket. token: {websocket.query_params.get("token")}')
            await websocket.close()
        except WebSocketDisconnect:
            logging.info(f'Client conneection closed, terminating connection with webserver socket. token: {websocket.query_params.get("token")}')
            await webserver_client.close()
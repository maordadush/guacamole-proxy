import logging

from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
import aiohttp

from config import EnvConfig

config = EnvConfig()
config.guacamole_server_port = 8080

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

@app.get('/files')
async def proxy_download(request: Request):
    original_uri = request.headers['x-original-uri']
    async with aiohttp.ClientSession() as session:
        async with session.get(f'http://{config.guacamole_server_host}:{config.guacamole_server_port}{original_uri}',
            params=request.query_params) as response:

            return Response(content=(await response.read()), media_type='application/octet-stream')

@app.post('/files')
async def proxy_download(request: Request):
    original_uri = request.headers['x-original-uri']
    async with aiohttp.ClientSession()  as session:
        async with session.post(f'http://{config.guacamole_server_host}:{config.guacamole_server_port}{original_uri}',
            params=request.query_params, data=(await request.body())) as response:

            return Response(content=(await response.read()), media_type='application/octet-stream')
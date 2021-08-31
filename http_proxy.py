import logging
from fastapi import FastAPI, Response, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import aiohttp

logging.basicConfig(level=logging.DEBUG)

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
        async with session.get(f'http://host.docker.internal:8080{original_uri}', params=request.query_params) as response:
            return Response(content=(await response.read()), media_type='application/octet-stream')

@app.post('/files')
async def proxy_download(request: Request):
    original_uri = request.headers['x-original-uri']
    async with aiohttp.ClientSession()  as session:
        async with session.post(f'http://host.docker.internal:8080{original_uri}', params=request.query_params, data=(await request.body())) as response:
            return Response(content=(await response.read()), media_type='application/octet-stream')
import logging

import requests
from fastapi import FastAPI, Response, Request
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


@app.get('/files')
async def proxy_download(request: Request):
    original_uri = request.headers['x-original-uri']
    octet_stream_media_type = 'application/octet-stream'
    guacamole_response = requests.get(
        f'http://{config.guacamole_server_host}:{config.guacamole_server_port}{original_uri}', params=request.query_params)
    if not guacamole_response.ok:
        return Response(status_code=500)

    original_file_content = guacamole_response.text
    middleware_response = requests.post(
        f'http://{config.middleware_api_host}:{config.middleware_api_port}/download', data=original_file_content)
    if middleware_response.status_code == 204:
        return Response(original_file_content, media_type=octet_stream_media_type)

    elif middleware_response.status_code == 200:
        modified_file_content = middleware_response.text
        return Response(modified_file_content, media_type=octet_stream_media_type)

    elif middleware_response.status_code == 403:
        return Response(status_code=403)

    return Response(status_code=500)


@app.post('/files')
async def proxy_upload(request: Request):
    original_uri = request.headers['x-original-uri']
    octet_stream_media_type = 'application/octet-stream'
    guacamole_upload_uri = f'http://{config.guacamole_server_host}:{config.guacamole_server_port}{original_uri}'
    
    original_file_content = await request.body()
    middleware_response = requests.post(f'http://{config.middleware_api_host}:{config.middleware_api_port}/upload', data=original_file_content)

    if middleware_response.status_code == 204:
        guacamole_response = requests.post(guacamole_upload_uri, params=request.query_params, data=original_file_content)
        return Response(guacamole_response.text, status_code=guacamole_response.status_code, media_type=octet_stream_media_type)

    elif middleware_response.status_code == 200:
        modified_file_content = middleware_response.content
        guacamole_response = requests.post(guacamole_upload_uri, params=request.query_params, data=modified_file_content)
        return Response(guacamole_response.text, status_code=guacamole_response.status_code, media_type=octet_stream_media_type)
    
    elif middleware_response.status_code == 403:
        return Response(status_code=403)

    return Response(status_code=500)

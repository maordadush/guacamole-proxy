import json
import logging

import requests
from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from config import EnvConfig
from zip import ZipFile, ZIP_DEFLATED

config = EnvConfig()

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


@app.get('/test_stream')
async def foo(request: Request):
    async def generator():
        # yield b'\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\\0\0\0\0\0\0\0\0\0\0'
        # await asyncio.sleep(5) # Simulate long running task to retrieve data
        yield 'data'
    return StreamingResponse(generator())


@app.get('/files')
async def proxy_download(request: Request):
    original_uri = request.headers['x-original-uri']
    octet_stream_media_type = 'application/octet-stream'

    def get_file_content_iterator():
        # Wrapping file content in a zip in order to return any valid data ASAP (zip file header)
        zip_stream = ZipFile(mode='w')
        zip_header, zip_info = zip_stream.write_header('test', compress_type=ZIP_DEFLATED)
        yield zip_header

        guacamole_request = {
            'url': f'http://{config.guacamole_server_host}:{config.guacamole_server_port}{original_uri}',
            'params': request.query_params._dict
        }
        middleware_response = requests.post(f'http://{config.middleware_api_host}:{config.middleware_api_port}/download',
                                            data=json.dumps(guacamole_request), stream=True)

        if middleware_response.status_code == 200:
            for chunk in zip_stream.write_content(middleware_response.iter_content(1024*1024), zip_info):
                yield chunk
        for chunk in zip_stream._ZipFile__close():
            yield chunk
        

    return StreamingResponse(get_file_content_iterator(), media_type=octet_stream_media_type)


@app.post('/files')
async def proxy_upload(request: Request):
    original_uri = request.headers['x-original-uri']
    octet_stream_media_type = 'application/octet-stream'
    guacamole_upload_uri = f'http://{config.guacamole_server_host}:{config.guacamole_server_port}{original_uri}'

    original_file_content = await request.body()
    middleware_response = requests.post(
        f'http://{config.middleware_api_host}:{config.middleware_api_port}/upload', data=original_file_content)

    if middleware_response.status_code == 204:
        guacamole_response = requests.post(
            guacamole_upload_uri, params=request.query_params, data=original_file_content)
        return Response(guacamole_response.text, status_code=guacamole_response.status_code, media_type=octet_stream_media_type)

    elif middleware_response.status_code == 200:
        modified_file_content = middleware_response.content
        guacamole_response = requests.post(
            guacamole_upload_uri, params=request.query_params, data=modified_file_content)
        return Response(guacamole_response.text, status_code=guacamole_response.status_code, media_type=octet_stream_media_type)

    elif middleware_response.status_code == 403:
        return Response(status_code=403)

    return Response(status_code=500)

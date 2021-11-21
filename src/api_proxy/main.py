import json
import logging
from urllib.parse import quote

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


@app.get('/proxy/api/files')
async def proxy_download(request: Request):
    token = request.query_params.get('token', '')
    guacamole_host = request.headers['x-guacamole-host']
    username = await get_username_from_token(token, guacamole_host)
    original_uri = request.headers['x-original-uri']
    original_filename = original_uri[original_uri.rfind('/') + 1:]
    zipped_filename = f'{original_filename}.zip'
    octet_stream_media_type = 'application/octet-stream'

    def get_file_content_iterator():
        # Wrapping file content in a zip in order to return any valid data ASAP (zip file header)
        zip_stream = ZipFile(mode='w')
        zip_header, zip_info = zip_stream.write_header(
            original_filename, compress_type=ZIP_DEFLATED)
        yield zip_header

        guacamole_request = {
            'url': f'http://{guacamole_host}{original_uri}',
            'params': request.query_params._dict
        }
        middleware_response = requests.post(f'http://{config.middleware_api_host}:{config.middleware_api_port}/validations/download',
                                            data=json.dumps(guacamole_request), stream=True)

        if middleware_response.status_code == 200:
            logging.info(
                f'Download file middleware vallidation successful. Username: {username}, filename: {original_filename}, token: {token}')
            for chunk in zip_stream.write_content(middleware_response.iter_content(1024*1024), zip_info):
                yield chunk
        else:
            logging.warn(
                f'Download file middleware validation failed. Username: {username}, filename: {original_filename},'
                f' status_code: {middleware_response.status_code}, body: {middleware_response.content}, token: {token}')
            raise StopIteration()
        for chunk in zip_stream._ZipFile__close():
            yield chunk

    return StreamingResponse(get_file_content_iterator(), media_type=octet_stream_media_type, headers={'Content-Disposition': f'attachment; filename="{zipped_filename}"'})


@app.post('/proxy/api/files')
async def proxy_upload(request: Request):
    token = request.query_params.get('token', '')
    guacamole_host = request.headers['x-guacamole-host']
    username = await get_username_from_token(token, guacamole_host)
    original_uri = request.headers['x-original-uri']
    filename = original_uri[original_uri.rfind('/') + 1:]
    octet_stream_media_type = 'application/octet-stream'
    url_encoded_original_uri = quote(original_uri, safe='/')
    guacamole_upload_uri = f'http://{guacamole_host}{url_encoded_original_uri}'

    logging.debug(
        f'Received upload file request. Username: {username}, filename: {filename}, token: {token}')
    original_file_content = await request.body()
    middleware_response = requests.post(
        f'http://{config.middleware_api_host}:{config.middleware_api_port}/validations/upload', data=original_file_content, stream=True)

    if middleware_response.status_code == 200:
        file_content = middleware_response.iter_content(1024*1024)
    elif middleware_response.status_code == 204:
        file_content = original_file_content
    else:
        logging.warn(
            f'Upload file middleware validation failed. Username: {username}, filename: {filename}, token: {token}')
        return Response(status_code=middleware_response.status_code)

    logging.info(f'Upload file successful middleware validation. Username: {username}, filename: {filename},'
                 f' status_code: {middleware_response.status_code}, token: {token}')
    guacamole_response = requests.post(
        guacamole_upload_uri, params=request.query_params, data=file_content)
    return Response(guacamole_response.text, headers=guacamole_response.headers, status_code=guacamole_response.status_code, media_type=octet_stream_media_type)

async def get_username_from_token(token: str, guacamole_host: str) -> str:
    # This function is duplicated in tunnel_proxy, should be refactored to use a common module
    try:
        response = requests.get(
            f'http://{guacamole_host}/api/session/data/mysql-shared/self/permissions?token={token}')
        if response.status_code == 200:
            username = list(response.json()['userPermissions'].keys())[0]
            return username
        else:
            logging.warn(
                f'Failed to get username. token: {token}, error: {response.status_code}: {response.text}')
            return ''
    except Exception as e:
        logging.warn(
            f'Failed to get username. token: {token}, error: {str(e)}')
        return ''

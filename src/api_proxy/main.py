import logging
from urllib.parse import quote

import requests
import aiohttp
from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

from config import EnvConfig
from zip import ZipFile, ZIP_DEFLATED
from multipart import get_multipart_body_generator, generate_boundary, get_multipart_body_async_generator

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
        modified_filename = None
        file_modification_timeout = 1.5
        try:
            filename_modification_response = requests.get(
                f'http://{config.middleware_api_host}:{config.middleware_api_port}/validations/download/filename?filename={original_filename}',
                timeout=file_modification_timeout)
            if filename_modification_response.status_code == 200:
                modified_filename = filename_modification_response.text
            else:
                logging.error(
                    f'Filename modification request failed. status_code: {filename_modification_response.status_code}, text: {filename_modification_response.text}')
        except requests.exceptions.ReadTimeout:
            logging.error(f'Filename modification request timed out. Timeout: {str(file_modification_timeout)}')
            raise StopIteration()

        # Wrapping file content in a zip in order to return any valid data ASAP (zip file header)
        zip_stream = ZipFile(mode='w')
        zip_header, zip_info = zip_stream.write_header(
            modified_filename, compress_type=ZIP_DEFLATED)
        yield zip_header

        guacamole_response = requests.get(
            f'http://{guacamole_host}{original_uri}', params=request.query_params, stream=True)
        boundary = generate_boundary()
        middleware_request_body_generator = get_multipart_body_generator(
            guacamole_response.iter_content(chunk_size=1024 * 1024), boundary, original_filename)
        middleware_response = requests.post(f'http://{config.middleware_api_host}:{config.middleware_api_port}/validations/download',
                                            data=middleware_request_body_generator, stream=True, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})

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

    middleware_response_iterator = None
    session = aiohttp.ClientSession()
    boundary = generate_boundary()
    async_multipart_body_generator = get_multipart_body_async_generator(
        request.stream(), boundary, filename)

    middleware_response = await session.post(f'http://{config.middleware_api_host}:{config.middleware_api_port}/validations/upload',
                                             data=async_multipart_body_generator, headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    middleware_response_iterator = middleware_response.content.iter_any()

    if middleware_response.status == 200:
        logging.info(f'Upload file successful middleware validation. Username: {username}, filename: {filename},'
                     f' status_code: {middleware_response.status}, token: {token}')
        guacamole_response = await session.post(guacamole_upload_uri, data=middleware_response_iterator, params=request.query_params,
                                                headers={'Content-Type': octet_stream_media_type})
        guacamole_response_text = await guacamole_response.text()
        if guacamole_response.status != 200:
            logging.warn(
                f'Upload file to guacamole failed. Guacamole response: {guacamole_response_text}, Username: {username}, filename: {filename}, status_code: {guacamole_response.status}, token: {token}')
        response = Response(guacamole_response_text, headers=guacamole_response.headers,
                            status_code=guacamole_response.status, media_type=octet_stream_media_type)
        guacamole_response.close()
    else:
        logging.warn(
            f'Upload file middleware validation failed. Username: {username}, filename: {filename}, token: {token}, status_code: {middleware_response.status}')
        response = Response(status_code=middleware_response.status)
    middleware_response.close()
    await session.close()
    return response


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

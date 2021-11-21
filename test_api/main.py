import json

import requests
import asyncio
from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse

app = FastAPI()

origins = ['*']

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post('/validations/upload')
async def verify_upload(request: Request):
    try:
        content = (await request.body()).decode('utf-8')
        if content.startswith('CHANGE_ME'):
            return Response(status_code=200, content='CHANGED')
        else:
            await asyncio.sleep(5)
            return Response(status_code=204)
    except:
        await asyncio.sleep(5)
        return Response(status_code=204)


@app.post('/validations/download')
async def verify_download(request: Request):
    body = json.loads(await request.body())
    url = body['url']
    params = body['params']
    response = requests.get(url, params=params, stream=True)
    def generate():
        first_chunk = True
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                try:
                    if first_chunk and chunk.decode('utf-8').startswith('CHANGE_ME'):
                        yield 'CHANGED'
                    else:
                        yield chunk
                    first_chunk = False
                except StopIteration as e:
                    raise e
                except Exception:
                    yield chunk
    return StreamingResponse(generate(), media_type='application/octet-stream')

@app.post('/validations/file_extension')
async def modify_file_extension(request: Request):
    file_extesion = (await request.body()).decode('utf-8')
    if file_extesion == 'docx':
        return Response('pdf'.encode(), status_code=200)
    return Response(status_code=204)

@app.post('/validations/input_clipboard')
async def modify_input_clipboard(request: Request):
    clipboard = (await request.body()).decode('utf-8')
    if 'virus' in clipboard:
        return Response('', status_code=200)
    clipboard = clipboard.replace('123', '321')
    return Response(clipboard, status_code=200)

@app.post('/validations/output_clipboard')
async def modify_output_clipboard(request: Request):
    clipboard = (await request.body()).decode('utf-8')
    if 'virus' in clipboard:
        return Response('', status_code=200)
    clipboard = clipboard.replace('abc', 'cba')
    return Response(clipboard, status_code=200)

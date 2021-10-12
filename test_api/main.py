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
    await asyncio.sleep(10)
    return Response(status_code=204)

@app.post('/validations/download')
async def verify_download(request: Request):
    body = json.loads(await request.body())
    url = body['url']
    params = body['params']
    response = requests.get(url, params=params, stream=True)
    await asyncio.sleep(10)  # Validating file
    return StreamingResponse(response.iter_content(1024*1024))

@app.post('/validations/file_extension')
async def modify_file_extension(request: Request):
    file_extesion = (await request.body()).decode('utf-8')
    if file_extesion == 'docx':
        return Response('pdf'.encode(), status_code=200)
    if file_extesion == 'jpg':
        return Response('jpeg'.encode(), status_code=200)
    return Response(status_code=204)

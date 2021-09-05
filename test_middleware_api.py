import logging

from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = ['*']

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post('/upload')
async def verify_upload(request: Request):
    try:
        content = str(await request.body())
        if 'BAD' in content:
            return Response(status_code=403)
        elif 'GOOD_CHANGE' in content:
            return Response(content=str.encode('new file content in town'), status_code=200)
        return Response(status_code=204)
    except:
        logging.debug('Request body is not utf')
        return Response(status_code=204)

@app.post('/download')
async def verify_download(request: Request):
    try:
        content = str(await request.body())
        if 'BAD' in content:
            return Response(status_code=403)
        elif 'GOOD_CHANGE' in content:
            return Response(content=str.encode('new file content in town!!!'), status_code=200)
        return Response(status_code=204)
    except:
        logging.debug('Request body is not utf')
        return Response(status_code=204)

@app.post('/file_extension')
async def modify_file_extension(request: Request):
    file_extesion = (await request.body()).decode('utf-8')
    if file_extesion == 'docx':
        return Response('pdf'.encode(), status_code=200)
    if file_extesion == 'jpg':
        return Response('jpeg'.encode(), status_code=200)
    return Response(status_code=204)

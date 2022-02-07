import os

from io import BytesIO
from datetime import datetime
from contextlib import suppress

from aiohttp import ClientSession

from disnake import Webhook, Embed, File

from fastapi import FastAPI, Request, BackgroundTasks, status
from fastapi.responses import Response, RedirectResponse
from fastapi.templating import Jinja2Templates

from jinja2 import TemplateNotFound

from async_lru import alru_cache

STATS_WH = os.environ.get("STATS_WH")
IPINFO_TOKEN = os.environ.get("IPINFO_TOKEN")


app = FastAPI(
    title="",
    description="",
    docs_url=None,
    openapi_url=None,
    redoc_url=None,
)

templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
async def on_startup():
    app.session = ClientSession()


@app.on_event("shutdown")
async def on_shutdown():
    await app.session.close()


@alru_cache(maxsize=100)
async def ipinfo(ip: str):
    async with app.session.get(
        f"https://ipinfo.io/{ip}", headers={"Authorization": f"Bearer {IPINFO_TOKEN}"}
    ) as r:
        return await r.json()


async def wh_send(*args, **kwargs) -> None:
    wh = Webhook.from_url(STATS_WH, session=app.session)

    await wh.send(*args, **kwargs)


def listify(dic: dict):
    return "".join([f"- {k}: {v}\n" for k, v in dic.items()])


async def log_request(request: Request):
    e = Embed(description="", color=0x03A9F4)

    e.title = "New Request"

    e.description += f"`{request.method}` `{request.url}`\n"
    e.description += f"From: `{request.client.host}:{request.client.port}`\n\n"

    if info := await ipinfo(request.client.host):
        e.description += "**IP info:**\n```\n"
        e.description += listify(info)
        e.description += "```\n"

    if headers := request.headers:
        e.description += "**Headers:**\n```\n"
        e.description += listify(headers)
        e.description += "```\n"

    if cookies := request.cookies:
        e.description += "**Cookies:**\n```\n"
        e.description += listify(cookies)
        e.description += "```\n"

    if query := dict(request.query_params):
        e.description += "**Query:**\n```\n"
        e.description += listify(query)
        e.description += "```\n"

    content = None
    files = []

    if body := await request.body():
        if len(body) > 2000:
            fp = BytesIO(body)
            fp.seek(0)
            files.append(File(fp, "body.txt"))

        else:
            content = f'```{body.decode("utf-8")}```'

    e.timestamp = datetime.utcnow()

    await wh_send(content, embed=e, files=files)


@app.api_route(
    "/{path_name:path}",
    methods=[
        "GET",
        "POST",
        "OPTIONS",
        "HEAD",
        "PUT",
        "DELETE",
        "PATCH",
        "CONNECT",
        "TRACE",
    ],
)
async def catch(request: Request, background_tasks: BackgroundTasks):
    await request.body()  # this will chache the body so fastapi doesn't freak out in the background task

    background_tasks.add_task(log_request, request)

    host = request.url.hostname

    with suppress(TemplateNotFound):
        tr = templates.TemplateResponse(f"{host}.html", {"request": request})

        if tr and request.method == "GET":
            if request.url.path != "/":
                return RedirectResponse("/")

            return tr

    return Response(status_code=status.HTTP_204_NO_CONTENT)

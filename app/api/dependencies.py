from fastapi import Request

from app.core.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container

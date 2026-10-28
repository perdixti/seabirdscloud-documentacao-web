from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field, SecretStr

from .github import GitHubPublisher
from .models import DocumentInput


class ReviewInput(BaseModel):
    directory: str = Field(default="", max_length=4096)
    document: DocumentInput


class SiteReviewInput(BaseModel):
    directory: str = Field(min_length=1, max_length=4096)


class PlanInput(BaseModel):
    token: str = Field(max_length=64)


class PublishInput(PlanInput):
    selected: list[str] = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)


class GitHubSettingsInput(BaseModel):
    directory: str = Field(default="", max_length=4096)
    name: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=254)
    token_action: Literal["keep", "replace", "remove"] = "keep"
    token: SecretStr = SecretStr("")


def github_router(settings, filesystem_access, publisher=None):
    router = APIRouter(prefix="/github")
    publisher = publisher or GitHubPublisher(settings.data_dir)

    @router.get("/settings")
    def github_settings(request: Request, directory: str = ""):
        filesystem_access(request)
        return publisher.settings_status(directory)

    @router.post("/settings")
    def configure_github(payload: GitHubSettingsInput, request: Request):
        filesystem_access(request)
        return publisher.configure(
            payload.name,
            payload.email,
            payload.token_action,
            payload.token.get_secret_value(),
            payload.directory,
        )

    @router.post("/review")
    def review(payload: ReviewInput, request: Request):
        filesystem_access(request)
        return publisher.inspect(payload.directory, payload.document)

    @router.post("/review-site")
    def review_site(payload: SiteReviewInput, request: Request):
        filesystem_access(request)
        return publisher.inspect(payload.directory, DocumentInput(), site_only=True)

    @router.post("/sync")
    def sync(payload: PlanInput, request: Request):
        filesystem_access(request)
        return publisher.sync(payload.token)

    @router.post("/publish")
    def publish(payload: PublishInput, request: Request):
        filesystem_access(request)
        return publisher.publish(payload.token, payload.selected, payload.message)

    @router.post("/publications/{identifier}/retry")
    def retry(identifier: str, request: Request):
        filesystem_access(request)
        return publisher.retry(identifier)

    @router.get("/publications/{identifier}/runs")
    def runs(identifier: str, request: Request):
        filesystem_access(request)
        return publisher.runs(identifier)

    return router

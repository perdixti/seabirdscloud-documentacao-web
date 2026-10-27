from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

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


def github_router(settings, filesystem_access):
    router = APIRouter(prefix="/github")
    publisher = GitHubPublisher(settings.data_dir)

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

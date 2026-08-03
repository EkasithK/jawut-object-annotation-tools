"""Project lifecycle endpoints backing the welcome screen."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from jawut import config, session
from jawut.models import Envelope
from jawut.services import projects

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class ProjectSummary(BaseModel):
    name: str
    path: Path
    schema_version: int
    created_at: datetime

    @classmethod
    def of(cls, project: projects.Project) -> ProjectSummary:
        return cls(
            name=project.name,
            path=project.path,
            schema_version=project.schema_version,
            created_at=project.created_at,
        )


class RecentEntry(BaseModel):
    name: str
    path: Path
    opened_at: datetime


class WelcomeState(BaseModel):
    """Everything the welcome screen needs in one call."""

    open_project: ProjectSummary | None
    recent: list[RecentEntry]
    default_projects_dir: Path


class CreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_dir: Path


class OpenRequest(BaseModel):
    path: Path


class ForgetRequest(BaseModel):
    path: Path


class RecentList(BaseModel):
    recent: list[RecentEntry]


@router.get("")
async def welcome_state() -> Envelope[WelcomeState]:
    project = session.current()
    return Envelope(
        data=WelcomeState(
            open_project=None if project is None else ProjectSummary.of(project),
            recent=[
                RecentEntry(name=p.name, path=p.path, opened_at=p.opened_at)
                for p in config.existing_recent_projects()
            ],
            default_projects_dir=config.default_projects_dir(),
        )
    )


@router.post("", status_code=201)
async def create_project(payload: CreateRequest) -> Envelope[ProjectSummary]:
    try:
        project = projects.create(payload.parent_dir, payload.name)
    except projects.ProjectError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=422, detail=f"could not create the project: {exc}"
        ) from exc

    session.set_current(project)
    config.remember_project(project.name, project.path)
    return Envelope(data=ProjectSummary.of(project))


@router.post("/open")
async def open_existing(payload: OpenRequest) -> Envelope[ProjectSummary]:
    try:
        project = projects.open_project(payload.path)
    except projects.ProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=422, detail=f"could not open the project: {exc}"
        ) from exc

    session.set_current(project)
    config.remember_project(project.name, project.path)
    return Envelope(data=ProjectSummary.of(project))


@router.post("/close", status_code=200)
async def close_current() -> Envelope[WelcomeState]:
    session.clear()
    return await welcome_state()


@router.post("/forget")
async def forget(payload: ForgetRequest) -> Envelope[RecentList]:
    """Drop a project from the recent list without touching it on disk."""
    config.forget_project(payload.path)
    return Envelope(
        data=RecentList(
            recent=[
                RecentEntry(name=p.name, path=p.path, opened_at=p.opened_at)
                for p in config.existing_recent_projects()
            ]
        )
    )

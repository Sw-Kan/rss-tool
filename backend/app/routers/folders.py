"""M2 目录管理。收藏是虚拟目录，不落表。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from ..deps import CurrentUser, DbSession
from ..models import Folder, Subscription
from ..schemas import FolderCounts, FolderIn, FolderListOut, FolderOut
from ..services import counts

router = APIRouter(prefix="/api/folders", tags=["folders"])


@router.get("", response_model=FolderListOut)
def list_folders(user: CurrentUser, db: DbSession) -> FolderListOut:
    folders = db.scalars(
        select(Folder).where(Folder.user_id == user.id).order_by(Folder.position, Folder.name)
    ).all()
    summary = counts.sidebar_summary(db, user.id)

    feed_counts = dict(
        db.execute(
            select(Subscription.folder_id, func.count())
            .where(Subscription.user_id == user.id, Subscription.folder_id.is_not(None))
            .group_by(Subscription.folder_id)
        ).all()
    )
    ungrouped_feeds = (
        db.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.user_id == user.id, Subscription.folder_id.is_(None))
        )
        or 0
    )

    return FolderListOut(
        items=[
            FolderOut(
                id=folder.id,
                name=folder.name,
                position=folder.position,
                feed_count=feed_counts.get(folder.id, 0),
                unread_count=summary.folders.get(folder.id, 0),
            )
            for folder in folders
        ],
        ungrouped=FolderCounts(feed_count=ungrouped_feeds, unread_count=summary.ungrouped),
    )


@router.post("", response_model=FolderOut, status_code=status.HTTP_201_CREATED)
def create_folder(payload: FolderIn, user: CurrentUser, db: DbSession) -> FolderOut:
    if db.scalar(select(Folder).where(Folder.user_id == user.id, Folder.name == payload.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="同名目录已存在")

    last = db.scalar(select(func.max(Folder.position)).where(Folder.user_id == user.id))
    folder = Folder(user_id=user.id, name=payload.name, position=(last or 0) + 1)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return FolderOut(
        id=folder.id, name=folder.name, position=folder.position, feed_count=0, unread_count=0
    )


@router.patch("/{folder_id}", response_model=FolderOut)
def rename_folder(folder_id: str, payload: FolderIn, user: CurrentUser, db: DbSession) -> FolderOut:
    folder = _owned_folder(db, user.id, folder_id)
    clash = db.scalar(
        select(Folder).where(
            Folder.user_id == user.id, Folder.name == payload.name, Folder.id != folder_id
        )
    )
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="同名目录已存在")

    folder.name = payload.name
    db.commit()
    summary = counts.sidebar_summary(db, user.id)
    feed_count = (
        db.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.user_id == user.id, Subscription.folder_id == folder.id)
        )
        or 0
    )
    return FolderOut(
        id=folder.id,
        name=folder.name,
        position=folder.position,
        feed_count=feed_count,
        unread_count=summary.folders.get(folder.id, 0),
    )


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(folder_id: str, user: CurrentUser, db: DbSession) -> None:
    """删除目录：源回落到未分组，不删源也不删文章。"""
    folder = _owned_folder(db, user.id, folder_id)
    for subscription in db.scalars(
        select(Subscription).where(
            Subscription.user_id == user.id, Subscription.folder_id == folder.id
        )
    ):
        subscription.folder_id = None
    db.delete(folder)
    db.commit()


def _owned_folder(db: DbSession, user_id: str, folder_id: str) -> Folder:
    folder = db.get(Folder, folder_id)
    if folder is None or folder.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="目录不存在")
    return folder

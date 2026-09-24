"""M2 OPML 导入导出。"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from ..deps import CurrentUser, DbSession
from ..schemas import OpmlImportOut
from ..services import opml_service

router = APIRouter(prefix="/api/opml", tags=["opml"])

MAX_OPML_BYTES = 5 * 1024 * 1024


@router.get("/export")
def export_opml(user: CurrentUser, db: DbSession) -> Response:
    content = opml_service.export_opml(db, user)
    return Response(
        content=content,
        media_type="text/x-opml; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="rss-tool.opml"'},
    )


@router.post("/import", response_model=OpmlImportOut)
async def import_opml(
    user: CurrentUser, db: DbSession, file: UploadFile = File(...)
) -> OpmlImportOut:
    raw = await file.read(MAX_OPML_BYTES + 1)
    if len(raw) > MAX_OPML_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail="文件过大")
    try:
        imported, skipped, errors = await opml_service.import_opml(db, user, raw)
    except opml_service.OpmlError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OpmlImportOut(imported=imported, skipped=skipped, errors=errors)

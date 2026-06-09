from __future__ import annotations

import string

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_container, require_global_api_key
from app.schemas import TemplateCreateRequest, TemplateUpdateRequest

router = APIRouter(prefix="/api/templates", tags=["templates"], dependencies=[Depends(require_global_api_key)])


@router.get("")
async def list_templates(container=Depends(get_container)):
    return {"items": [_serialize_template(item) for item in container.template_repo.list_all()]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_template(payload: TemplateCreateRequest, container=Depends(get_container)):
    template_id = container.template_repo.create(
        name=payload.name,
        description=payload.description,
        template=payload.template,
        category=payload.category,
        preview_image_path=payload.preview_image_path,
    )
    return {"id": template_id}


@router.put("/{template_id}")
async def update_template(template_id: int, payload: TemplateUpdateRequest, container=Depends(get_container)):
    updated = container.template_repo.update(
        template_id,
        name=payload.name,
        description=payload.description,
        template=payload.template,
        category=payload.category,
        preview_image_path=payload.preview_image_path,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return {"ok": True}


@router.delete("/{template_id}")
async def delete_template(template_id: int, container=Depends(get_container)):
    deleted = container.template_repo.delete(template_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return {"ok": True}


def _serialize_template(template: dict) -> dict:
    return {
        **template,
        "variables": extract_template_variables(template["template"]),
    }


def extract_template_variables(template: str) -> list[str]:
    formatter = string.Formatter()
    variables: list[str] = []
    for _, field_name, _, _ in formatter.parse(template):
        if field_name and field_name not in variables:
            variables.append(field_name)
    return variables

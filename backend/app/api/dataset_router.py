from __future__ import annotations
import io
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response as FastAPIResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings, STORAGE_DIR
from app.core.security import safe_filename, user_storage_dir
from app.models import get_db, Dataset
from app.models.user import User
from app.api.auth_router import get_current_user
from app.analytics import (
    load_dataframe, save_dataframe, profile_dataset, frame_records,
    run_cleaning, build_cleaning_preview,
    run_eda, generate_charts,
    build_ai_context, ai_explain,
    generate_pdf_report,
)

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


class CleanIn(BaseModel):
    drop_duplicates: bool = False
    trim_whitespace: bool = True
    fill_numeric: str = Field(default='none', pattern=r'^(none|median|mean|zero)$')
    fill_categorical: str = Field(default='none', pattern=r'^(none|mode|unknown)$')
    preview_only: bool = False


class ChatIn(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    provider: str = Field(default='openai', pattern=r'^(openai|gemini)$')


def get_owned_dataset(dataset_id: str, user: User, db: Session) -> Dataset:
    ds = db.scalars(select(Dataset).where(Dataset.id == dataset_id, Dataset.user_id == user.id)).first()
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return ds


# ── List datasets ─────────────────────────────────────────────────────────────

@router.get("")
def list_datasets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Dataset).where(Dataset.user_id == user.id).order_by(Dataset.created_at.desc())).all()
    return {'datasets': [
        {'id': d.id, 'filename': d.filename, 'row_count': d.row_count, 'col_count': d.col_count,
         'file_size_bytes': d.file_size_bytes, 'created_at': d.created_at.isoformat()}
        for d in rows
    ]}


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filename = safe_filename(file.filename or 'dataset.csv')
    ext = Path(filename).suffix.lower()
    if ext not in ('.csv', '.xlsx', '.xls'):
        raise HTTPException(status_code=415, detail="Only CSV and Excel (.xlsx, .xls) files are supported.")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds the {settings.max_upload_mb} MB upload limit.")
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    did = str(uuid.uuid4())
    folder = user_storage_dir(user.id)
    original_path = folder / f"{did}_original{ext}"
    current_path = folder / f"{did}_current{ext}"
    original_path.write_bytes(data)
    current_path.write_bytes(data)

    ds = Dataset(
        id=did, user_id=user.id, filename=filename,
        stored_path=str(current_path), original_path=str(original_path),
        file_size_bytes=len(data), cleaning_log='[]',
    )
    try:
        df = load_dataframe(ds)
        if df.shape[1] == 0:
            raise HTTPException(status_code=422, detail="No columns found in dataset.")
        if len(df) > 500_000 or len(df.columns) > 500:
            raise HTTPException(status_code=413, detail="Dataset exceeds supported limits (500k rows / 500 columns).")
        ds.row_count = len(df)
        ds.col_count = len(df.columns)
        db.add(ds)
        db.commit()
    except HTTPException:
        original_path.unlink(missing_ok=True)
        current_path.unlink(missing_ok=True)
        raise
    except Exception as e:
        original_path.unlink(missing_ok=True)
        current_path.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Could not read dataset: {e}") from e

    prof = profile_dataset(df)
    return {
        'dataset': {
            'id': ds.id, 'filename': ds.filename,
            'row_count': ds.row_count, 'col_count': ds.col_count,
            'file_size_bytes': ds.file_size_bytes,
            'profile': prof,
            'preview': {'columns': [str(c) for c in df.columns], 'rows': frame_records(df, 50)},
        }
    }


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/{dataset_id}/profile")
def dataset_profile(dataset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = get_owned_dataset(dataset_id, user, db)
    df = load_dataframe(ds)
    return {'dataset_id': ds.id, 'filename': ds.filename, 'profile': profile_dataset(df)}


# ── Preview ───────────────────────────────────────────────────────────────────

@router.get("/{dataset_id}/preview")
def dataset_preview(dataset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = get_owned_dataset(dataset_id, user, db)
    df = load_dataframe(ds)
    return {
        'columns': [str(c) for c in df.columns],
        'rows': frame_records(df, 200),
        'total_rows': len(df),
        'total_cols': len(df.columns),
    }


# ── Clean ─────────────────────────────────────────────────────────────────────

@router.post("/{dataset_id}/clean")
def clean_dataset(dataset_id: str, data: CleanIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = get_owned_dataset(dataset_id, user, db)
    df = load_dataframe(ds)
    opts = {
        'trim_whitespace': data.trim_whitespace,
        'drop_duplicates': data.drop_duplicates,
        'fill_numeric': data.fill_numeric,
        'fill_categorical': data.fill_categorical,
    }

    if data.preview_only:
        preview = build_cleaning_preview(df, opts)
        return {'preview': True, **preview}

    cleaned_df, actions, before, after = run_cleaning(df.copy(), opts)
    save_dataframe(cleaned_df, ds.stored_path)
    ds.row_count = len(cleaned_df)

    log = json.loads(ds.cleaning_log or '[]')
    from app.core.security import utcnow
    log.append({'at': utcnow().isoformat(), 'actions': actions, 'before': before, 'after': after})
    ds.cleaning_log = json.dumps(log)
    db.commit()

    return {
        'message': 'Cleaning complete. Original file is preserved.',
        'actions': actions,
        'before': before,
        'after': after,
        'profile': profile_dataset(cleaned_df),
    }


@router.get("/{dataset_id}/cleaning-log")
def cleaning_log(dataset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = get_owned_dataset(dataset_id, user, db)
    return {'dataset_id': ds.id, 'operations': json.loads(ds.cleaning_log or '[]')}


# ── EDA ───────────────────────────────────────────────────────────────────────

@router.get("/{dataset_id}/eda")
def eda_endpoint(dataset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = get_owned_dataset(dataset_id, user, db)
    df = load_dataframe(ds)
    return {'dataset_id': ds.id, 'filename': ds.filename, 'eda': run_eda(df)}


# ── Charts ────────────────────────────────────────────────────────────────────

@router.get("/{dataset_id}/charts")
def charts_endpoint(dataset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = get_owned_dataset(dataset_id, user, db)
    df = load_dataframe(ds)
    return {'charts': generate_charts(df)}


# ── AI Chat ───────────────────────────────────────────────────────────────────

@router.post("/{dataset_id}/chat")
async def chat_endpoint(dataset_id: str, data: ChatIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = get_owned_dataset(dataset_id, user, db)
    df = load_dataframe(ds)
    context = build_ai_context(df, ds.filename)
    answer = await ai_explain(data.provider, data.question, context)
    return {
        'answer': answer,
        'provider': data.provider,
        'context_summary': {
            'rows': context['rows'],
            'columns': context['columns'],
            'filename': context['filename'],
        },
        'note': 'Numeric context is computed by Python. AI text should be reviewed for accuracy.',
    }


# ── Downloads ─────────────────────────────────────────────────────────────────

@router.get("/{dataset_id}/download")
def download_dataset(dataset_id: str, original: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = get_owned_dataset(dataset_id, user, db)
    file_path = Path(ds.original_path if original else ds.stored_path).resolve()
    if STORAGE_DIR not in file_path.parents or not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on server.")
    suffix = file_path.suffix.lower()
    media_type = 'text/csv' if suffix == '.csv' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    prefix = 'original_' if original else 'cleaned_'
    with open(file_path, 'rb') as f:
        content = f.read()
    return FastAPIResponse(
        content=content, media_type=media_type,
        headers={'Content-Disposition': f'attachment; filename="{prefix}{ds.filename}"'},
    )


# ── PDF Report ────────────────────────────────────────────────────────────────

@router.get("/{dataset_id}/report.pdf")
def pdf_report(dataset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = get_owned_dataset(dataset_id, user, db)
    df = load_dataframe(ds)
    prof = profile_dataset(df)
    pdf_bytes = generate_pdf_report(df, ds.filename, prof)
    stem = Path(ds.filename).stem
    return FastAPIResponse(
        content=pdf_bytes, media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{stem}_datapilot_report.pdf"'},
    )


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ds = get_owned_dataset(dataset_id, user, db)
    for p in [ds.stored_path, ds.original_path]:
        Path(p).unlink(missing_ok=True)
    db.delete(ds)
    db.commit()
    return {'message': 'Dataset deleted successfully.'}

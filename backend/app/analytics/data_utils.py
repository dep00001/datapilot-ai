from __future__ import annotations
import json
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import HTTPException

from app.core.config import STORAGE_DIR
from app.core.security import safe_filename
from app.models.dataset import Dataset


def load_dataframe(ds: Dataset) -> pd.DataFrame:
    path = Path(ds.stored_path).resolve()
    if STORAGE_DIR not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="Dataset file not found on server.")
    try:
        if path.suffix.lower() in ('.xlsx', '.xls'):
            return pd.read_excel(path)
        return pd.read_csv(path, low_memory=False)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not parse dataset: {e}") from e


def save_dataframe(df: pd.DataFrame, path_str: str) -> None:
    path = Path(path_str).resolve()
    if STORAGE_DIR not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid save path.")
    suffix = path.suffix.lower()
    if suffix in ('.xlsx', '.xls'):
        df.to_excel(path, index=False)
    else:
        df.to_csv(path, index=False)


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, 'isoformat') and not isinstance(value, str):
        return value.isoformat()
    if hasattr(value, 'item'):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def frame_records(df: pd.DataFrame, limit: int = 100) -> list[dict]:
    return _json_safe(df.head(limit).to_dict(orient='records'))  # type: ignore


def profile_dataset(df: pd.DataFrame) -> dict[str, Any]:
    column_profiles = []
    for col in df.columns:
        series = df[col]
        numeric = bool(pd.api.types.is_numeric_dtype(series))
        missing = int(series.isna().sum())
        unique = int(series.nunique(dropna=True))
        sample = []
        for v in series.dropna().head(3).tolist():
            try:
                if pd.isna(v):
                    continue
            except (TypeError, ValueError):
                pass
            if hasattr(v, 'item'):
                sample.append(v.item())
            elif hasattr(v, 'isoformat'):
                sample.append(v.isoformat())
            else:
                sample.append(v)

        column_profiles.append({
            'name': str(col),
            'dtype': str(series.dtype),
            'missing': missing,
            'missing_pct': round(float(missing / len(series) * 100), 2) if len(series) else 0.0,
            'unique': unique,
            'numeric': numeric,
            'sample': sample,
        })

    numeric_df = df.select_dtypes(include=np.number)
    numeric_summary: dict = {}
    if not numeric_df.empty:
        desc = numeric_df.describe().astype(object)
        desc = desc.where(pd.notna(desc), None)
        numeric_summary = _json_safe(desc.to_dict())  # type: ignore

    correlation: dict = {}
    try:
        if numeric_df.shape[1] > 1:
            corr = numeric_df.corr(numeric_only=True).round(4).astype(object)
            corr = corr.where(pd.notna(corr), None)
            correlation = _json_safe(corr.to_dict())  # type: ignore
    except Exception:
        correlation = {}

    total_missing = int(df.isna().sum().sum())
    warnings = []
    if total_missing > 0:
        warnings.append(f"Dataset contains {total_missing} missing cells across {sum(1 for c in column_profiles if c['missing'] > 0)} columns.")
    if int(df.duplicated().sum()) > 0:
        warnings.append(f"Dataset contains {int(df.duplicated().sum())} duplicate rows.")

    return {
        'rows': int(len(df)),
        'columns': int(len(df.columns)),
        'duplicate_rows': int(df.duplicated().sum()),
        'total_missing': total_missing,
        'column_profile': column_profiles,
        'numeric_summary': numeric_summary,
        'correlation': correlation,
        'memory_bytes': int(df.memory_usage(deep=True).sum()),
        'warnings': warnings,
    }

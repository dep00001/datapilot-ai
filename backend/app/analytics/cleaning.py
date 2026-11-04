from __future__ import annotations
import json
from typing import Any

import numpy as np
import pandas as pd

from app.analytics.data_utils import _json_safe


def run_cleaning(df: pd.DataFrame, options: dict) -> tuple[pd.DataFrame, list[str], dict, dict]:
    before = {
        'rows': int(len(df)),
        'duplicates': int(df.duplicated().sum()),
        'missing': int(df.isna().sum().sum()),
    }
    actions: list[str] = []

    # 1. Trim whitespace in string columns
    if options.get('trim_whitespace', True):
        for col in df.select_dtypes(include=['object', 'string']).columns:
            df[col] = df[col].map(lambda x: x.strip() if isinstance(x, str) else x)
        actions.append('Trimmed leading/trailing whitespace in all text columns.')

    # 2. Drop exact duplicate rows
    if options.get('drop_duplicates', False):
        before_n = len(df)
        df = df.drop_duplicates()
        removed = before_n - len(df)
        if removed > 0:
            actions.append(f'Removed {removed} exact duplicate rows.')

    # 3. Fill missing numeric values
    fill_numeric = options.get('fill_numeric', 'none')
    if fill_numeric in ('median', 'mean', 'zero'):
        for col in df.select_dtypes(include=np.number).columns:
            if df[col].isna().any():
                fill_val = {
                    'median': df[col].median(),
                    'mean': df[col].mean(),
                    'zero': 0.0,
                }[fill_numeric]
                df[col] = df[col].fillna(fill_val)
        actions.append(f'Filled missing numeric values using {fill_numeric} strategy.')

    # 4. Fill missing categorical values
    fill_cat = options.get('fill_categorical', 'none')
    if fill_cat in ('mode', 'unknown'):
        for col in df.select_dtypes(include=['object', 'string', 'category']).columns:
            if df[col].isna().any():
                if fill_cat == 'mode':
                    mode = df[col].mode(dropna=True)
                    fill_val = mode.iloc[0] if not mode.empty else 'Unknown'
                else:
                    fill_val = 'Unknown'
                df[col] = df[col].fillna(fill_val)
        actions.append(f'Filled missing categorical values using {fill_cat} strategy.')

    after = {
        'rows': int(len(df)),
        'duplicates': int(df.duplicated().sum()),
        'missing': int(df.isna().sum().sum()),
    }

    if not actions:
        actions.append('No cleaning operations were applied.')

    return df, actions, before, after


def build_cleaning_preview(df: pd.DataFrame, options: dict) -> dict[str, Any]:
    """Run cleaning on a copy and return a diff preview without applying to the original."""
    df_copy = df.copy()
    _, actions, before, after = run_cleaning(df_copy, options)
    return {
        'actions': actions,
        'before': before,
        'after': after,
        'diff': {
            'rows_removed': before['rows'] - after['rows'],
            'duplicates_removed': before['duplicates'] - after['duplicates'],
            'missing_filled': before['missing'] - after['missing'],
        }
    }

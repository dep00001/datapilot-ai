from __future__ import annotations
from typing import Any

import numpy as np
import pandas as pd

from app.analytics.data_utils import _json_safe


def run_eda(df: pd.DataFrame) -> dict[str, Any]:
    numeric_df = df.select_dtypes(include=np.number)
    cat_cols = df.select_dtypes(include=['object', 'string', 'category']).columns.tolist()

    # Descriptive statistics per numeric column
    numeric_details: list[dict] = []
    for col in numeric_df.columns:
        s = numeric_df[col].dropna()
        if len(s) == 0:
            continue
        numeric_details.append({
            'column': str(col),
            'count': int(s.count()),
            'mean': round(float(s.mean()), 4),
            'median': round(float(s.median()), 4),
            'std': round(float(s.std()), 4),
            'min': round(float(s.min()), 4),
            'max': round(float(s.max()), 4),
            'q25': round(float(s.quantile(0.25)), 4),
            'q75': round(float(s.quantile(0.75)), 4),
            'skewness': round(float(s.skew()), 4) if len(s) > 2 else None,
            'kurtosis': round(float(s.kurt()), 4) if len(s) > 3 else None,
            'zero_count': int((s == 0).sum()),
            'negative_count': int((s < 0).sum()),
        })

    # Categorical summaries
    categorical_summaries: list[dict] = []
    for col in cat_cols[:12]:
        counts = df[col].fillna('(Missing)').astype(str).value_counts().head(15)
        categorical_summaries.append({
            'column': str(col),
            'unique_count': int(df[col].nunique(dropna=True)),
            'missing_count': int(df[col].isna().sum()),
            'top_values': [{'value': str(k), 'count': int(v)} for k, v in counts.items()],
        })

    # Correlation matrix
    correlation: dict = {}
    try:
        if numeric_df.shape[1] > 1:
            corr = numeric_df.corr(numeric_only=True).round(4).astype(object)
            corr = corr.where(pd.notna(corr), None)
            correlation = _json_safe(corr.to_dict())  # type: ignore
    except Exception:
        correlation = {}

    # Missing values report
    missing_report: list[dict] = []
    for col in df.columns:
        miss = int(df[col].isna().sum())
        if miss > 0:
            missing_report.append({
                'column': str(col),
                'missing_count': miss,
                'missing_pct': round(miss / len(df) * 100, 2),
            })

    warnings: list[str] = []
    if df.isna().sum().sum() > 0:
        warnings.append("Dataset contains missing values. Consider filling or removing them before analysis.")
    if df.duplicated().sum() > 0:
        warnings.append("Duplicate rows detected. This may skew distributions and aggregations.")
    for col in numeric_df.columns:
        s = numeric_df[col].dropna()
        if len(s) > 4:
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            outliers = ((s < q1 - 1.5 * iqr) | (s > q3 + 1.5 * iqr)).sum()
            if outliers > 0:
                warnings.append(f"Column '{col}' has {int(outliers)} potential outlier(s) by IQR method.")

    return {
        'numeric_details': numeric_details,
        'categorical_summaries': categorical_summaries,
        'correlation': correlation,
        'missing_report': missing_report,
        'warnings': warnings,
        'summary': {
            'total_rows': int(len(df)),
            'total_columns': int(len(df.columns)),
            'numeric_columns': int(len(numeric_df.columns)),
            'categorical_columns': int(len(cat_cols)),
            'total_missing': int(df.isna().sum().sum()),
            'duplicate_rows': int(df.duplicated().sum()),
        }
    }

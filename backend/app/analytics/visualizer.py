from __future__ import annotations
from typing import Any

import numpy as np
import pandas as pd


def generate_charts(df: pd.DataFrame) -> list[dict[str, Any]]:
    charts: list[dict] = []
    nums = df.select_dtypes(include=np.number).columns.tolist()
    cats = df.select_dtypes(include=['object', 'string', 'category']).columns.tolist()

    # Histogram of first numeric column
    if nums:
        col = nums[0]
        vals = df[col].dropna().head(500).tolist()
        charts.append({
            'id': f'hist_{col}',
            'kind': 'histogram',
            'title': f'Distribution of {col}',
            'column': str(col),
            'x': [float(v) for v in vals],
            'x_label': str(col),
            'description': f'Frequency distribution showing how {col} values are spread.',
        })

    # Bar chart: average numeric by first categorical
    if cats and nums:
        cat_col, num_col = cats[0], nums[0]
        temp = (
            df[[cat_col, num_col]]
            .dropna()
            .groupby(cat_col, dropna=False)[num_col]
            .mean()
            .sort_values(ascending=False)
            .head(15)
        )
        charts.append({
            'id': f'bar_{num_col}_by_{cat_col}',
            'kind': 'bar',
            'title': f'Average {num_col} by {cat_col}',
            'x': [str(v) for v in temp.index.tolist()],
            'y': [round(float(v), 2) for v in temp.values.tolist()],
            'x_label': str(cat_col),
            'y_label': f'Avg {num_col}',
            'description': f'Average {num_col} grouped by {cat_col} (top 15 categories).',
        })
    elif cats:
        col = cats[0]
        counts = df[col].fillna('(Missing)').astype(str).value_counts().head(15)
        charts.append({
            'id': f'bar_count_{col}',
            'kind': 'bar',
            'title': f'Count by {col}',
            'x': [str(v) for v in counts.index.tolist()],
            'y': [int(v) for v in counts.values.tolist()],
            'x_label': str(col),
            'y_label': 'Count',
            'description': f'Number of records per category in column {col}.',
        })

    # Scatter: first two numeric columns
    if len(nums) >= 2:
        a, b = nums[0], nums[1]
        temp = df[[a, b]].dropna().head(800)
        charts.append({
            'id': f'scatter_{a}_vs_{b}',
            'kind': 'scatter',
            'title': f'{a} vs {b}',
            'x': [float(v) for v in temp[a].tolist()],
            'y': [float(v) for v in temp[b].tolist()],
            'x_label': str(a),
            'y_label': str(b),
            'description': f'Scatter plot showing relationship between {a} and {b}.',
        })

    # Second bar: count by second categorical column
    if len(cats) >= 2:
        col = cats[1]
        counts = df[col].fillna('(Missing)').astype(str).value_counts().head(12)
        charts.append({
            'id': f'bar_count_{col}',
            'kind': 'bar',
            'title': f'Count by {col}',
            'x': [str(v) for v in counts.index.tolist()],
            'y': [int(v) for v in counts.values.tolist()],
            'x_label': str(col),
            'y_label': 'Count',
            'description': f'Distribution of {col} values.',
        })

    # Additional histogram for second numeric column
    if len(nums) >= 3:
        col = nums[2]
        vals = df[col].dropna().head(500).tolist()
        charts.append({
            'id': f'hist_{col}',
            'kind': 'histogram',
            'title': f'Distribution of {col}',
            'column': str(col),
            'x': [float(v) for v in vals],
            'x_label': str(col),
            'description': f'Distribution of {col}.',
        })

    return charts

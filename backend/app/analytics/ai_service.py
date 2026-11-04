from __future__ import annotations
import json
from typing import Any

import numpy as np
import pandas as pd
from fastapi import HTTPException

from app.core.config import settings
from app.analytics.data_utils import _json_safe


def build_ai_context(df: pd.DataFrame, filename: str) -> dict[str, Any]:
    """Build a safe, minimized context summary for the AI provider. Never sends full raw rows."""
    nums = df.select_dtypes(include=np.number).columns.tolist()
    cats = df.select_dtypes(include=['object', 'string', 'category']).columns.tolist()

    cat_summary = []
    for col in cats[:8]:
        top = df[col].fillna('(Missing)').astype(str).value_counts().head(8)
        cat_summary.append({'column': col, 'top_values': top.to_dict()})

    num_summary = {}
    if nums:
        try:
            num_summary = _json_safe(
                df[nums].describe().astype(object).where(pd.notna(df[nums].describe()), None).to_dict()
            )
        except Exception:
            pass

    corr_summary: dict = {}
    try:
        if len(nums) > 1:
            corr = df[nums].corr().round(3).astype(object).where(pd.notna(df[nums].corr()), None)
            corr_summary = _json_safe(corr.to_dict())
    except Exception:
        pass

    return {
        'filename': filename,
        'rows': int(len(df)),
        'columns': int(len(df.columns)),
        'column_names': [str(c) for c in df.columns.tolist()],
        'numeric_summary': num_summary,
        'categorical_summary': cat_summary,
        'correlation': corr_summary,
        'missing_per_column': {str(c): int(df[c].isna().sum()) for c in df.columns if df[c].isna().sum() > 0},
        'duplicate_rows': int(df.duplicated().sum()),
    }


async def ai_explain(provider: str, question: str, context: dict) -> str:
    system_prompt = (
        "You are a careful, accurate data analyst. "
        "Explain only what is supported by the provided VERIFIED DATA CONTEXT — computed by Python. "
        "Do not invent numbers, make up trends, or guess values not in the context. "
        "Distinguish between correlation and causation. "
        "If context is insufficient to answer the question, clearly say so. "
        "Keep the answer helpful, well-structured, and honest about limitations."
    )
    context_str = json.dumps(context, default=str)[:18000]
    user_content = f"QUESTION: {question}\n\nVERIFIED DATA CONTEXT:\n{context_str}"

    if provider == 'openai':
        if not settings.openai_api_key:
            return (
                "AI provider (OpenAI) is not configured. Add OPENAI_API_KEY to the backend .env file. "
                "Your dataset has been profiled and charts are available. AI explanation requires an API key."
            )
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
            result = client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=1200,
                temperature=0.2,
            )
            return result.choices[0].message.content or "OpenAI returned an empty response."
        except Exception as e:
            return f"OpenAI request failed: {str(e)}. Your dataset profile and charts are still available."

    elif provider == 'gemini':
        if not settings.gemini_api_key:
            return (
                "AI provider (Gemini) is not configured. Add GEMINI_API_KEY to the backend .env file. "
                "Your dataset has been profiled and charts are available. AI explanation requires an API key."
            )
        try:
            from google import genai
            client = genai.Client(api_key=settings.gemini_api_key)
            full_prompt = f"{system_prompt}\n\n{user_content}"
            result = client.models.generate_content(
                model=settings.gemini_model,
                contents=full_prompt,
            )
            return result.text or "Gemini returned no text response."
        except Exception as e:
            return f"Gemini request failed: {str(e)}. Your dataset profile and charts are still available."

    raise HTTPException(status_code=422, detail="Invalid AI provider. Choose 'openai' or 'gemini'.")

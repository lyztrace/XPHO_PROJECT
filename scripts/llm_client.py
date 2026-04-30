"""
llm_client.py
LLM 调用客户端，支持 OpenAI 兼容 API。
通过环境变量配置：
  - LLM_API_KEY: API 密钥（必需）
  - LLM_BASE_URL: API 端点（默认 https://api.openai.com/v1）
  - LLM_MODEL: 模型名（默认 gpt-4o）
  - LLM_MAX_TOKENS: 最大输出 token（默认 4096）
  - LLM_TEMPERATURE: 温度（默认 0.3）
"""
from __future__ import annotations
import json
import os
import time
from typing import Any

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o"
_DEFAULT_MAX_TOKENS = 4096
_DEFAULT_TEMPERATURE = 0.3
_MAX_RETRIES = 3
_RETRY_DELAY = 2.0


def _get_client():
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "openai package is required for LLM calls. Install with: pip install openai"
        )

    api_key = os.environ.get("LLM_API_KEY", "")
    if not api_key:
        raise RuntimeError("LLM_API_KEY environment variable is not set")

    base_url = os.environ.get("LLM_BASE_URL", _DEFAULT_BASE_URL)
    return OpenAI(api_key=api_key, base_url=base_url)


def _get_config() -> dict:
    return {
        "model": os.environ.get("LLM_MODEL", _DEFAULT_MODEL),
        "max_tokens": int(os.environ.get("LLM_MAX_TOKENS", str(_DEFAULT_MAX_TOKENS))),
        "temperature": float(os.environ.get("LLM_TEMPERATURE", str(_DEFAULT_TEMPERATURE))),
    }


def chat(system_prompt: str, user_prompt: str, response_format: dict | None = None) -> str:
    """调用 LLM 并返回响应文本。支持 JSON mode。"""
    client = _get_client()
    cfg = _get_config()

    kwargs: dict[str, Any] = {
        "model": cfg["model"],
        "temperature": cfg["temperature"],
        "max_tokens": cfg["max_tokens"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    if response_format is not None:
        kwargs["response_format"] = response_format

    last_error = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content or ""
            return content
        except Exception as e:
            last_error = e
            if attempt < _MAX_RETRIES:
                wait = _RETRY_DELAY * attempt
                print(f"[llm] attempt {attempt} failed: {e}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"[llm] all {_MAX_RETRIES} attempts failed: {e}")

    raise RuntimeError(f"LLM call failed after {_MAX_RETRIES} retries: {last_error}")


def chat_json(system_prompt: str, user_prompt: str) -> Any:
    """调用 LLM 并返回解析后的 JSON 对象。"""
    client = _get_client()
    cfg = _get_config()

    kwargs: dict[str, Any] = {
        "model": cfg["model"],
        "temperature": cfg["temperature"],
        "max_tokens": cfg["max_tokens"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    last_error = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content or "{}"
            return json.loads(content)
        except json.JSONDecodeError as e:
            last_error = e
            if attempt < _MAX_RETRIES:
                wait = _RETRY_DELAY * attempt
                print(f"[llm] JSON parse failed attempt {attempt}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"[llm] JSON parse failed all attempts: {e}")
        except Exception as e:
            last_error = e
            if attempt < _MAX_RETRIES:
                wait = _RETRY_DELAY * attempt
                print(f"[llm] attempt {attempt} failed: {e}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"[llm] all {_MAX_RETRIES} attempts failed: {e}")

    raise RuntimeError(f"LLM JSON call failed after {_MAX_RETRIES} retries: {last_error}")


ANNOTATION_SYSTEM_PROMPT = """You are an expert physics competition problem annotator. Your task is to analyze physics competition problems and provide structured annotations in English.

For each sub-question, you must provide:
1. related_knowledge_points: An array of 3-level knowledge point classifications. Each entry is [Level1, Level2, Level3]. Use standard physics knowledge taxonomy (e.g., ["Mechanics", "Kinematics", "Uniformly Accelerated Motion"]).
2. physical_model: The physical model(s) used in this problem (e.g., "Two-body gravitational system in rotating reference frame").
3. physical_scenario: The physical scenario described (e.g., "Electrodynamic tether orbiting Earth in the equatorial plane").
4. explicit_conditions: Explicit conditions directly given in the problem text.
5. implicit_conditions: Implicit conditions that must be inferred, each as {"condition_text": "original text from problem", "hidden_meaning": "what this implies"}.
6. grading_rubric: Array of grading criteria strings extracted from the marking scheme.
7. core_idea: The core solution approach in 1-2 sentences.
8. difficulty: One of "easy", "medium", or "hard".
9. answer_type: One of "expression", "numerical", "choice", "equation", "open-ended", or "inequality".

Rules:
- ALL output must be in English.
- Be precise and concise.
- For knowledge points, follow the IPhO syllabus taxonomy.
- For grading rubric, extract the actual point allocations and criteria.
- If unsure about a field, make your best educated guess as a physics expert."""


def annotate_subquestion(
    sub_id: str,
    question_text: str,
    solution_text: str,
    grading_rubric_text: str,
    background_text: str,
) -> dict:
    """Call LLM to annotate a single subquestion. Returns a dict with annotation fields."""
    user_prompt = f"""Analyze the following physics competition sub-question and provide annotations.

=== SUB-QUESTION ID ===
{sub_id}

=== BACKGROUND / CONTEXT ===
{background_text[:3000]}

=== QUESTION TEXT ===
{question_text[:3000]}

=== STANDARD SOLUTION ===
{solution_text[:4000]}

=== GRADING RUBRIC (if available) ===
{grading_rubric_text[:4000]}

Provide a JSON object with these fields:
{{
  "related_knowledge_points": [["Level1", "Level2", "Level3"], ...],
  "physical_model": "string describing the physical model(s) used",
  "physical_scenario": "string describing the physical scenario",
  "explicit_conditions": ["condition 1", "condition 2", ...],
  "implicit_conditions": [
    {{"condition_text": "original text from problem", "hidden_meaning": "the implied condition"}},
    ...
  ],
  "grading_rubric": ["Award X pt if ...", ...],
  "core_idea": "core solution approach in 1-2 sentences",
  "difficulty": "easy" | "medium" | "hard",
  "answer_type": "expression" | "numerical" | "choice" | "equation" | "open-ended" | "inequality"
}}"""

    try:
        result = chat_json(ANNOTATION_SYSTEM_PROMPT, user_prompt)
        return result
    except Exception as e:
        print(f"[llm] annotation failed for {sub_id}: {e}")
        return {}

"""
fill_annotation_new.py
读取 work/Q{n}.subquestions.json 并填充成最终模板格式的 JSON 骨架。
支持通过 LLM 自动填充标注字段；LLM 调用由环境变量 LLM_API_KEY 控制，
若未设置则仅生成骨架（需人工填充）。

新格式：数组形式，每个元素代表一个子问题，完全对齐最终模板.json。
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _normalize_latex(text: str) -> str:
    """确保文本中所有数学公式都用 LaTeX $...$ 包裹。
    修复常见问题：双句号、裸变量表达式等。"""
    if not text:
        return text
    # 修复双句号 ".. Otherwise" -> ". Otherwise"
    text = re.sub(r'\.\.\s+Otherwise', '. Otherwise', text)
    # 修复 $.. Otherwise -> $. Otherwise
    text = re.sub(r'\$\.\.\s+Otherwise', r'\$. Otherwise', text)
    return text


def clean_final_answer(raw: str) -> str:
    """清理最终答案，去掉多余的描述文本"""
    if not raw:
        return ""

    cleaned = re.sub(r'^[Tt]he (total |final )?(answer|result|force|expression) is\s+', '', raw)
    cleaned = re.sub(r'^[Aa]nswer:\s*', '', cleaned)
    cleaned = re.sub(r'\.\s*[A-Z][a-z]+.*$', '.', cleaned)
    cleaned = re.sub(r'\*\*', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    if '$$' in cleaned:
        matches = re.findall(r'\$\$(.*?)\$\$', cleaned, re.DOTALL)
        if matches:
            cleaned = f"$${matches[-1].strip()}$$"
    elif '$' in cleaned:
        matches = re.findall(r'\$(.*?)\$', cleaned)
        if matches:
            cleaned = f"${matches[-1].strip()}$"

    return cleaned


def infer_answer_type(answer: str, question: str) -> str:
    """推断答案类型"""
    if not answer:
        return ""

    answer_lower = answer.lower()
    question_lower = question.lower()

    if '=' in answer and not answer.startswith('$'):
        return "equation"

    if not any(c in answer for c in ['$', '=', '\\', '^', '_', '{', '}']):
        if any(word in question_lower for word in ['which', 'determine', 'identify', 'choose']):
            return "open-ended"

    if any(op in answer for op in ['<', '>', '≤', '≥', 'leq', 'geq', 'lt', 'gt']):
        return "inequality"

    return "expression"


def infer_answer_unit(answer: str, question: str, answer_type: str) -> str:
    """推断答案单位"""
    if not answer or answer_type == "open-ended":
        return ""

    if answer_type == "expression":
        return ""

    question_lower = question.lower()
    answer_lower = answer.lower()

    if re.search(r'\bd[a-z]+\s*/\s*dt\b', answer_lower) or re.search(r'\bd[a-z]+\s*/\s*dt\b', question_lower):
        return "m/s"

    unit_keywords = {
        'tension': 'N', 'force': 'N', 'lorentz force': 'N',
        'emf': 'V', 'electromotive force': 'V', 'voltage': 'V', 'potential': 'V',
        'power': 'W', 'energy': 'J', 'work': 'J',
        'radius': 'm', 'distance': 'm', 'length': 'm', 'orbit': 'm',
        'velocity': 'm/s', 'speed': 'm/s', 'acceleration': 'm/s²',
        'temperature': 'K', 'current': 'A', 'total charge': 'C',
        'charge transferred': 'C', 'charge': 'C',
        'magnetic field': 'T', 'resistance': 'Ω', 'capacitance': 'F',
        'inductance': 'H', 'frequency': 'Hz', 'time': 's',
        'mass': 'kg', 'momentum': 'kg·m/s', 'angular momentum': 'kg·m²/s',
        'decay rate': 'm/s', 'rate of change': 'm/s',
    }

    sorted_keywords = sorted(unit_keywords.items(), key=lambda x: len(x[0]), reverse=True)
    for keyword, unit in sorted_keywords:
        if keyword in question_lower:
            return unit

    if not any(c in answer for c in ['$', '=', '\\', '^', '_', '{', '}']):
        return ""

    return ""


def infer_modality(question_text: str, has_image: bool, image_paths: list[str] | None = None) -> str:
    """推断模态类型。
    
    四种模态类型：
    - text-only：问题完全使用文字描述，没有图表辅助
    - text+illustration figure：图表描述场景，文字提供描述
    - text+variable figure：图表明确关键变量或空间范围
    - text+data figure：图表呈现文本中未给出的数据、图表或函数
    
    如果问题含多个物理量求解，则返回列表包含多个类型。
    默认基于 has_image 做基础判断，LLM 可用时调用 LLM 精确分类。
    """
    if not has_image:
        return "text-only"
    
    # 尝试用 LLM 精确判断模态类型
    if os.environ.get("LLM_API_KEY") and question_text:
        try:
            from llm_client import infer_modality_with_llm
            result = infer_modality_with_llm(question_text, image_paths or [])
            if result and result in (
                "text-only", "text+illustration figure", "text+variable figure", "text+data figure"
            ):
                return result
        except Exception:
            pass
    
    # 启发式回退：有图默认 illustration figure
    return "text+illustration figure"


def extract_explicit_conditions(question: str) -> list[str]:
    """从问题文本提取显性条件"""
    conditions = []
    if not question:
        return conditions

    number_patterns = re.findall(r'\b\d+\.?\d*\s*(?:m|kg|s|N|V|A|T|Ω|Hz|K|J|W|C|F|H)\b', question)
    conditions.extend(number_patterns)

    assume_patterns = re.findall(r'[Aa]ssume\s+([^,.]+)', question)
    conditions.extend(assume_patterns)

    given_patterns = re.findall(r'[Gg]iven\s+([^,.]+)', question)
    conditions.extend(given_patterns)

    return conditions


def try_llm_fill(
    sub_id: str,
    question_text: str,
    solution_text: str,
    grading_text: str,
    background_text: str,
) -> dict:
    """尝试通过 LLM 填充标注字段。若 LLM 不可用或失败则返回空 dict。"""
    if not os.environ.get("LLM_API_KEY"):
        return {}

    try:
        from llm_client import annotate_subquestion

        print(f"[fill] calling LLM for {sub_id} ...")
        result = annotate_subquestion(
            sub_id=sub_id,
            question_text=question_text,
            solution_text=solution_text,
            grading_rubric_text=grading_text,
            background_text=background_text,
        )
        print(f"[fill] LLM returned for {sub_id}: difficulty={result.get('difficulty', '?')}")
        return result
    except ImportError as e:
        print(f"[fill] LLM not available (import error): {e}")
        return {}
    except Exception as e:
        print(f"[fill] LLM call failed for {sub_id}: {e}")
        return {}


def build_annotation_new(sub_pack: dict, meta: dict) -> tuple[list[dict], list[str]]:
    """生成新格式的标注 JSON（完全对齐最终模板.json）"""
    annotations = []
    todos: list[str] = []
    seen_parts: set[str] = set()

    grading_text = sub_pack.get("grading_rubric_text", "")

    for s in sub_pack["subquestions"]:
        sub_id = s["id"]
        parts = sub_id.split(".")
        part_letter = parts[0] if len(parts) > 0 else ""

        question_text = s.get("original_question", "")
        solution_text = s.get("solution_process", "")
        raw_background_info = s.get("background_info", "")
        # 背景信息去重：同一 Part 只保留第一个子题目的背景信息
        if part_letter and part_letter in seen_parts:
            background_info = ""
        else:
            background_info = raw_background_info
            if part_letter:
                seen_parts.add(part_letter)
        context = s.get("context", "")
        rubric = s.get("rubric_items", [])

        final_raw = s.get("final_answer_raw", "").strip()
        final_cleaned = clean_final_answer(final_raw)
        final_arr = [final_cleaned] if final_cleaned else [""]

        answer_type = infer_answer_type(final_cleaned, question_text)
        answer_unit = infer_answer_unit(final_cleaned, question_text, answer_type)
        # 初始模态类型（无图片时 text-only，后续 sync_image_refs 会更新）
        modality = infer_modality(question_text, has_image=False)
        explicit_conditions = extract_explicit_conditions(question_text)

        llm_result = try_llm_fill(
            sub_id=sub_id,
            question_text=question_text,
            solution_text=solution_text,
            grading_text=grading_text,
            background_text=background_info,
        )

        llm_kp = llm_result.get("related_knowledge_points", [])
        llm_model = llm_result.get("physical_model", "")
        llm_scenario = llm_result.get("physical_scenario", "")
        llm_explicit = llm_result.get("explicit_conditions", [])
        llm_implicit = llm_result.get("implicit_conditions", [])
        llm_rubric = llm_result.get("grading_rubric", [])
        llm_core = llm_result.get("core_idea", "")
        llm_difficulty = llm_result.get("difficulty", "")
        llm_answer_type = llm_result.get("answer_type", "")

        if llm_kp:
            related_kp = [[str(k[0]), str(k[1]), str(k[2])] for k in llm_kp if len(k) >= 3]
        else:
            related_kp = []

        if llm_explicit:
            explicit_conditions = [str(c) for c in llm_explicit]

        implicit_conditions = []
        for ic in llm_implicit:
            if isinstance(ic, dict):
                implicit_conditions.append({
                    "条件原文": str(ic.get("condition_text", ic.get("条件原文", ""))),
                    "隐藏条件": str(ic.get("hidden_meaning", ic.get("隐藏条件", ""))),
                })

        difficulty = llm_difficulty if llm_difficulty in ("easy", "medium", "hard") else ""
        final_answer_type_val = llm_answer_type if llm_answer_type in (
            "expression", "numerical", "choice", "equation", "open-ended", "inequality"
        ) else answer_type

        if llm_rubric:
            rubric = [_normalize_latex(str(r)) for r in llm_rubric]
        elif rubric:
            rubric = [_normalize_latex(r) for r in rubric]
        else:
            rubric = []
        core_idea = llm_core or ""
        physical_model = llm_model or ""
        physical_scenario = llm_scenario or ""

        # 只针对版块3，去掉A.1/B.1等的点
        block3 = sub_id.replace(".", "") if re.match(r"^[A-Z]\.\d+$", sub_id) else sub_id
        annotation = {
            "标注基础信息": {
                "来源": meta.get("source", ""),
                "补充": meta.get("supplement", ""),
                "年份": meta.get("year", ""),
                "版块1": meta.get("section_1", ""),
                "版块2": f"Part-{part_letter}" if part_letter else "",
                "版块3": block3,
            },
            "题目信息": {
                "背景信息": background_info,
                "上下文": context,
                "问题原文": question_text,
                "改造后问题": "",
                "核心思路": core_idea,
                "解答过程": solution_text,
                "最终答案": final_arr,
                "改造后答案": [""] * len(final_arr),
                "答案类型": [final_answer_type_val] if final_answer_type_val else [""],
                "改造后答案类型": [""] * len(final_arr),
                "答案单位": [answer_unit] if answer_unit else [""],
                "改造后答案单位": [""] * len(final_arr),
                "关联图片路径": [""] * len(final_arr),
                "模态类型": [modality] if modality else [""],
                "难度": difficulty,
            },
            "条件提取": {
                "显性条件": explicit_conditions if explicit_conditions else [],
                "隐性条件": implicit_conditions,
            },
            "物理模型": physical_model,
            "关联考点": related_kp,
            "物理场景": physical_scenario,
            "判分标准": rubric,
            "错误解题步骤": [],
            "多解法标注": [],
        }

        annotations.append(annotation)

        llm_tag = " [LLM]" if llm_result else ""
        todos.append(f"- [ ] Fill 改造后问题 for {sub_id}")
        todos.append(f"- [ ] Fill 改造后答案 for {sub_id}")
        todos.append(f"- [ ] Fill 改造后答案类型 for {sub_id}")
        todos.append(f"- [ ] Fill 改造后答案单位 for {sub_id}")
        if not llm_kp:
            todos.append(f"- [ ] Fill 关联考点 for {sub_id}")
        if not physical_model:
            todos.append(f"- [ ] Fill 物理模型 for {sub_id}")
        if not physical_scenario:
            todos.append(f"- [ ] Fill 物理场景 for {sub_id}")
        if not rubric:
            todos.append(f"- [ ] Fill 判分标准 for {sub_id}")
        if not explicit_conditions and not implicit_conditions:
            todos.append(f"- [ ] Fill 条件提取 for {sub_id}")
        if not difficulty:
            todos.append(f"- [ ] Fill 难度 for {sub_id}")
        todos.append(f"- [ ] Fill 多解法标注 for {sub_id} (if applicable)")
        todos.append(f"- [ ] Fill 错误解题步骤 for {sub_id} (if applicable)")

    todos.extend([
        "- [ ] Manual physics correctness review",
        "- [ ] Verify all values are in English",
        "- [ ] Verify 关联图片路径 and 模态类型 per image",
    ])

    return annotations, todos


def main():
    if len(sys.argv) != 5:
        print("usage: fill_annotation_new.py <subquestions.json> <out.json> <review_todo.md> <meta.json>")
        sys.exit(1)
    sub_pack = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    meta = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
    annotations, todos = build_annotation_new(sub_pack, meta)
    Path(sys.argv[2]).write_text(json.dumps(annotations, indent=2, ensure_ascii=False), encoding="utf-8")
    Path(sys.argv[3]).write_text("# Review TODO\n\n## Manual items (after pipeline)\n" + "\n".join(todos) + "\n", encoding="utf-8")
    print(f"[fill_annotation_new] wrote {sys.argv[2]} and {sys.argv[3]}")


if __name__ == "__main__":
    main()

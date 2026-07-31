"""
json_parser.py — LLM 输出 JSON 解析 + Pydantic 校验（Phase P0: schema 硬约束补强）

设计目标（与 plan 一致）：
  1. 完全兼容现有 llm.invoke(messages) 返回 content 字符串的链路
  2. 测试 mock 完全不动（仍返回 content 字符串）
  3. 解析失败时返回 (None, error_msg)，节点层决定是否 fallback

处理链路（按顺序尝试）：
  Layer 1: 直接 json.loads(content)
  Layer 2: 剥离 ```json / ```fence 包裹后 json.loads
  Layer 3: 寻找第一个 { 和最后一个 } 截取后 json.loads
  Layer 4: 寻找第一个 [ 和最后一个 ] 截取后 json.loads
  Layer 5: （可选）json_repair.loads(content) — 自动修复常见 JSON 错误
  Layer 6: （可选）json_repair.loads(原始 + fence 剥离 + 截取)
  Layer 7: 全部失败 → 返回 (None, error_msg)

校验（与现有 _extract_json_safe 等价 + 升级）：
  - 解析成功的 dict → schema.model_validate(dict) 校验
  - 校验失败 → 返回 (None, validation_error_msg)
  - 校验成功 → 返回 (schema_instance, None)

依赖：
  - json_repair（pyproject.toml 已声明）
  - pydantic v2（项目根依赖）
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel, ValidationError

from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


def parse_and_validate(
    content: str,
    schema: Type[BaseModel],
    *,
    use_repair: bool = True,
) -> Tuple[Optional[BaseModel], Optional[str]]:
    """从 LLM 原始 content 字符串解析 + Pydantic 校验。

    Args:
        content: LLM 原始输出字符串
        schema: Pydantic BaseModel 子类
        use_repair: 是否启用 json_repair 兜底（默认 True）

    Returns:
        (parsed_instance, error_msg) — 成功时 (instance, None)，失败时 (None, error_msg)
    """
    if not content:
        return None, "empty content"

    errors: List[str] = []

    # ---- Layer 1-4: 现有 _extract_json_safe 等价实现 ----
    candidates = _make_candidates(content)
    for idx, cand in enumerate(candidates):
        try:
            data = json.loads(cand)
            # 解析成功 → 立刻 Pydantic 校验
            return _validate(data, schema)
        except (json.JSONDecodeError, ValidationError, TypeError) as e:
            errors.append(f"Layer{idx+1} parse/validate failed: {type(e).__name__}: {e}")
            continue

    # ---- Layer 5-6: json_repair 兜底 ----
    if use_repair:
        repaired_errors: List[str] = []
        try:
            import json_repair  # 一次性导入（Python 缓存）
        except ImportError:
            logger.warning(
                "[parse_and_validate] json_repair 未安装,跳过 Layer5-6(可 pip install json-repair)"
            )
            errors.append("json_repair ImportError")
        else:
            # Layer 5: 优先修复原始 content
            try:
                repaired = json_repair.loads(content)
                if repaired:
                    result = _validate(repaired, schema)
                    if result[0] is not None:
                        logger.info(
                            "[parse_and_validate] json_repair 修复 Layer1-4 失败的 JSON 成功"
                        )
                        return result
                    else:
                        repaired_errors.append(f"Layer5 repair+validate: {result[1]}")
            except (ValidationError, TypeError, ValueError) as e:
                # 预期内的解析/校验错误
                repaired_errors.append(f"Layer5 repair: {type(e).__name__}: {e}")
            except Exception as e:
                # 兜底：json_repair 自身 bug
                logger.warning(f"[parse_and_validate] json_repair 异常（Layer5）: {e}")
                repaired_errors.append(f"Layer5 unexpected: {type(e).__name__}: {e}")

            # Layer 6: 修复每个 candidate
            for cand in candidates[1:]:  # 跳过原始 content（已尝试）
                try:
                    repaired = json_repair.loads(cand)
                    if repaired:
                        result = _validate(repaired, schema)
                        if result[0] is not None:
                            logger.info(
                                "[parse_and_validate] json_repair 修复 candidate 成功"
                            )
                            return result
                except (ValidationError, TypeError, ValueError) as e:
                    repaired_errors.append(f"Layer6 candidate repair: {type(e).__name__}: {e}")
                except Exception as e:
                    logger.warning(f"[parse_and_validate] json_repair 异常（Layer6）: {e}")
                    repaired_errors.append(f"Layer6 unexpected: {type(e).__name__}: {e}")

            errors.extend(repaired_errors)

    # ---- Layer 7: 全部失败 ----
    return None, "; ".join(errors[:5])  # 取前 5 个错误


def _make_candidates(content: str) -> List[str]:
    """生成 4 种解析候选（与现有 _extract_json_safe 等价）"""
    candidates: List[str] = [content]

    # Layer 2: 剥 markdown fence
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if m:
        candidates.append(m.group(1).strip())

    # Layer 3: 截 {...}
    brace_start = content.find("{")
    if brace_start >= 0:
        brace_end = content.rfind("}")
        if brace_end > brace_start:
            candidates.append(content[brace_start:brace_end + 1].strip())

    # Layer 4: 截 [...]
    bracket_start = content.find("[")
    if bracket_start >= 0:
        bracket_end = content.rfind("]")
        if bracket_end > bracket_start:
            candidates.append(content[bracket_start:bracket_end + 1].strip())

    return candidates


def _validate(
    data: Any, schema: Type[BaseModel]
) -> Tuple[Optional[BaseModel], Optional[str]]:
    """dict → Pydantic 校验（Pydantic v2 model_validate）"""
    try:
        instance = schema.model_validate(data)
        return instance, None
    except ValidationError as e:
        # 返回精简后的错误信息（Pydantic 默认输出很长）
        err_count = len(e.errors())
        first_err = e.errors()[0] if e.errors() else {}
        loc = ".".join(str(x) for x in first_err.get("loc", []))
        msg = first_err.get("msg", "unknown")
        return None, f"Pydantic ValidationError ({err_count} errors, first: {loc}: {msg})"
    except Exception as e:
        return None, f"Unexpected validate exception: {type(e).__name__}: {e}"


def legacy_parse_and_render(
    content: str,
    render_markdown: Callable[[Dict[str, Any]], str],
    *,
    error_prefix: str = "[legacy_parse]",
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], str]:
    """统一的 legacy JSON 解析入口（剥 fence + json.loads + 渲染 Markdown）。

    用于 P0 接入的 commodity analyst 节点：
      - Pydantic 校验成功 → 走 parse_and_validate 路径
      - Pydantic 校验失败 → 走 legacy_parse_and_render 降级路径
      - 关闭 FEATURE_COMMODITY_SCHEMA_VALIDATION → 走 legacy_parse_and_render

    Args:
        content: LLM 原始输出字符串
        render_markdown: dict → Markdown 字符串的回调（每个节点的 _structured_to_markdown）
        error_prefix: 解析失败时 logger.warning 的前缀（区分不同节点）

    Returns:
        (parsed_dict, structured_report, report_md)
        - parsed_dict: 解析成功时为 dict,失败时为 None
        - structured_report: 解析成功时为 dict,失败时为 {"raw": content, "parse_error": str}
        - report_md: 解析成功时为 render_markdown(dict),失败时为 content 原始 markdown
    """
    parsed_dict: Optional[Dict[str, Any]] = None
    try:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            start = 1 if lines[0].strip().startswith("```") else 0
            end = -1 if lines[-1].strip() == "```" else len(lines)
            cleaned = "\n".join(lines[start:end])
        parsed_dict = json.loads(cleaned)
        structured_report = parsed_dict
        report_md = render_markdown(parsed_dict)
    except Exception as parse_err:  # noqa: BLE001 - legacy 兜底,保留所有现有行为
        logger.warning(f"{error_prefix} JSON 解析失败,回退原始内容: {parse_err}")
        structured_report = {"raw": content, "parse_error": str(parse_err)}
        report_md = content
    return parsed_dict, structured_report, report_md


__all__ = ["legacy_parse_and_render", "parse_and_validate"]
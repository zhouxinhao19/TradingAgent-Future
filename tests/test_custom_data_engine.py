"""
测试 engine 模块: run_analysis() / AnalysisResult
"""

import json
import os
import tempfile

import pytest

from tradingagents.agents.custom_data.engine import AnalysisResult, run_analysis, _fallback_report


class TestFallbackReport:
    def test_fallback_report_contains_summary(self):
        """降级报告包含数据摘要"""
        summary = json.dumps([
            {"type": "tabular", "overview": {"rows": 100, "columns": 5, "missing_cells": 0, "missing_ratio": 0.0}}
        ])
        report = _fallback_report(summary)
        assert "降级版本" in report
        assert "100" in report

    def test_fallback_invalid_json(self):
        """无效 JSON 也能生成降级报告"""
        report = _fallback_report("not valid json")
        assert report  # 非空即可


class TestRunAnalysis:
    def test_no_llm_fallback(self):
        """无 LLM 时返回降级报告"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("a,b\n1,2\n3,4\n")
            f.flush()
            fpath = f.name
        try:
            result = run_analysis([fpath], llm=None)
            assert result.success is True
            assert result.fallback is True
            assert result.file_count == 1
            assert "tabular" in result.content_types
            assert result.report
        finally:
            os.unlink(fpath)

    def test_missing_files(self):
        """文件读取失败返回 success=False"""
        result = run_analysis(["/tmp/nonexistent_file_xyz.csv"], llm=None)
        assert result.success is False
        assert result.error is not None

    def test_multiple_files(self):
        """多个文件"""
        paths = []
        for i in range(2):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
                f.write(f"x,y\n{i},2\n")
                f.flush()
                paths.append(f.name)
        try:
            result = run_analysis(paths, llm=None)
            assert result.success is True
            assert result.file_count == 2
            assert result.fallback is True
        finally:
            for p in paths:
                os.unlink(p)

    def test_analysis_result_dataclass(self):
        """AnalysisResult 默认值"""
        r = AnalysisResult()
        assert r.success is True
        assert r.fallback is False
        assert r.error is None

    def test_with_mock_llm(self):
        """Mock LLM 返回结构化报告"""
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("a,b\n1,2\n")
            f.flush()
            fpath = f.name
        try:
            class MockLLM:
                def invoke(self, messages):
                    from types import SimpleNamespace
                    return SimpleNamespace(content="## 分析报告\n数据质量良好。")

            result = run_analysis([fpath], llm=MockLLM())
            assert result.success is True
            assert result.fallback is False
            assert "分析报告" in result.report
        finally:
            os.unlink(fpath)

    def test_with_user_context(self):
        """user_context 传入 LLM prompt"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("a,b\n1,2\n")
            f.flush()
            fpath = f.name
        try:
            result = run_analysis([fpath], llm=None, user_context="这是库存数据")
            assert result.success is True
        finally:
            os.unlink(fpath)

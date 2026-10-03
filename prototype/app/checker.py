"""规则引擎：对课程设计计算表做「计算自洽性」校核。

设计要点（写进方案书的技术实现章节）：
1. 确定性校核交给规则引擎，不交给大模型。
   大模型算数不可靠，而"负荷-流量-温差"这类关系式是硬性的，必须精确判定。
2. 规则全部外置在 YAML 里，教师可自行增删规则而不改代码。
3. 公式用受限 AST 求值，只允许四则运算与白名单函数，不执行任意代码。
4. 每条规则都带 common_mistake 与 suggestion，直接告诉学生"错在哪、为什么、怎么改"。
"""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

ALLOWED_FUNCS: dict[str, object] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sqrt": math.sqrt,
}

ALLOWED_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.Call,
    ast.keyword,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.USub,
)

SEVERITY_ORDER = {"error": 0, "warning": 1}
SEVERITY_LABEL = {"error": "❌ 错误", "warning": "⚠️ 警告", "ok": "✅ 通过"}


class RuleExpressionError(ValueError):
    """规则表达式非法时抛出，便于定位写错的规则。"""


def safe_eval(expr: str, variables: dict[str, float]) -> float:
    """受限表达式求值：只允许四则运算、幂与白名单函数。"""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise RuleExpressionError(f"表达式语法错误：{expr}") from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCS:
                raise RuleExpressionError(f"表达式使用了不允许的函数：{expr}")
        elif not isinstance(node, ALLOWED_NODES):
            raise RuleExpressionError(
                f"表达式包含不允许的语法 {type(node).__name__}：{expr}"
            )

    try:
        result = eval(  # noqa: S307 - 已通过 AST 白名单校验，且变量来自本地表格
            compile(tree, "<rule>", "eval"),
            {"__builtins__": {}},
            {**ALLOWED_FUNCS, **variables},
        )
    except ZeroDivisionError as exc:
        raise RuleExpressionError(f"表达式出现除以零：{expr}") from exc
    return float(result)


@dataclass
class Issue:
    room_id: str
    room_name: str
    rule_id: str
    title: str
    category: str
    severity: str
    expected: str
    actual: str
    deviation: str = ""
    reference: str = ""
    common_mistake: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "房间编号": self.room_id,
            "房间名称": self.room_name,
            "规则编号": self.rule_id,
            "检查项": self.title,
            "类别": self.category,
            "级别": SEVERITY_LABEL.get(self.severity, self.severity),
            "应有取值": self.expected,
            "实际取值": self.actual,
            "偏差": self.deviation,
            "依据": self.reference,
            "常见错因": self.common_mistake,
            "改正建议": self.suggestion,
        }


@dataclass
class RuleResult:
    room_id: str
    room_name: str
    rule_id: str
    title: str
    category: str
    severity: str  # ok / warning / error
    expected: str
    actual: str
    deviation: str = ""


@dataclass
class CheckReport:
    rules_version: str
    rows_checked: int
    results: list[RuleResult] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)

    # ---------- 汇总指标 ----------

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def total_checks(self) -> int:
        return len(self.results)

    @property
    def pass_rate(self) -> float:
        if not self.total_checks:
            return 0.0
        passed = sum(1 for result in self.results if result.severity == "ok")
        return round(passed / self.total_checks, 4)

    @property
    def clean_rooms(self) -> int:
        rooms_with_error = {issue.room_id for issue in self.issues}
        return self.rows_checked - len(rooms_with_error)

    @property
    def error_density(self) -> float:
        """错误密度：平均每间房的错误数，是"批改负担"的核心量化指标。"""
        if not self.rows_checked:
            return 0.0
        return round(self.error_count / self.rows_checked, 2)

    def room_scores(self, penalty: dict[str, int]) -> dict[str, int]:
        scores = {result.room_id: 100 for result in self.results}
        for issue in self.issues:
            scores[issue.room_id] = scores.get(issue.room_id, 100) - penalty.get(
                issue.severity, 0
            )
        return {room: max(score, 0) for room, score in scores.items()}

    def error_ranking(self) -> list[tuple[str, str, int]]:
        """错因排行：哪个规则被触发的次数最多，教师视角的教学重点。"""
        counter: dict[tuple[str, str], int] = {}
        for issue in self.issues:
            key = (issue.rule_id, issue.title)
            counter[key] = counter.get(key, 0) + 1
        ranked = sorted(counter.items(), key=lambda item: -item[1])
        return [(rule_id, title, count) for (rule_id, title), count in ranked]

    def to_frame(self) -> pd.DataFrame:
        rows = [issue.to_dict() for issue in self.issues]
        if not rows:
            return pd.DataFrame(
                columns=[
                    "房间编号",
                    "房间名称",
                    "规则编号",
                    "检查项",
                    "类别",
                    "级别",
                    "应有取值",
                    "实际取值",
                    "偏差",
                    "依据",
                    "常见错因",
                    "改正建议",
                ]
            )
        return pd.DataFrame(rows)

    def to_markdown(self) -> str:
        lines = [
            "# 计算自洽性校核报告",
            "",
            f"- 规则库版本：{self.rules_version}",
            f"- 校核房间数：{self.rows_checked}",
            f"- 校核项次：{self.total_checks}",
            f"- 一次通过率：{self.pass_rate * 100:.1f}%",
            f"- 错误数：{self.error_count}，警告数：{self.warning_count}",
            f"- 错误密度：{self.error_density} 处/房间",
            f"- 完全无错房间：{self.clean_rooms} / {self.rows_checked}",
            "",
        ]
        if self.missing_fields:
            lines += ["## 缺失字段", "", *(f"- {name}" for name in self.missing_fields), ""]

        ranking = self.error_ranking()
        if ranking:
            lines += ["## 错因排行（教学重点）", "", "| 规则 | 检查项 | 触发次数 |", "| --- | --- | --- |"]
            lines += [f"| {rid} | {title} | {count} |" for rid, title, count in ranking]
            lines.append("")

        if not self.issues:
            lines += ["## 结论", "", "本次提交未发现自洽性问题。", ""]
            return "\n".join(lines)

        lines += ["## 逐条问题", ""]
        for issue in sorted(self.issues, key=lambda i: (i.room_id, SEVERITY_ORDER.get(i.severity, 9))):
            lines += [
                f"### [{issue.rule_id}] {issue.room_name}（{issue.room_id}）- {issue.title}",
                "",
                f"- 级别：{SEVERITY_LABEL.get(issue.severity, issue.severity)}",
                f"- 应有取值：{issue.expected}",
                f"- 实际取值：{issue.actual}",
            ]
            if issue.deviation:
                lines.append(f"- 偏差：{issue.deviation}")
            if issue.common_mistake:
                lines.append(f"- 常见错因：{issue.common_mistake}")
            if issue.suggestion:
                lines.append(f"- 改正建议：{issue.suggestion}")
            if issue.reference:
                lines.append(f"- 依据：{issue.reference}")
            lines.append("")
        return "\n".join(lines)


class RuleEngine:
    """从 YAML 加载规则，对 DataFrame 逐项校核。"""

    def __init__(self, rule_path: Path) -> None:
        self.rule_path = rule_path
        config = yaml.safe_load(rule_path.read_text(encoding="utf-8")) or {}
        self.scene_id: str = config.get("scene_id", rule_path.stem)
        self.name: str = config.get("name", "校核规则")
        self.version: str = str(config.get("version", "unknown"))
        self.rules: list[dict] = list(config.get("rules") or [])
        self.header_aliases: dict[str, str] = dict(config.get("header_aliases") or {})
        self.field_labels: dict[str, str] = dict(config.get("field_labels") or {})
        self.units: dict[str, str] = dict(config.get("units") or {})
        self.penalty: dict[str, int] = dict(
            config.get("severity_penalty") or {"error": 15, "warning": 5}
        )

    # ---------- 输入规范化 ----------

    def normalize_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        """把中文表头映射成内部字段名，容忍空格与全半角差异。"""
        rename: dict[str, str] = {}
        for column in frame.columns:
            key = str(column).strip().replace(" ", "")
            if key in self.header_aliases:
                rename[column] = self.header_aliases[key]
            elif key in self.field_labels:
                rename[column] = key
        normalized = frame.rename(columns=rename)
        # 同名列只保留第一个
        normalized = normalized.loc[:, ~normalized.columns.duplicated()]
        return normalized

    def load_csv(self, path: Path) -> pd.DataFrame:
        last_error: Exception | None = None
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                frame = pd.read_csv(path, encoding=encoding)
                return self.normalize_frame(frame)
            except UnicodeDecodeError as exc:
                last_error = exc
        raise RuntimeError(f"无法解析 CSV：{path}（{last_error}）")

    # ---------- 校核 ----------

    def _cell(self, row: pd.Series, field_name: str) -> float | None:
        if field_name not in row:
            return None
        value = row[field_name]
        if pd.isna(value):
            return None
        if isinstance(value, str):
            value = value.strip().replace("，", "").replace(",", "")
            if not value:
                return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _evaluate(self, row: pd.Series) -> dict[str, float]:
        variables: dict[str, float] = {}
        for column in row.index:
            value = self._cell(row, column)
            if value is not None:
                variables[str(column)] = value
        return variables

    @staticmethod
    def _fmt(value: float | None, unit: str = "") -> str:
        if value is None:
            return "-"
        text = f"{value:.3f}".rstrip("0").rstrip(".")
        return f"{text} {unit}".strip()

    def _check_range(
        self, rule: dict, variables: dict[str, float]
    ) -> tuple[str, str, str, str] | None:
        field_name = rule["field"]
        value = variables.get(field_name)
        unit = self.units.get(field_name, "")
        if value is None:
            return None
        allowed = rule.get("allowed") or []
        recommended = rule.get("recommended") or []
        label = self.field_labels.get(field_name, field_name)

        if allowed and not (allowed[0] <= value <= allowed[1]):
            return (
                "error",
                f"{label} ∈ [{allowed[0]}, {allowed[1]}] {unit}",
                self._fmt(value, unit),
                "超出规范允许区间",
            )
        if recommended and not (recommended[0] <= value <= recommended[1]):
            return (
                "warning",
                f"{label} 推荐 [{recommended[0]}, {recommended[1]}] {unit}",
                self._fmt(value, unit),
                "在允许区间内，但偏离推荐范围",
            )
        return ("ok", f"{label} 取值合理", self._fmt(value, unit), "")

    def _check_threshold(
        self, rule: dict, variables: dict[str, float]
    ) -> tuple[str, str, str, str] | None:
        field_name = rule["field"]
        value = variables.get(field_name)
        unit = self.units.get(field_name, "")
        if value is None:
            return None
        label = self.field_labels.get(field_name, field_name)
        minimum = rule.get("min")
        maximum = rule.get("max")
        if minimum is not None and value < minimum:
            return ("error", f"{label} ≥ {minimum} {unit}", self._fmt(value, unit), "低于下限")
        if maximum is not None and value > maximum:
            return ("error", f"{label} ≤ {maximum} {unit}", self._fmt(value, unit), "高于上限")
        return ("ok", f"{label} 满足下限要求", self._fmt(value, unit), "")

    def _check_consistency(
        self, rule: dict, variables: dict[str, float]
    ) -> tuple[str, str, str, str] | None:
        target = rule["target"]
        actual = variables.get(target)
        unit = self.units.get(target, "")
        if actual is None:
            return None
        try:
            expected = safe_eval(rule["expr"], variables)
        except RuleExpressionError:
            raise
        except KeyError:
            # 公式依赖的字段缺失，跳过而非报错
            return None
        label = self.field_labels.get(target, target)
        tolerance = float(rule.get("tolerance", 0.05))
        if expected == 0:
            return None
        deviation = abs(actual - expected) / abs(expected)
        detail = f"应约为 {self._fmt(expected, unit)}，偏差 {deviation * 100:.1f}%"
        if deviation > tolerance:
            return ("error", f"{label} ≈ {self._fmt(expected, unit)}", self._fmt(actual, unit), detail)
        return ("ok", f"{label} 与公式自洽", self._fmt(actual, unit), "")

    def _check_difference_range(
        self, rule: dict, variables: dict[str, float]
    ) -> tuple[str, str, str, str] | None:
        high = variables.get(rule["high"])
        low = variables.get(rule["low"])
        if high is None or low is None:
            return None
        delta = high - low
        high_label = self.field_labels.get(rule["high"], rule["high"])
        low_label = self.field_labels.get(rule["low"], rule["low"])
        unit = self.units.get(rule["low"], "℃")
        allowed = rule.get("allowed") or []
        recommended = rule.get("recommended") or []
        if allowed and not (allowed[0] <= delta <= allowed[1]):
            return (
                "error",
                f"{high_label} − {low_label} ∈ [{allowed[0]}, {allowed[1]}] {unit}",
                self._fmt(delta, unit),
                "温差超出允许区间",
            )
        if recommended and not (recommended[0] <= delta <= recommended[1]):
            return (
                "warning",
                f"{high_label} − {low_label} 推荐 [{recommended[0]}, {recommended[1]}] {unit}",
                self._fmt(delta, unit),
                "温差偏离推荐区间",
            )
        return ("ok", "供回水温差合理", self._fmt(delta, unit), "")

    def _check_ratio(
        self, rule: dict, variables: dict[str, float]
    ) -> tuple[str, str, str, str] | None:
        numerator = variables.get(rule["numerator"])
        if numerator is None:
            return None
        try:
            denominator = safe_eval(rule["denominator"], variables)
        except RuleExpressionError:
            raise
        except KeyError:
            return None
        if not denominator:
            return None
        ratio = numerator / denominator
        allowed = rule.get("allowed") or []
        recommended = rule.get("recommended") or []
        num_label = self.field_labels.get(rule["numerator"], rule["numerator"])
        expected_text = f"比值 ∈ [{allowed[0]}, {allowed[1]}]"
        actual_text = f"{num_label} = {self._fmt(numerator)}，比值 {ratio:.3f}"
        if allowed and not (allowed[0] <= ratio <= allowed[1]):
            reason = "选型/配置不足或过度放大" if ratio < allowed[0] else "超出合理放大区间"
            return ("error", expected_text, actual_text, reason)
        if recommended and not (recommended[0] <= ratio <= recommended[1]):
            return ("warning", f"推荐比值 [{recommended[0]}, {recommended[1]}]", actual_text, "偏离推荐区间")
        return ("ok", expected_text, actual_text, "")

    def check_frame(self, frame: pd.DataFrame) -> CheckReport:
        frame = self.normalize_frame(frame)
        report = CheckReport(rules_version=self.version, rows_checked=len(frame))

        required_fields = {
            rule.get("field") or rule.get("target") or rule.get("numerator")
            for rule in self.rules
        }
        missing = sorted(
            self.field_labels.get(name, name)
            for name in required_fields
            if name and name not in frame.columns and name != "room_id"
        )
        if "room_id" not in frame.columns:
            missing.append("房间编号")
        report.missing_fields = missing

        for position, (_, row) in enumerate(frame.iterrows()):
            variables = self._evaluate(row)
            room_id = str(row.get("room_id", f"第{position + 1}行")).strip()
            room_name = str(row.get("room_name", room_id)).strip()

            for rule in self.rules:
                kind = rule.get("kind")
                try:
                    if kind == "range":
                        outcome = self._check_range(rule, variables)
                    elif kind == "threshold":
                        outcome = self._check_threshold(rule, variables)
                    elif kind == "consistency":
                        outcome = self._check_consistency(rule, variables)
                    elif kind == "difference_range":
                        outcome = self._check_difference_range(rule, variables)
                    elif kind == "ratio":
                        outcome = self._check_ratio(rule, variables)
                    else:
                        outcome = None
                except RuleExpressionError as exc:
                    report.missing_fields.append(f"规则 {rule.get('id')} 表达式异常：{exc}")
                    outcome = None

                if outcome is None:
                    continue

                severity, expected, actual, deviation = outcome
                report.results.append(
                    RuleResult(
                        room_id=room_id,
                        room_name=room_name,
                        rule_id=rule.get("id", ""),
                        title=rule.get("title", ""),
                        category=rule.get("category", ""),
                        severity=severity,
                        expected=expected,
                        actual=actual,
                        deviation=deviation,
                    )
                )
                if severity in {"error", "warning"}:
                    report.issues.append(
                        Issue(
                            room_id=room_id,
                            room_name=room_name,
                            rule_id=rule.get("id", ""),
                            title=rule.get("title", ""),
                            category=rule.get("category", ""),
                            severity=rule.get("severity", "error")
                            if severity == "error"
                            else "warning",
                            expected=expected,
                            actual=actual,
                            deviation=deviation,
                            reference=rule.get("reference", ""),
                            common_mistake=rule.get("common_mistake", ""),
                            suggestion=rule.get("suggestion", ""),
                        )
                    )
        return report


def load_engine(rules_dir: Path, scene_id: str) -> RuleEngine:
    path = rules_dir / f"{scene_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"找不到规则库：{path}")
    return RuleEngine(path)

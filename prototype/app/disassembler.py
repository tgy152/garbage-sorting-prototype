"""拆解引导引擎：把识别出的物品清单变成可执行的分步投放指令。

这是本作品与"拍照识垃圾"类产品拉开差距的地方。
现有产品大多只回答"某物属于哪一类"，而真实痛点是：
  · 复合垃圾要拆成几部分、每部分投哪个桶；
  · 类别判定常常是有条件的（餐盒洗干净才能回收）；
  · 投之前要先做什么（倒空、冲洗、沥干、撕碎）。

规则全部外置在 rules/<scene>.yaml，地区标签可切换，教师/环卫人员可自行维护。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.vision import DetectedItem, VisionResult

# 规则作者容易写成的桶名简写，需要在本地化时一并处理
SHORTHAND_BUCKETS = {
    "kitchen": "厨余",
    "residual": "其他",
}

# 分拣优先级：面对"一堆混在一起的垃圾"时的处理顺序。
# 顺序依据风险与污染扩散速度：有害先挑出，液体先倒掉，厨余先分离，
# 可回收物再冲洗，最后才是其他垃圾。
SORT_PRIORITY = [
    ("hazardous", "必须单独挑出", "混进别的桶会造成污染与安全风险"),
    ("liquid", "先倒掉", "液体会污染同桶的所有垃圾"),
    ("kitchen", "分离出来", "食物残渣混入可回收物会让整桶回收物失去回收价值"),
    ("recyclable", "冲洗沥干后投放", "可回收物必须干净才具备回收价值"),
    ("residual", "直接投放", "既不能回收、也不含食物残渣的部分"),
]

# 四分类桶位 -> 该桶应收的类别；用于"混投检查"
BIN_CATEGORY = {
    "recyclable": "recyclable",
    "hazardous": "hazardous",
    "kitchen": "kitchen",
    "residual": "residual",
}


@dataclass
class PartGuidance:
    part: str
    category: str
    category_label: str
    bin_color: str
    requirement: str
    prep: list[str] = field(default_factory=list)
    conditional: str = ""
    pitfall: str = ""
    note: str = ""
    reference: str = ""
    source: str = ""
    matched_items: list[str] = field(default_factory=list)
    count: int = 1

    def display_name(self) -> str:
        return f"{self.part} ×{self.count}" if self.count > 1 else self.part


@dataclass
class Guidance:
    region: str
    region_name: str
    summary: str
    is_composite: bool
    composite_id: str = ""
    composite_name: str = ""
    why: str = ""
    parts: list[PartGuidance] = field(default_factory=list)
    extras: list[PartGuidance] = field(default_factory=list)
    unmatched: list[DetectedItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    trigger_hits: int = 0
    residual_label: str = "其他垃圾"
    labels: dict[str, str] = field(default_factory=dict)
    bin_type: str = ""
    mismatches: list[PartGuidance] = field(default_factory=list)

    @property
    def has_mismatch(self) -> bool:
        return bool(self.mismatches)

    @property
    def all_parts(self) -> list[PartGuidance]:
        return self.parts + self.extras

    @property
    def has_conditional(self) -> bool:
        return any(part.conditional for part in self.all_parts)

    @property
    def has_pitfall(self) -> bool:
        return any(part.pitfall for part in self.all_parts)

    def category_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for part in self.all_parts:
            counts[part.category] = counts.get(part.category, 0) + 1
        return counts

    def to_markdown(self) -> str:
        def bin_text(part: PartGuidance) -> str:
            """液体类没有对应桶位，不渲染空桶名这种奇怪的写法。"""
            if not part.bin_color or part.bin_color == "-":
                return f"**{part.category_label}**"
            return f"**{part.category_label}**（{part.bin_color}桶）"

        lines: list[str] = []
        if self.is_composite:
            lines.append(f"### 这是复合垃圾：{self.composite_name}")
            if self.why:
                lines.append(f"\n> {self.why}")
            lines.append(f"\n**需要拆成 {len(self.parts)} 部分分别投放**\n")
        else:
            lines.append(f"### 识别结果：{self.summary or '未命名物品'}\n")

        lines.append("| 部件 | 投放类别 | 投之前要做 |")
        lines.append("| --- | --- | --- |")
        for part in self.all_parts:
            prep = "；".join(part.prep) if part.prep else "无"
            lines.append(f"| {part.display_name()} | {bin_text(part)} | {prep} |")

        conditional = [part for part in self.all_parts if part.conditional]
        if conditional:
            lines.append("\n**⚠️ 条件说明（最容易投错的地方）**\n")
            for part in conditional:
                lines.append(f"- **{part.display_name()}**：{part.conditional}")

        pitfalls = [part for part in self.all_parts if part.pitfall]
        if pitfalls:
            lines.append("\n**❌ 常见误投**\n")
            for part in pitfalls:
                lines.append(f"- **{part.display_name()}**：{part.pitfall}")

        notes = [part for part in self.all_parts if part.note]
        if notes:
            lines.append("\n**📌 补充说明**\n")
            for part in notes:
                lines.append(f"- **{part.display_name()}**：{part.note}")

        if self.steps:
            lines.append("\n**📋 操作步骤**\n")
            lines.extend(f"{index}. {step}" for index, step in enumerate(self.steps, start=1))

        # 物品较多时（典型场景：投放点拍到一堆混投的垃圾），
        # 给出分拣优先级，比逐个念表格更可执行
        if len(self.all_parts) >= 4:
            priority_lines: list[str] = []
            for index, (category, action, reason) in enumerate(SORT_PRIORITY, start=1):
                members = [
                    part.display_name() for part in self.all_parts if part.category == category
                ]
                if not members:
                    continue
                priority_lines.append(
                    f"{len(priority_lines) + 1}. **{action}**："
                    + "、".join(members)
                + f"（→ {self.labels.get(category, category)}）。{reason}"
                )
            if priority_lines:
                lines.append("\n**🧭 分拣优先级（按这个顺序处理效率最高）**\n")
                lines.extend(priority_lines)

        if self.unmatched:
            lines.append("\n**❓ 未匹配到规则的部件**\n")
            for item in self.unmatched:
                material = f"（{item.material}）" if item.material else ""
                lines.append(
                    f"- {item.name}{material}：规则库暂未收录，"
                    f"建议按**{self.residual_label}**投放，"
                    "并向当地环卫部门确认"
                )

        if self.mismatches:
            bin_label = self.labels.get(self.bin_type, self.bin_type)
            lines.append(
                f"\n**🚫 混投检查：这个桶是「{bin_label}」桶，"
                f"以下 {len(self.mismatches)} 项不该投在这里**\n"
            )
            lines.extend(
                f"- **{part.display_name()}** 应投"
                f"**{part.category_label}**（{part.bin_color}桶）"
                for part in self.mismatches
            )
            lines.append(
                "\n> 混投会让整桶垃圾失去分类价值，"
                "保洁需要二次分拣，是投放点最主要的成本来源。"
            )

        if self.warnings:
            lines.append("\n**提示**\n")
            lines.extend(f"- {warning}" for warning in self.warnings)

        lines.append(
            f"\n> 分类口径：**{self.region_name}**。"
            "各地标准存在差异，最终以所在城市现行分类目录为准。"
        )
        return "\n".join(lines)


def _normalize(text: str) -> str:
    return re.sub(r"[\s（）()【】\[\]·、,，。.]", "", text or "").lower()


def _similarity(name: str, key: str) -> float:
    """部件名与规则关键词的相似度（0~1）。

    中文垃圾名称的中心语在末尾（瓶/袋/盒/罐/纸），所以先做中心语校验，
    再做字符集合重叠，避免"塑料袋"误匹配"塑料瓶"。
    用相似度取最优匹配，而不是"第一条命中就返回"，
    这样"塑料瓶盖"会被更具体的瓶盖规则接住，而不是被饮料瓶规则抢走。
    """
    if not name or not key:
        return 0.0
    if name == key:
        return 1.0
    if name in key or key in name:
        shorter, longer = sorted((len(name), len(key)))
        return 0.9 + 0.1 * (shorter / longer)
    # 中心语不同则直接判不相关
    if name[-1] != key[-1]:
        return 0.0
    overlap = len(set(name) & set(key)) / min(len(set(name)), len(set(key)))
    return round(overlap * 0.8, 4)


class WasteDisassembler:
    def __init__(self, rule_path: Path) -> None:
        self.rule_path = rule_path
        config = yaml.safe_load(rule_path.read_text(encoding="utf-8")) or {}
        self.scene_id: str = config.get("scene_id", rule_path.stem)
        self.name: str = config.get("name", "垃圾分类规则库")
        self.version: str = str(config.get("version", "unknown"))
        self.regions: dict[str, dict] = dict(config.get("regions") or {})
        self.bins: dict[str, dict] = dict(config.get("bins") or {})
        self.composites: list[dict] = list(config.get("composites") or [])
        self.singles: list[dict] = list(config.get("singles") or [])
        # 命中多少个触发词才认定匹配到该复合物品
        self.min_trigger_hits: int = int(config.get("min_trigger_hits", 2))

    # ---------- 地区标签 ----------

    def region_options(self) -> list[tuple[str, str]]:
        return [(raw.get("name", key), key) for key, raw in self.regions.items()]

    def region_name(self, region: str) -> str:
        return str((self.regions.get(region) or {}).get("name", region))

    def _category_label(self, region: str, category: str) -> str:
        labels = (self.regions.get(region) or {}).get("labels") or {}
        return str(labels.get(category, category))

    def _localize_text(self, text: str, region: str) -> str:
        """把规则文本里硬编码的类别名替换为当前地区的叫法。

        否则会出现"上海口径下条件说明仍写其他垃圾"这类前后矛盾，
        这是投放引导系统最容易失去信任的地方。

        同时处理桶名简写（"厨余桶"→"湿垃圾桶"），因为规则作者很容易写成简写。
        """
        if not text:
            return text
        national = (self.regions.get("national") or {}).get("labels") or {}
        local = (self.regions.get(region) or {}).get("labels") or {}
        result = text
        for key, base_label in national.items():
            local_label = str(local.get(key, base_label))
            if local_label != base_label and base_label in result:
                result = result.replace(base_label, local_label)
        for key, shorthand in SHORTHAND_BUCKETS.items():
            local_label = str(local.get(key, national.get(key, shorthand)))
            if local_label != shorthand and f"{shorthand}桶" in result:
                result = result.replace(f"{shorthand}桶", f"{local_label}桶")
        return result

    def _bin_hint(self, category: str) -> tuple[str, str]:
        info = self.bins.get(category) or {}
        return str(info.get("color", "")), str(info.get("requirement", ""))

    # ---------- 匹配 ----------

    def _match_composite(self, haystack: str) -> tuple[dict | None, list[str], int]:
        return self._match_composite_with_hint(haystack, item_count=0)

    def required_trigger_hits(self, item_count: int) -> int:
        """照片里的物品越多，认定"这是某种复合垃圾"所需的证据越强。

        否则一堆混合垃圾会因为偶然出现"餐盒""塑料袋"两个词，
        被误判成"没吃完的外卖餐盒"。
        """
        required = self.min_trigger_hits
        if item_count >= 8:
            required += 1
        if item_count >= 15:
            required += 1
        return required

    def _match_composite_with_hint(
        self, haystack: str, item_count: int
    ) -> tuple[dict | None, list[str], int]:
        best: dict | None = None
        best_hits: list[str] = []
        for composite in self.composites:
            hits = [
                trigger
                for trigger in composite.get("triggers") or []
                if _normalize(trigger) in haystack
            ]
            if len(hits) > len(best_hits):
                best, best_hits = composite, hits
        if best is None or len(best_hits) < self.required_trigger_hits(item_count):
            return None, [], len(best_hits)
        return best, best_hits, len(best_hits)

    def _match_single(self, name: str) -> dict | None:
        target = _normalize(name)
        best_rule: dict | None = None
        best_score = 0.0
        for rule in self.singles:
            for key in rule.get("keys") or []:
                score = _similarity(target, _normalize(key))
                if score > best_score:
                    best_rule, best_score = rule, score
        return best_rule if best_score >= 0.8 else None

    def _build_part(self, raw: dict, region: str, source: str) -> PartGuidance:
        category = str(raw.get("category", "residual"))
        color, requirement = self._bin_hint(category)
        return PartGuidance(
            part=str(raw.get("name", "")),
            category=category,
            category_label=self._category_label(region, category),
            bin_color=color,
            requirement=self._localize_text(requirement, region),
            prep=[self._localize_text(str(item), region) for item in (raw.get("prep") or [])],
            conditional=self._localize_text(str(raw.get("conditional", "") or ""), region),
            pitfall=self._localize_text(str(raw.get("pitfall", "") or ""), region),
            note=self._localize_text(str(raw.get("note", "") or ""), region),
            reference=str(raw.get("reference", "") or ""),
            source=source,
        )

    # ---------- 主流程 ----------

    def guide(
        self,
        vision: VisionResult,
        region: str = "national",
        bin_type: str = "",
    ) -> Guidance:
        if region not in self.regions:
            region = next(iter(self.regions), "national")

        item_text = " ".join(
            f"{item.name} {item.material}" for item in vision.items
        )
        haystack = _normalize(item_text)
        composite, hits, hit_count = self._match_composite_with_hint(
            haystack, len(vision.items)
        )

        guidance = Guidance(
            region=region,
            region_name=self.region_name(region),
            summary=vision.summary,
            is_composite=composite is not None,
            trigger_hits=hit_count,
            residual_label=self._category_label(region, "residual"),
            labels={
                key: self._category_label(region, key)
                for key in ("recyclable", "hazardous", "kitchen", "residual", "liquid")
            },
        )

        covered_items: set[str] = set()
        if composite is not None:
            guidance.composite_id = str(composite.get("id", ""))
            guidance.composite_name = str(composite.get("name", ""))
            guidance.why = self._localize_text(str(composite.get("why", "")), region)
            for raw in composite.get("parts") or []:
                part = self._build_part(raw, region, guidance.composite_name)
                part.matched_items = [
                    item.name
                    for item in vision.items
                    if any(
                        _normalize(token) in _normalize(f"{item.name}{item.material}")
                        for token in [part.part] + list(raw.get("match") or [])
                    )
                ]
                guidance.parts.append(part)
            guidance.warnings.append(
                f"匹配依据：识别结果命中「{composite.get('name')}」的 "
                f"{hit_count} 个特征（{'、'.join(hits)}）"
            )
            # 已被复合规则覆盖的识别项：命中触发词，或名称与某个部件名互相包含。
            # 后者用于避免重复统计（例如识别出"纸杯"，同时也被 C05 的"纸杯本体"覆盖）。
            part_tokens = [_normalize(part.part) for part in guidance.parts]
            part_tokens += [_normalize(token) for token in hits]
            covered_items = set()
            for item in vision.items:
                item_name = _normalize(item.name)
                if not item_name:
                    continue
                if any(
                    token and (item_name in token or token in item_name)
                    for token in part_tokens
                ):
                    covered_items.add(item.name)

        # 未被复合规则覆盖的物品，按单一物品规则处理
        # 同一类物品可能被识别出多件（例如一堆易拉罐），合并成一条并标注数量
        extra_index: dict[str, PartGuidance] = {}
        for item in vision.items:
            if item.name in covered_items:
                continue
            rule = self._match_single(item.name)
            if rule is None:
                guidance.unmatched.append(item)
                continue
            rule_name = str(rule.get("name", item.name))
            existing = extra_index.get(rule_name)
            if existing is not None:
                existing.count += 1
                existing.matched_items.append(item.name)
                continue
            category = str(rule.get("category", "residual"))
            color, requirement = self._bin_hint(category)
            part = PartGuidance(
                part=rule_name,
                category=category,
                category_label=self._category_label(region, category),
                bin_color=color,
                requirement=self._localize_text(requirement, region),
                prep=[
                    self._localize_text(str(entry), region)
                    for entry in (rule.get("prep") or [])
                ],
                conditional=self._localize_text(
                    str(rule.get("conditional", "") or ""), region
                ),
                pitfall=self._localize_text(str(rule.get("pitfall", "") or ""), region),
                note=self._localize_text(str(rule.get("note", "") or ""), region),
                reference=str(rule.get("reference", "") or ""),
                source="单一物品规则",
                matched_items=[item.name],
            )
            extra_index[rule_name] = part
            guidance.extras.append(part)

        guidance.steps = self._build_steps(guidance)

        # 混投检查：用户指明"这是哪个桶"时，找出不该出现在该桶里的物品
        if bin_type in BIN_CATEGORY:
            expected = BIN_CATEGORY[bin_type]
            if expected == "kitchen":
                expected_categories = {"kitchen", "liquid"}
            else:
                expected_categories = {expected}
            guidance.bin_type = bin_type
            guidance.mismatches = [
                part for part in guidance.all_parts if part.category not in expected_categories
            ]
            if guidance.mismatches:
                guidance.warnings.append(
                    f"该照片被标记为「{self._category_label(region, bin_type)}」桶，"
                    f"其中 {len(guidance.mismatches)} 项属于混投"
                )

        if not guidance.is_composite and not guidance.all_parts:
            guidance.warnings.append(
                "识别结果未匹配到任何规则，请补拍更清晰的照片，或检查规则库覆盖范围。"
            )
        return guidance

    @staticmethod
    def _build_steps(guidance: Guidance) -> list[str]:
        """按"先分离内容物 → 再拆分部件 → 再预处理 → 最后投放"的固定顺序生成步骤。"""
        steps: list[str] = []
        liquids = [part for part in guidance.all_parts if part.category == "liquid"]
        kitchen = [part for part in guidance.all_parts if part.category == "kitchen"]
        if liquids or kitchen:
            targets = liquids + kitchen
            steps.append(
                "先分离内容物："
                + "；".join(f"{part.part} → {part.category_label}" for part in targets)
            )
        if guidance.is_composite:
            steps.append(f"把物品拆成 {len(guidance.parts)} 个部件，分别处置")
        needs_wash = [
            part for part in guidance.all_parts if part.requirement and "冲洗" in part.requirement
        ]
        if needs_wash:
            steps.append(
                "冲洗并沥干：" + "、".join(part.part for part in needs_wash)
            )
        steps.append(
            "按上表逐个投放："
            + "；".join(
                f"{part.part} → {part.category_label}"
                + (f"（{part.bin_color}桶）" if part.bin_color and part.bin_color != "-" else "")
                for part in guidance.all_parts
            )
        )
        return steps


def load_disassembler(rules_dir: Path, scene_id: str) -> WasteDisassembler:
    path = rules_dir / f"{scene_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"找不到规则库：{path}")
    return WasteDisassembler(path)

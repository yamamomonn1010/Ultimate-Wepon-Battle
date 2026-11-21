"""自由記述から、対戦判定に使う能力の特徴を読み取る。"""

from dataclasses import dataclass
import re
from typing import Literal
from unicodedata import normalize


AbilityStatus = Literal["分類済み", "未分類", "爆散対象"]
MainEffect = Literal["攻撃", "反射", "防御", "回復", "運操作"]

# 発動条件は文頭、代償は「代わりに」などで始まる文末の部分を読む。
CONDITION = re.compile(
    r"^(?P<condition>一度だけ|(?:[0-9]+|[一二三四五六七八九十]+)回だけ"
    r"|[^、,。!?]+?(?:とき(?:だけ)?|時(?:だけ)?|場合(?:だけ)?|なら|れば))"
    r"[、,]?\s*"
)
COST = re.compile(r"(?:代わりに|かわりに|代償として)[、,]?\s*(?P<cost>.+)$")

# 文全体が明確な保証に当てはまるときだけ爆散させる。
# 「必ず勝つとは限らない」のように後ろに否定が続く場合は一致しない。
ABSOLUTE_EFFECT = re.compile(
    r"(?:何があっても(?:必ず勝つ|負けない)|(?:必ず|絶対に)勝つ"
    r"|(?:すべて|全て)の攻撃を無効化(?:する|して(?:必ず|絶対に)勝つ)"
    r"|どんな攻撃も無効化する|(?:常に|永久に)無敵(?:になる|である))"
    r"(?:武器|剣)?"
)

EFFECT_PATTERNS: tuple[tuple[MainEffect, str], ...] = (
    ("攻撃", r"(?:相手に)?体当たりする|(?:相手を)?直接攻撃する"),
    ("反射", r"(?:相手の)?攻撃を反射(?:する|できる)"),
    ("防御", r"無敵になる|(?:相手の)?攻撃を防ぐ"),
    ("回復", r"(?:自分の)?体力を回復する"),
    ("運操作", r"(?:自分の)?運を(?:上げる|操作する)"),
)


@dataclass(frozen=True)
class AbilityAnalysis:
    status: AbilityStatus
    main_effect: MainEffect | None
    tags: tuple[str, ...]
    condition: str | None
    cost: str | None
    reason: str


def analyze_ability(description: str) -> AbilityAnalysis:
    """対応する言い回しから主効果を一つ選び、判断できない文は未分類にする。"""
    text = normalize("NFKC", description).strip().rstrip("。.!?").strip()
    condition_match = CONDITION.match(text)
    condition = condition_match["condition"] if condition_match else None
    effect_text = text[condition_match.end():] if condition_match else text

    cost_match = COST.search(effect_text)
    cost = cost_match["cost"] if cost_match else None
    if cost_match:
        effect_text = effect_text[:cost_match.start()].rstrip(" 、,")

    context = ""
    if condition:
        context += f" 発動条件「{condition}」。"
    if cost:
        context += f" 代償「{cost}」。"

    if condition is None and cost is None and ABSOLUTE_EFFECT.fullmatch(text):
        return AbilityAnalysis(
            "爆散対象", None, (), None, None,
            "無条件の勝利や全面無効化を保証するため、持ち主が爆散する。",
        )

    effects = set()
    for clause in re.split(r"[、,。.!?]+", effect_text):
        clause = clause.strip()
        for effect, pattern in EFFECT_PATTERNS:
            if re.fullmatch(pattern, clause):
                effects.add(effect)
                break
        else:
            # 読み取れない節を含む文では、意味や主効果を決めつけない。
            return AbilityAnalysis(
                "未分類", None, (), condition, cost,
                "主効果を特定できないため、自由枠の基本点を適用する。" + context,
            )

    if len(effects) == 1:
        effect = effects.pop()
        tags = ("直接攻撃",) if effect == "攻撃" else ()
        return AbilityAnalysis(
            "分類済み", effect, tags, condition, cost,
            f"主効果を「{effect}」として認識した。" + context,
        )

    return AbilityAnalysis(
        "未分類", None, (), condition, cost,
        "主効果が一つに定まらないため、自由枠の基本点を適用する。" + context,
    )

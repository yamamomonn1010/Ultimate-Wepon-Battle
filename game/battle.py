"""能力の解析結果と属性相性から、対戦の結果を決める。"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal

from game.abilities import AbilityAnalysis, analyze_ability


Outcome = Literal["1P", "2P", "引き分け"]
ELEMENTS_PATH = Path(__file__).resolve().parents[1] / "data" / "elements.json"
ATTRIBUTE_ADVANTAGE_POINTS = 2
ABILITY_BASE_POINTS = 1


@dataclass(frozen=True)
class Weapon:
    name: str
    element: str
    ability: str

    def __post_init__(self) -> None:
        for label, value, limit in (
            ("武器名", self.name, 30),
            ("特殊能力", self.ability, 50),
        ):
            if not value.strip() or len(value) > limit:
                raise ValueError(f"{label}は空白だけにせず、{limit}文字以内で入力してください。")


@dataclass(frozen=True)
class ElementRules:
    elements: frozenset[str]
    advantages: frozenset[tuple[str, str]]


def load_element_rules(path: Path = ELEMENTS_PATH) -> ElementRules:
    """JSONから、有利な属性と不利な属性の組を読み込む。"""
    config = json.loads(path.read_text(encoding="utf-8"))
    elements = frozenset(config["elements"])
    advantages = frozenset((winner, loser) for winner, loser in config["advantages"])

    for winner, loser in advantages:
        if winner not in elements or loser not in elements:
            raise ValueError(f"相性設定に未登録の属性があります ({winner}, {loser})。")
        if winner == loser or (loser, winner) in advantages:
            raise ValueError(f"属性相性の設定が矛盾しています ({winner}, {loser})。")
    return ElementRules(elements, advantages)


@dataclass(frozen=True)
class ScoreBreakdown:
    attribute_points: int
    ability_base_points: int
    ability_matchup_points: int

    @property
    def total(self) -> int:
        return self.attribute_points + self.ability_base_points + self.ability_matchup_points


@dataclass(frozen=True)
class BattleResult:
    ability_analyses: tuple[AbilityAnalysis, AbilityAnalysis]
    scores: tuple[ScoreBreakdown, ScoreBreakdown] | None
    provisional_outcome: Outcome | None
    final_outcome: Outcome
    reasons: tuple[str, ...]


def score_ability_matchup(ability: AbilityAnalysis, opponent: AbilityAnalysis) -> int:
    """自分の主効果と相手のタグだけを照合する。"""
    if ability.main_effect == "反射" and "直接攻撃" in opponent.tags:
        return 1
    return 0


def resolve_battle(first: Weapon, second: Weapon, rules: ElementRules) -> BattleResult:
    """入力を確認し、爆散または通常得点で結果を確定する。"""
    for weapon in (first, second):
        if weapon.element not in rules.elements:
            raise ValueError(f"属性「{weapon.element}」は使用できません。")

    abilities = (analyze_ability(first.ability), analyze_ability(second.ability))
    first_explodes = abilities[0].status == "爆散対象"
    second_explodes = abilities[1].status == "爆散対象"
    if first_explodes and second_explodes:
        return BattleResult(abilities, None, None, "引き分け", ("両者が爆散したため引き分け。",))
    if first_explodes:
        return BattleResult(abilities, None, None, "2P", ("1Pが爆散したため2Pの勝利。",))
    if second_explodes:
        return BattleResult(abilities, None, None, "1P", ("2Pが爆散したため1Pの勝利。",))

    reasons = []
    scores = []
    # 双方を加点前の能力解析結果から評価する。得点は相手の評価に使わない。
    for index, (weapon, opponent) in enumerate(((first, second), (second, first))):
        attribute_points = 0
        if (weapon.element, opponent.element) in rules.advantages:
            attribute_points = ATTRIBUTE_ADVANTAGE_POINTS
            reasons.append(f"{index + 1}Pの{weapon.element}は相手の{opponent.element}に有利。")

        matchup_points = score_ability_matchup(abilities[index], abilities[1 - index])
        if matchup_points:
            reasons.append(f"{index + 1}Pが相手の直接攻撃を反射し、相性で1点を獲得。")
        scores.append(ScoreBreakdown(attribute_points, ABILITY_BASE_POINTS, matchup_points))

    first_score, second_score = scores
    outcome: Outcome = "引き分け"
    if first_score.total > second_score.total:
        outcome = "1P"
    elif first_score.total < second_score.total:
        outcome = "2P"

    totals = f"通常得点は1Pが{first_score.total}点、2Pが{second_score.total}点"
    if outcome == "引き分け":
        reasons.append(f"{totals}で、同点のため引き分け。")
    else:
        reasons.append(f"{totals}で、得点の高い{outcome}の勝利。")

    return BattleResult(abilities, (first_score, second_score), outcome, outcome, tuple(reasons))

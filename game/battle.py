"""能力、属性相性、運、特殊イベントから対戦結果を決める。"""

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
from random import Random
from secrets import randbits
from typing import Literal
from unicodedata import normalize

from game.abilities import AbilityAnalysis, analyze_ability
from game.events import EventRule, load_event_rules, select_event


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
    weapon_luck_points: int = 0
    ability_luck_points: int = 0
    match_luck_points: int = 0
    event_points: int = 0

    @property
    def total(self) -> int:
        return (
            self.attribute_points + self.ability_base_points + self.ability_matchup_points
            + self.weapon_luck_points + self.ability_luck_points + self.match_luck_points
            + self.event_points
        )


@dataclass(frozen=True)
class BattleResult:
    ability_analyses: tuple[AbilityAnalysis, AbilityAnalysis]
    scores: tuple[ScoreBreakdown, ScoreBreakdown] | None
    provisional_outcome: Outcome | None
    final_outcome: Outcome
    reasons: tuple[str, ...]
    adjusted_scores: tuple[ScoreBreakdown, ScoreBreakdown] | None = None
    event_id: str | None = None
    seed: int | None = None


def score_ability_matchup(ability: AbilityAnalysis, opponent: AbilityAnalysis) -> int:
    """自分の主効果と相手のタグだけを照合する。"""
    if ability.main_effect == "反射" and "直接攻撃" in opponent.tags:
        return 1
    return 0


def score_weapon_luck(name: str) -> int:
    """武器名の表記を整え、SHA-256の末尾1バイトの偶奇を0点か1点にする。"""
    normalized_name = normalize("NFKC", name).strip()
    digest = sha256(normalized_name.encode("utf-8")).digest()
    return digest[-1] % 2


def outcome_from_points(first_points: int, second_points: int) -> Outcome:
    if first_points > second_points:
        return "1P"
    if second_points > first_points:
        return "2P"
    return "引き分け"


def resolve_battle(
    first: Weapon,
    second: Weapon,
    rules: ElementRules,
    *,
    seed: int | None = None,
    events: tuple[EventRule, ...] | None = None,
) -> BattleResult:
    """爆散を先に確認し、通常得点と特殊イベントから勝敗を確定する。"""
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

    if seed is None:
        seed = randbits(64)
    # 試合中の運とイベントは別々に抽選する。
    luck_random = Random(f"{seed}:luck")
    event_random = Random(f"{seed}:event")
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
        scores.append(ScoreBreakdown(
            attribute_points,
            ABILITY_BASE_POINTS,
            matchup_points,
            weapon_luck_points=score_weapon_luck(weapon.name),
            ability_luck_points=int(abilities[index].main_effect == "運操作"),
            match_luck_points=luck_random.randint(0, 1),
        ))

    first_score, second_score = scores
    first_points, second_points = first_score.total, second_score.total
    provisional_outcome = outcome_from_points(first_points, second_points)
    final_outcome = provisional_outcome
    adjusted_scores = None

    if events is None:
        events = load_event_rules()
    event = select_event(events, event_random.randint(1, 100), abs(first_points - second_points))
    score_label = "通常得点"
    if event is not None:
        reasons.append(event.message)
        if event.effect == "add_to_trailing":
            assert event.effect_value is not None  # 設定の読み込み時に検証済み。
            trailing_index = 0 if first_points < second_points else 1
            scores[trailing_index] = replace(scores[trailing_index], event_points=event.effect_value)
            adjusted_scores = (scores[0], scores[1])
            first_points, second_points = scores[0].total, scores[1].total
            final_outcome = outcome_from_points(first_points, second_points)
            reasons.append(f"{trailing_index + 1}Pが特殊イベントで{event.effect_value}点を獲得。")
            score_label = "補正後の得点"
        elif event.effect == "force_draw":
            final_outcome = "引き分け"

    totals = f"{score_label}は1Pが{first_points}点、2Pが{second_points}点"
    if event is not None and event.effect == "force_draw":
        reasons.append(f"{totals}だったが、特殊イベントにより引き分け。")
    elif final_outcome == "引き分け":
        reasons.append(f"{totals}で、同点のため引き分け。")
    else:
        reasons.append(f"{totals}で、得点の高い{final_outcome}の勝利。")

    return BattleResult(
        abilities,
        (first_score, second_score),
        provisional_outcome,
        final_outcome,
        tuple(reasons),
        adjusted_scores=adjusted_scores,
        event_id=event.id if event is not None else None,
        seed=seed,
    )

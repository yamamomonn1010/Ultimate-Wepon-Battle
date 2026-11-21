"""特殊イベントの設定を読み込み、1回分の抽選結果を判定する。"""

from dataclasses import dataclass
import json
from pathlib import Path


EVENTS_PATH = Path(__file__).resolve().parents[1] / "data" / "events.json"
EFFECT_BY_KIND = {
    "flavor": "add_message",
    "score": "add_to_trailing",
    "outcome": "force_draw",
}


@dataclass(frozen=True)
class EventRule:
    id: str
    kind: str
    probability: int
    condition: str
    effect: str
    message: str
    condition_value: int | None = None
    effect_value: int | None = None


def load_event_rules(path: Path = EVENTS_PATH) -> tuple[EventRule, ...]:
    """イベントを設定順に読み込み、抽選に使える内容かを確認する。"""
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, list):
        raise ValueError("イベント設定は一覧で記述してください。")

    rules = []
    used_ids = set()
    for index, entry in enumerate(config, start=1):
        try:
            rule = EventRule(**entry)
        except TypeError as error:
            raise ValueError(f"イベント設定の{index}件目の項目が正しくありません。") from error

        if not isinstance(rule.id, str) or not rule.id.strip() or rule.id in used_ids:
            raise ValueError(f"イベントIDが空、または重複しています ({rule.id})。")
        if type(rule.probability) is not int or not 0 <= rule.probability <= 100:
            raise ValueError(f"イベント「{rule.id}」の確率は0〜100の整数で指定してください。")
        if rule.condition not in ("always", "score_gap", "has_winner"):
            raise ValueError(f"イベント「{rule.id}」の条件に対応していません。")
        if rule.condition == "score_gap":
            if type(rule.condition_value) is not int or rule.condition_value < 0:
                raise ValueError(f"イベント「{rule.id}」の点差は0以上の整数で指定してください。")
        expected_effect = EFFECT_BY_KIND.get(rule.kind) if isinstance(rule.kind, str) else None
        if expected_effect is None or rule.effect != expected_effect:
            raise ValueError(f"イベント「{rule.id}」の種類と効果の組み合わせに対応していません。")
        if rule.effect == "add_to_trailing":
            if type(rule.effect_value) is not int or rule.effect_value <= 0:
                raise ValueError(f"イベント「{rule.id}」の加点は正の整数で指定してください。")
        if not isinstance(rule.message, str) or not rule.message.strip():
            raise ValueError(f"イベント「{rule.id}」には実況文が必要です。")
        used_ids.add(rule.id)
        rules.append(rule)

    if sum(rule.probability for rule in rules) > 100:
        raise ValueError("イベント確率の合計は100%以内にしてください。")
    return tuple(rules)


def select_event(events: tuple[EventRule, ...], roll: int, score_gap: int) -> EventRule | None:
    """抽選値に割り当てられた1件だけを確認する。score_gapは通常得点の差の絶対値。"""
    upper_bound = 0
    for event in events:
        upper_bound += event.probability
        if roll > upper_bound:
            continue

        if event.condition == "score_gap" and score_gap != event.condition_value:
            return None
        if score_gap == 0 and (event.condition == "has_winner" or event.effect == "add_to_trailing"):
            return None
        return event

    return None

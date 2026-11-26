"""Flaskで2人分の入力を受け取り、対戦結果と実況を表示する。"""

from flask import Flask, render_template, request

from game.battle import BattleResult, Weapon, load_element_rules, resolve_battle
from game.events import load_event_rules


app = Flask(__name__)
PLAYERS = ("1P", "2P")
FIELDS = ("name", "element", "ability")


def battle_commentary(result: BattleResult, weapons: tuple[Weapon, Weapon], event_message: str | None) -> list[str]:
    """確定済みの判定から、画面に表示する実況を作る。"""
    lines = ["対戦開始！"]
    if result.scores is None:
        for player, ability in zip(PLAYERS, result.ability_analyses):
            if ability.status == "爆散対象":
                lines.append(f"{player}は強すぎる能力に耐えきれず、爆散した！")
        return lines

    for player, score, weapon, opponent in zip(PLAYERS, result.scores, weapons, reversed(weapons)):
        if score.attribute_points:
            lines.append(f"{player}の{weapon.element}属性は、相手の{opponent.element}属性に有利だ！")
        if score.ability_matchup_points:
            lines.append(f"{player}が相手の直接攻撃を反射した！")

    if event_message is not None:
        lines.append(event_message)
        if result.adjusted_scores is not None:
            lines.append("劣勢だった側が盛り返した！")
    if len(lines) == 1:
        lines.append("両者の武器の相性、能力、運で決着をつける！")
    return lines


@app.route("/", methods=["GET", "POST"])
def arena():
    rules = load_element_rules()
    elements = sorted(rules.elements)
    entries = tuple(
        {field: request.form.get(f"{player}_{field}", "").replace("\r\n", "\n") for field in FIELDS}
        for player in PLAYERS
    )
    context = {"players": PLAYERS, "entries": entries, "elements": elements}
    if request.method == "GET":
        return render_template("arena.html", **context)

    errors = {}
    weapons = []
    for player, entry in zip(PLAYERS, entries):
        player_errors = []
        if entry["element"] not in rules.elements:
            player_errors.append("登録されている属性を選んでください。")
        try:
            weapons.append(Weapon(**entry))
        except ValueError as error:
            player_errors.append(str(error))
        if player_errors:
            errors[player] = player_errors

    if errors:
        return render_template("arena.html", errors=errors, **context), 400

    first, second = weapons
    events = load_event_rules()
    result = resolve_battle(first, second, rules, events=events)
    event_message = next((event.message for event in events if event.id == result.event_id), None)
    outcome = result.final_outcome
    verdict = "引き分け" if outcome == "引き分け" else f"{outcome}の勝利"
    return render_template(
        "result.html",
        commentary=battle_commentary(result, (first, second), event_message),
        verdict=verdict,
        **context,
    )

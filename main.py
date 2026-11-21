"""固定の武器2つで、基本の勝敗判定を実行する。"""

from game.battle import Weapon, load_element_rules, resolve_battle


def main() -> None:
    weapons = (
        Weapon("ひっくり返しの鏡", "水", "相手の攻撃を反射する"),
        Weapon("突進するやかん", "水", "相手に体当たりする"),
    )
    result = resolve_battle(weapons[0], weapons[1], load_element_rules())

    for index, (weapon, ability) in enumerate(zip(weapons, result.ability_analyses), start=1):
        print(f"{index}P {weapon.name}（{weapon.element}）")
        print(f"  能力「{weapon.ability}」  {ability.reason}")

    if result.scores is not None:
        for index, score in enumerate(result.scores, start=1):
            print(
                f"{index}P 得点 {score.total}点"
                f"（属性 {score.attribute_points}、能力基本 {score.ability_base_points}"
                f"、能力相性 {score.ability_matchup_points}）"
            )

    print("勝敗理由")
    for reason in result.reasons:
        print(f"  {reason}")


if __name__ == "__main__":
    main()

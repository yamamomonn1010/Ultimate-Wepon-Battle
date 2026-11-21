"""固定の武器2つで、基本の勝敗判定を実行する。"""

from argparse import ArgumentParser

from game.battle import Weapon, load_element_rules, resolve_battle


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, help="同じ対戦結果を再現するための整数")
    args = parser.parse_args()

    weapons = (
        Weapon("ひっくり返しの鏡", "水", "相手の攻撃を反射する"),
        Weapon("突進するやかん", "水", "相手に体当たりする"),
    )
    result = resolve_battle(weapons[0], weapons[1], load_element_rules(), seed=args.seed)

    for index, (weapon, ability) in enumerate(zip(weapons, result.ability_analyses), start=1):
        print(f"{index}P {weapon.name}（{weapon.element}）")
        print(f"  能力「{weapon.ability}」  {ability.reason}")

    if result.seed is not None:
        print(f"試合シード {result.seed}")

    if result.scores is not None:
        for index, score in enumerate(result.scores, start=1):
            print(
                f"{index}P 通常得点 {score.total}点"
                f"（属性 {score.attribute_points}、能力基本 {score.ability_base_points}"
                f"、能力相性 {score.ability_matchup_points}、固有の運 {score.weapon_luck_points}"
                f"、能力による運 {score.ability_luck_points}、試合ごとの運 {score.match_luck_points}）"
            )

    if result.adjusted_scores is not None:
        for index, score in enumerate(result.adjusted_scores, start=1):
            print(f"{index}P 補正後 {score.total}点（イベント補正 +{score.event_points}）")

    print("勝敗理由")
    for reason in result.reasons:
        print(f"  {reason}")


if __name__ == "__main__":
    main()

"""MVP第1段階の能力解析と対戦判定のテスト。"""

from dataclasses import replace
from functools import partial
from unittest import TestCase
from unittest.mock import patch

from game.abilities import analyze_ability
from game.battle import Weapon, load_element_rules, resolve_battle


DIRECT_ATTACK = "相手に体当たりする"
REFLECTION = "相手の攻撃を反射する"
RECOVERY = "自分の体力を回復する"
UNKNOWN = "相手の月曜日を火曜日にする"
GUARANTEE = "何があっても必ず勝つ"


class AbilityAnalysisTests(TestCase):
    def test_reflection_and_direct_attack_have_distinct_effects_and_tags(self) -> None:
        reflection = analyze_ability(REFLECTION)
        attack = analyze_ability(DIRECT_ATTACK)
        self.assertEqual((reflection.status, reflection.main_effect, reflection.tags), ("分類済み", "反射", ()))
        self.assertEqual((attack.main_effect, attack.tags), ("攻撃", ("直接攻撃",)))

    def test_negated_or_qualified_phrase_is_not_a_guarantee(self) -> None:
        for description in (
            "相手の攻撃を反射できない",
            "相手の攻撃を反射することはできない",
            "必ず勝つわけではない",
            "絶対に勝つとは限らない",
            "無限に伸びるが攻撃力はゼロの剣",
        ):
            with self.subTest(description=description):
                analysis = analyze_ability(description)
                self.assertEqual(analysis.status, "未分類")
                self.assertIsNone(analysis.main_effect)
                self.assertEqual(analysis.tags, ())

    def test_limited_invulnerability_is_defense_but_clear_guarantee_explodes(self) -> None:
        defense = analyze_ability("一度だけ無敵になる")
        self.assertEqual((defense.status, defense.main_effect, defense.condition), ("分類済み", "防御", "一度だけ"))

        for description in (GUARANTEE, "すべての攻撃を無効化して必ず勝つ剣"):
            with self.subTest(description=description):
                self.assertEqual(analyze_ability(description).status, "爆散対象")

    def test_conditions_and_costs_are_kept(self) -> None:
        analysis = analyze_ability(" １回だけ、無敵になる代わりに動けなくなる。 ")
        self.assertEqual(analysis.main_effect, "防御")
        self.assertEqual(analysis.condition, "1回だけ")
        self.assertEqual(analysis.cost, "動けなくなる")
        self.assertIn("1回だけ", analysis.reason)
        self.assertIn("動けなくなる", analysis.reason)

        for description in ("満月のときだけ、必ず勝つ", "必ず勝つ代わりに動けなくなる"):
            with self.subTest(description=description):
                self.assertNotEqual(analyze_ability(description).status, "爆散対象")

    def test_ambiguous_multiple_effects_are_unclassified(self) -> None:
        analysis = analyze_ability(f"{DIRECT_ATTACK}、{REFLECTION}")
        self.assertEqual(analysis.status, "未分類")
        self.assertEqual(analysis.tags, ())


class BattleTests(TestCase):
    def setUp(self) -> None:
        self.rules = load_element_rules()
        self.resolve_battle = partial(resolve_battle, seed=0, events=())

    def test_attribute_advantage_in_both_player_positions(self) -> None:
        for stronger, weaker in (("水", "炎"), ("炎", "風"), ("風", "水")):
            cases = ((stronger, weaker, "1P", (2, 0)), (weaker, stronger, "2P", (0, 2)))
            for first, second, winner, expected_points in cases:
                with self.subTest(first=first, second=second):
                    result = self.resolve_battle(Weapon("左", first, RECOVERY), Weapon("右", second, RECOVERY), self.rules)
                    assert result.scores is not None
                    self.assertEqual(tuple(score.attribute_points for score in result.scores), expected_points)
                    self.assertEqual(result.provisional_outcome, winner)
                    self.assertEqual(result.final_outcome, winner)

    def test_same_and_unlisted_attribute_matchups_are_neutral(self) -> None:
        for first, second in (("炎", "炎"), ("炎", "水")):
            with self.subTest(first=first, second=second):
                rules = replace(self.rules, advantages=frozenset({("炎", "風")}))
                result = self.resolve_battle(Weapon("左", first, RECOVERY), Weapon("右", second, RECOVERY), rules)
                assert result.scores is not None
                self.assertEqual(tuple(score.attribute_points for score in result.scores), (0, 0))

    def test_only_reflection_gets_matchup_point_against_direct_attack(self) -> None:
        reflection = Weapon("鏡", "水", REFLECTION)
        attack = Weapon("やかん", "水", DIRECT_ATTACK)
        for first, second, expected_points, winner in (
            (reflection, attack, (1, 0), "1P"),
            (attack, reflection, (0, 1), "2P"),
        ):
            with self.subTest(winner=winner):
                result = self.resolve_battle(first, second, self.rules)
                assert result.scores is not None
                self.assertEqual(tuple(score.ability_matchup_points for score in result.scores), expected_points)
                self.assertEqual(result.final_outcome, winner)
                self.assertTrue(any("直接攻撃を反射" in reason for reason in result.reasons))

    def test_reflection_has_no_bonus_against_nonattack_or_other_reflection(self) -> None:
        for opponent_ability in (RECOVERY, REFLECTION, UNKNOWN):
            with self.subTest(opponent_ability=opponent_ability):
                result = self.resolve_battle(
                    Weapon("鏡", "水", REFLECTION),
                    Weapon("相手", "水", opponent_ability),
                    self.rules,
                )
                assert result.scores is not None
                self.assertEqual(tuple(score.ability_matchup_points for score in result.scores), (0, 0))

    def test_unknown_ability_gets_the_same_base_point(self) -> None:
        result = self.resolve_battle(Weapon("暦", "風", UNKNOWN), Weapon("薬箱", "風", RECOVERY), self.rules)
        assert result.scores is not None
        self.assertEqual(tuple(score.ability_base_points for score in result.scores), (1, 1))
        self.assertIn("自由枠の基本点", result.ability_analyses[0].reason)

    def test_one_explosion_gives_other_player_win_without_scoring(self) -> None:
        for abilities, winner in (((GUARANTEE, DIRECT_ATTACK), "2P"), ((DIRECT_ATTACK, GUARANTEE), "1P")):
            with self.subTest(winner=winner), patch("game.battle.ScoreBreakdown") as score_breakdown:
                result = self.resolve_battle(
                    Weapon("左", "水", abilities[0]),
                    Weapon("右", "炎", abilities[1]),
                    self.rules,
                )
                score_breakdown.assert_not_called()
                self.assertEqual(result.final_outcome, winner)
                self.assertIsNone(result.provisional_outcome)
                self.assertIsNone(result.scores)
                self.assertIn("爆散", result.reasons[0])

    def test_both_explosions_give_draw_without_scoring(self) -> None:
        result = self.resolve_battle(Weapon("左", "水", GUARANTEE), Weapon("右", "炎", GUARANTEE), self.rules)
        self.assertEqual(result.final_outcome, "引き分け")
        self.assertIsNone(result.provisional_outcome)
        self.assertIsNone(result.scores)

    def test_equal_scores_give_normal_draw(self) -> None:
        result = self.resolve_battle(Weapon("左", "風", RECOVERY), Weapon("右", "風", RECOVERY), self.rules)
        assert result.scores is not None
        self.assertEqual(tuple(score.total for score in result.scores), (1, 1))
        self.assertEqual(result.provisional_outcome, "引き分け")
        self.assertEqual(result.final_outcome, "引き分け")
        self.assertIn("同点", result.reasons[-1])

    def test_weapon_length_boundaries_and_blank_inputs(self) -> None:
        weapon = Weapon("甲" * 30, "炎", "力" * 50)
        self.assertEqual((len(weapon.name), len(weapon.ability)), (30, 50))

        for name, ability, invalid_field in (
            ("甲" * 31, RECOVERY, "武器名"),
            ("武器", "力" * 51, "特殊能力"),
            ("  ", RECOVERY, "武器名"),
            ("武器", "　", "特殊能力"),
        ):
            with self.subTest(invalid_field=invalid_field), self.assertRaisesRegex(ValueError, invalid_field):
                Weapon(name, "炎", ability)

    def test_only_one_registered_attribute_is_allowed(self) -> None:
        for element in ("", "水・炎", "雷"):
            with self.subTest(element=element), self.assertRaisesRegex(ValueError, "属性"):
                resolve_battle(Weapon("左", element, RECOVERY), Weapon("右", "風", RECOVERY), self.rules)

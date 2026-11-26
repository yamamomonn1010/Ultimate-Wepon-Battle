"""既存の対戦判定とFlask画面の接続を検証する。"""

from unittest import TestCase
from unittest.mock import patch

from app import app


class ArenaTests(TestCase):
    def setUp(self) -> None:
        self.client = app.test_client()
        self.inputs = {
            "1P_name": "炎刀",
            "1P_element": "水",
            "1P_ability": "相手の攻撃を反射する",
            "2P_name": "やかん",
            "2P_element": "炎",
            "2P_ability": "相手に体当たりする",
        }

    def test_create_weapons_and_show_final_verdict_without_scores(self) -> None:
        page = self.client.get("/").get_data(as_text=True)
        for element in ("炎", "水", "風"):
            self.assertIn(f'<option value="{element}"', page)

        with patch("game.battle.randbits", return_value=42):
            response = self.client.post("/", data=self.inputs)
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("対戦開始！", page)
        self.assertIn("1Pの水属性は、相手の炎属性に有利だ！", page)
        self.assertIn("1Pが相手の直接攻撃を反射した！", page)
        self.assertIn('id="verdict" tabindex="-1">1Pの勝利', page)
        self.assertNotIn("得点", page)
        self.assertNotIn("1点", page)

    def test_invalid_input_renders_errors_and_keeps_the_other_weapon(self) -> None:
        cases = (
            ("1P_element", "雷", "登録されている属性"),
            ("1P_name", " " * 2, "武器名は空白だけにせず"),
            ("1P_name", "武" * 31, "30文字以内"),
            ("1P_ability", "力" * 51, "50文字以内"),
        )
        for field, value, message in cases:
            with self.subTest(field=field), patch("app.resolve_battle") as resolve:
                response = self.client.post("/", data={**self.inputs, field: value})
                self.assertEqual(response.status_code, 400)
                page = response.get_data(as_text=True)
                self.assertIn(message, page)
                self.assertIn('value="やかん"', page)
                self.assertIn("相手に体当たりする", page)
                resolve.assert_not_called()

    def test_length_limits_and_escaping_apply_to_result_and_rematch(self) -> None:
        name = "<script>" + "武" * 22
        ability = "</textarea>" + "力" * 39
        response = self.client.post("/", data={**self.inputs, "1P_name": name, "1P_ability": ability})
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn(f'name="1P_name" value="&lt;script&gt;{"武" * 22}"', page)
        self.assertIn(f'name="1P_ability">\n&lt;/textarea&gt;{"力" * 39}</textarea>', page)
        self.assertNotIn("<script>", page)
        self.assertNotIn(ability, page)

    def test_repeated_submission_uses_a_new_seed(self) -> None:
        with patch("game.battle.randbits", side_effect=(42, 77)) as generate_seed:
            for _ in range(2):
                response = self.client.post("/", data=self.inputs)
                self.assertEqual(response.status_code, 200)
                self.assertIn('name="1P_name" value="炎刀"', response.get_data(as_text=True))
        self.assertEqual(generate_seed.call_count, 2)

    def test_explosion_can_decide_battle_or_end_in_a_draw(self) -> None:
        explosive = "何があっても必ず勝つ"
        for second, verdict in ((self.inputs["2P_ability"], "2Pの勝利"), (explosive, "引き分け")):
            with self.subTest(verdict=verdict):
                response = self.client.post("/", data={
                    **self.inputs, "1P_ability": explosive, "2P_ability": second,
                })
                page = response.get_data(as_text=True)
                self.assertIn("1Pは強すぎる能力に耐えきれず、爆散した！", page)
                self.assertEqual("2Pは強すぎる能力に耐えきれず、爆散した！" in page, second == explosive)
                self.assertIn(f'id="verdict" tabindex="-1">{verdict}', page)

    def test_normal_draw_and_each_special_event(self) -> None:
        base = {
            "1P_name": "左", "1P_element": "水", "1P_ability": "自分の体力を回復する",
            "2P_name": "左", "2P_element": "水", "2P_ability": "自分の体力を回復する",
        }
        cases = (
            (0, {}, None, "引き分け"),
            (77, {"2P_element": "炎"}, "審判がくしゃみをした！", "1Pの勝利"),
            (149, {"1P_ability": "自分の運を上げる"}, "劣勢側が突然覚醒した！", "引き分け"),
            (795, {"2P_element": "炎"}, "隕石が落下した！", "引き分け"),
        )
        for seed, overrides, message, verdict in cases:
            with self.subTest(seed=seed), patch("game.battle.randbits", return_value=seed):
                response = self.client.post("/", data={**base, **overrides})
                self.assertEqual(response.status_code, 200)
                page = response.get_data(as_text=True)
                verdict_markup = f'id="verdict" tabindex="-1">{verdict}'
                self.assertIn(verdict_markup, page)
                if message:
                    self.assertIn(message, page)
                    self.assertLess(page.index(message), page.index(verdict_markup))
                self.assertNotIn("得点", page)

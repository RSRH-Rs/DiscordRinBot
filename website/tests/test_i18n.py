"""Console string dictionary: lookups, interpolation and file shape."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import i18n  # noqa: E402


class ConsoleStringTests(unittest.TestCase):
    def test_tr_returns_value(self):
        self.assertEqual(i18n.tr('bar.save'), '保存')

    def test_tr_interpolates(self):
        self.assertEqual(i18n.tr('overview.welcome.roles', n=3), '自动给 3 个身份组')

    def test_leveling_strings(self):
        expected = {
            'intro': '聊天攒经验，小凛会按经验给大家排名。关闭后已有等级会保留。',
            'master': '开启等级系统',
            'tab.settings': '设置',
            'tab.board': '排行榜',
            'notify': '升级提示',
            'notify_here': '发在原频道',
            'notify_channel': '发到指定频道',
            'notify_off': '不发',
            'channel': '发到哪个频道',
            'rewards': '等级奖励',
            'rewards_hint': '成员达到等级后自动获得身份组，升到更高等级也会保留。手动摘掉的身份组，成员下次获得经验时会再发回来。',
            'add': '添加奖励',
            'no_rewards': '还没有等级奖励。',
            'max': '最多 20 条奖励',
            'level_unit': '级',
            'level_label': '等级',
            'role_label': '身份组',
            'pick_role': '— 选择身份组 —',
            'remove': '移除这条奖励',
            'unknown_role': '未知身份组',
            'unknown_channel': '未知频道',
            'warn.above': '这个身份组排在小凛之上，发不出去。到服务器设置里把小凛的身份组拖到它上面。',
            'warn.managed': '这个身份组由其他机器人或集成管理，小凛不能发放。',
            'warn.deleted': '这个身份组已不存在，请换一个或删掉这条奖励。',
            'warn.no_permission': '小凛没有“管理身份组”权限，等级奖励暂时发不出去。加上这个权限后会自动恢复。',
            'error.duplicate_level': '这个等级已经有奖励了。',
            'error.duplicate_role': '这个身份组已经用在别的等级上了。',
            'error.need_channel': '请选择要发到哪个频道。',
            'error.need_role': '请选择一个身份组。',
            'error.level_range': '等级要在 1 到 999 之间。',
            'error.fix_first': '请先改正页面上标出的内容。',
        }
        for key, text in expected.items():
            self.assertEqual(i18n.tr('leveling.' + key), text, key)
        self.assertEqual(i18n.tr('leveling.board'), 'leveling.board')

    def test_unused_strings_are_gone(self):
        for key in ['common.count', 'common.optional', 'welcome.enabled_hint', 'welcome.appearance', 'automod.enabled_hint', 'logs.enabled_hint']:
            self.assertEqual(i18n.tr(key), key)

    def test_missing_key_returns_key(self):
        with self.assertLogs('rinbot.i18n', 'WARNING'):
            self.assertEqual(i18n.tr('nope.key'), 'nope.key')

    def test_dictionary_is_flat_strings(self):
        strings = i18n.console_strings()
        self.assertTrue(strings)
        for key, value in strings.items():
            self.assertRegex(key, r'^[a-z_]+(\.[A-Za-z0-9_]+)+$')
            self.assertIsInstance(value, str)
            self.assertTrue(value.strip(), key)


if __name__ == '__main__':
    unittest.main()

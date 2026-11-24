import importlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

with patch.object(sys, 'path', [str(Path(__file__).resolve().parents[1]/'scripts'), *sys.path]):
    suite = importlib.import_module('colocated-suite')


class FeaturedTest(unittest.TestCase):
    def test_complete_rounds_and_labels(self):
        runs = [
            dict(id=key, round=round_number, runtime={'Guest': 'Debian GNU/Linux 13'},
                 phases={'startup': {'ready_seconds': 1 + round_number},
                         'sustained': {'app_rss_mib': 142 + round_number,
                                       'p99_ms': 11 + round_number,
                                       'available_mib': 160 + round_number}})
            for round_number in (1, 2) for key in suite.LABELS
        ]
        data = dict(status='completed', protocol=suite.protocol(version='v1'), candidates=runs)
        svg = suite.featured_svg(data)
        self.assertEqual(svg, suite.featured_svg(data))
        labels = [element.text for element in ElementTree.fromstring(svg).iter('{http://www.w3.org/2000/svg}text')]
        self.assertIn("App readiness (s)", labels)
        self.assertTrue(any("40 RPS sustained" in label for label in labels))
        self.assertTrue(any("HotSpot 27" in label for label in labels))
        custom = dict(suite.benchmark_config.STANDARD, jvm=['-Xmx90m'])
        digest = suite.benchmark_config.sha256(custom)
        custom_svg = suite.featured_svg(dict(data, protocol=suite.protocol(version='v1', config=custom),
                                             configuration_sha256=digest))
        self.assertIn(f'Custom v1 · {digest[:12]}', custom_svg)
        self.assertNotIn("Database readiness (s)", labels)
        for label in ('Jex + Jdbi', 'Quarkus + Jdbi', 'Spring Boot + JDBC', 'Micronaut Data JDBC'):
            self.assertEqual(labels.count(label), 4)
        for value in ('2.00', '3.00', '143.00', '144.00', '12.00', '13.00', '161.00', '162.00'):
            self.assertEqual(labels.count(value), 4)
        for status in ('incomplete', 'failed'):
            self.assertIsNone(suite.featured_svg(dict(data, status=status)))
        self.assertIsNone(suite.featured_svg(dict(data, protocol=suite.protocol(True, 'v1'))))

    def test_guest_storage_rejects_tmpfs(self):
        with patch.object(suite.subprocess, 'run'), patch.object(
                suite.subprocess, 'check_output', return_value='ext4\n') as find_mount:
            suite.verify_guest_storage('vm', '/var/tmp/fb-runs')
            self.assertEqual(find_mount.call_args.args[0][-2:], ['-T', '/var/tmp/fb-runs'])
            find_mount.return_value = 'tmpfs\n'
            with self.assertRaisesRegex(ValueError, 'Found tmpfs'):
                suite.verify_guest_storage('vm', '/tmp/fb-runs')

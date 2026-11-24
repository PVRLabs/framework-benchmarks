import importlib
from subprocess import CompletedProcess
import unittest

storage_errors = importlib.import_module('benchmark-preflight').storage_errors


class BenchmarkStorageTest(unittest.TestCase):
    def test_small_guest_rejects_tmpfs_but_large_guest_can_keep_it(self):
        def findmnt(*args):
            return CompletedProcess(args, 0, 'tmpfs\n' if args[-1] == '/tmp' else 'ext4\n')

        self.assertEqual(storage_errors(510000, 524288, [], findmnt), ['/tmp must be disk-backed'])
        self.assertEqual(storage_errors(700000, 786432, [], findmnt), [])
        self.assertEqual(storage_errors(510000, 524288, [], lambda *args:
                                       CompletedProcess(args, 0, 'ext4\n')), [])

    def test_custom_evidence_mount_must_resolve_to_disk(self):
        for result in (CompletedProcess([], 0, 'tmpfs\n'), CompletedProcess([], 1, '')):
            def findmnt(*args):
                return result if args[-1] == '/evidence' else CompletedProcess(args, 0, 'ext4\n')

            self.assertEqual(storage_errors(700000, 786432, ['/evidence'], findmnt),
                             ['/evidence must be disk-backed'])

"""Real raw RocksDB persistence, backup failures and legacy archive support."""
import importlib
import os
from pathlib import Path
import pickle
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from easyrocks import RocksDB, WriteBatch

LEGACY_BACKUP = Path(os.environ.get(
    'EASYROCKS_LEGACY_BACKUP', Path(__file__).parent / 'fixtures/rocksdb6'))


class RocksDBTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.db = RocksDB(str(self.root / 'db'), safe_serialization=True)
        self.addCleanup(self.db.close)
        self.backup = self.root / 'backup'

    def test_raw_legacy_roundtrip_and_batch(self):
        value = {'items': [1, b'bytes']}
        self.db.db.put(b'legacy', pickle.dumps(value, protocol=5))
        self.assertEqual(self.db.get(b'legacy'), value)
        batch = WriteBatch()
        for key in (b'a', b'b', b'c'):
            self.db.put(key, value, write_batch=batch)
        self.db.commit(batch)
        self.db.reload()
        iterator = self.db.db.iterkeys()
        iterator.seek_to_last()
        self.assertEqual(list(reversed(iterator)), [
                         b'legacy', b'c', b'b', b'a'])
        iterator = self.db.db.iteritems()
        iterator.seek(b'b')
        self.assertEqual([key for key, _ in reversed(iterator)], [b'b', b'a'])
        self.assertEqual([key for key, _ in self.db.scan(
            start_key=b'a', stop_key=b'c')], [b'a', b'b', b'c'])

    def test_safe_serialization_requires_boolean(self):
        with self.assertRaises(TypeError):
            RocksDB(str(self.root / 'bad'), safe_serialization='true')

    def test_revisions_restore_exact_values_and_delete_only_one(self):
        for version in (1, 2):
            self.db.put(b'version', version)
            self.db.backup(str(self.backup))
        info = self.db.backup_info(str(self.backup))
        self.assertEqual([item['backup_id'] for item in info], [1, 2])
        self.assertTrue(all(item['size'] > 0 for item in info))
        self.assertEqual(set(info[0]), {'backup_id', 'timestamp', 'size'})
        self.db.restore_backup(str(self.backup), 1)
        self.assertEqual(self.db.get(b'version'), 1)
        self.db.restore_backup(str(self.backup))
        self.assertEqual(self.db.get(b'version'), 2)
        self.db.delete_backup(str(self.backup), 2)
        self.db.backup(str(self.backup))
        self.assertEqual([item['backup_id'] for item in
                          self.db.backup_info(str(self.backup))], [1, 3])

    def test_failed_backup_preserves_previous(self):
        self.db.put(b'important', 1)
        self.db.backup(str(self.backup))
        module = importlib.import_module('easyrocks.easyrocks')
        with patch.object(module, 'Checkpoint') as checkpoint:
            checkpoint.return_value.create_checkpoint.side_effect = OSError()
            with self.assertRaises(OSError):
                self.db.backup(str(self.backup))
        self.db.put(b'important', 2)
        self.db.restore_backup(str(self.backup))
        self.assertEqual(self.db.get(b'important'), 1)

    def test_invalid_restore_preserves_open_database(self):
        self.db.put(b'important', 1)
        self.backup.mkdir()
        with self.assertRaises(ValueError):
            self.db.restore_backup(str(self.backup))
        self.assertEqual(self.db.get(b'important'), 1)
        for path in (self.db.path, str(self.root), self.db.path + '/nested'):
            with self.assertRaises(ValueError):
                self.db.restore_backup(path)
            with self.assertRaises(ValueError):
                self.db.backup(path)

    def test_corrupt_backup_preserves_current_data(self):
        self.db.put(b'important', 1)
        self.db.backup(str(self.backup))
        self.db.put(b'important', 2)
        current = self.backup / 'private/1/CURRENT'
        current.write_bytes(b'invalid')
        with self.assertRaises(ValueError):
            self.db.restore_backup(str(self.backup))
        self.assertEqual(self.db.get(b'important'), 2)

    def test_restore_copy_failure_and_rename_failure_preserve_data(self):
        self.db.put(b'important', 1)
        self.db.backup(str(self.backup))
        self.db.put(b'important', 2)
        with patch('easyrocks.backups.shutil.copyfile', side_effect=OSError()):
            with self.assertRaises(OSError):
                self.db.restore_backup(str(self.backup))
        original = Path.rename

        def rename(source, target):
            if source.name == 'database':
                raise OSError('injected destination rename failure')
            return original(source, target)

        with patch.object(Path, 'rename', rename):
            with self.assertRaises(OSError):
                self.db.restore_backup(str(self.backup))
        self.assertEqual(self.db.get(b'important'), 2)
        self.db.reload()
        self.assertEqual(self.db.get(b'important'), 2)

    def test_first_restore_rename_failure_reopens_original(self):
        self.db.put(b'important', 1)
        self.db.backup(str(self.backup))
        with patch.object(Path, 'rename', side_effect=OSError()):
            with self.assertRaises(OSError):
                self.db.restore_backup(str(self.backup))
        self.assertEqual(self.db.get(b'important'), 1)

    def test_backup_paths_cannot_redirect_or_delete_another_revision(self):
        self.db.put(b'important', 1)
        self.db.backup(str(self.backup))
        with self.assertRaises(TypeError):
            self.db.delete_backup(str(self.backup))
        original = self.backup / 'private/1'
        moved = self.backup / 'original'
        original.rename(moved)
        original.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.db.restore_backup(str(self.backup), 1)
        with self.assertRaises(ValueError):
            self.db.delete_backup(str(self.backup), 1)
        self.assertTrue((moved / 'CURRENT').is_file())
        bad = self.root / 'bad-backup'
        bad.mkdir()
        (bad / 'meta').symlink_to(moved, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.db.backup(str(bad))

    def test_restore_through_database_symlink_preserves_alias(self):
        self.db.put(b'important', 1)
        self.db.backup(str(self.backup))
        self.db.close()
        alias = self.root / 'alias'
        alias.symlink_to(self.root / 'db', target_is_directory=True)
        linked = RocksDB(str(alias))
        try:
            linked.put(b'important', 2)
            linked.restore_backup(str(self.backup))
            self.assertTrue(alias.is_symlink())
            self.assertEqual(linked.get(b'important'), 1)
        finally:
            linked.close()

    def test_restore_interrupted_between_renames_recovers_original(self):
        self.db.put(b'important', 1)
        self.db.close()
        target = Path(self.db.path)
        target.rename(target.with_name(target.name + '.restore-previous'))
        self.db.reload()
        self.assertEqual(self.db.get(b'important'), 1)

    @unittest.skipUnless(LEGACY_BACKUP.is_dir(),
                         'requires native BackupEngine fixture')
    def test_native_legacy_shared_backup(self):
        shutil.copytree(LEGACY_BACKUP, self.backup)
        self.db.restore_backup(str(self.backup), 1)
        self.assertEqual(self.db.get(b'legacy'), 1)
        self.db.restore_backup(str(self.backup), 2)
        self.assertEqual(self.db.get(b'legacy'), 2)
        self.db.backup(str(self.backup))
        self.db.delete_backup(str(self.backup), 1)
        self.db.restore_backup(str(self.backup), 2)
        self.assertEqual(self.db.get(b'legacy'), 2)


if __name__ == '__main__':
    unittest.main()

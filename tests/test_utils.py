#!/usr/bin/env python
# -*- coding: utf-8 -*-

import importlib.util
import os
from pathlib import Path
import pickle
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / 'easyrocks' / 'utils.py'
SPEC = importlib.util.spec_from_file_location('easyrocks_utils', MODULE_PATH)
utils = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(utils)


class LegacyValue:
    pass


class UtilsTest(unittest.TestCase):

    def test_messagepack_round_trip(self):
        value = {
            b'bytes-key': [1, True, None, 'text', b'bytes-value'],
        }
        self.assertEqual(
            utils.unpack(utils.pack(value, safe=True), safe=True),
            value,
        )

    def test_safe_legacy_pickle_remains_readable(self):
        value = {'height': 7, 'hash': b'abc'}
        encoded = pickle.dumps(value, protocol=5)
        self.assertEqual(utils.unpack(encoded, safe=True), value)

    def test_graphn_primitive_block_shape_round_trip(self):
        block = {
            'hash': bytes.fromhex('ab' * 32),
            'version': 1,
            'prev_hash': bytes.fromhex('00' * 32),
            'timestamp': 1785772513000,
            'signature': bytes.fromhex('12' * 64),
            'items': [
                {
                    'hash': bytes.fromhex('cd' * 32),
                    'items': [
                        {
                            'hash': bytes.fromhex('ef' * 32),
                            'data': b'evidence',
                        },
                    ],
                },
            ],
        }
        encoded = utils.pack(block, safe=True)
        self.assertEqual(utils.unpack(encoded, safe=True), block)

    def test_legacy_pickle_cannot_import_or_execute_globals(self):
        marker = Path(tempfile.gettempdir()) / 'easyrocks-unsafe-pickle'
        if marker.exists():
            marker.unlink()

        class Payload:
            def __reduce__(self):
                return os.system, (f'touch {marker}',)

        encoded = pickle.dumps(Payload(), protocol=5)
        with self.assertRaisesRegex(ValueError, 'safe legacy pickle'):
            utils.unpack(encoded, safe=True)
        self.assertFalse(marker.exists())

    def test_safe_legacy_pickle_rejects_trailing_data(self):
        encoded = pickle.dumps({'height': 7}, protocol=5) + b'trailing'
        with self.assertRaisesRegex(ValueError, 'safe legacy pickle'):
            utils.unpack(encoded, safe=True)

    def test_unsupported_and_cyclic_values_fail_before_storage(self):
        with self.assertRaisesRegex(TypeError, 'unsupported'):
            utils.pack(object(), safe=True)

        cyclic = []
        cyclic.append(cyclic)
        with self.assertRaisesRegex(TypeError, 'cyclic'):
            utils.pack(cyclic, safe=True)

        with self.assertRaisesRegex(TypeError, 'safe map keys'):
            utils.pack({7: 'integer key'}, safe=True)

    def test_legacy_mode_remains_available_for_existing_consumers(self):
        encoded = utils.pack(LegacyValue())
        self.assertIsInstance(utils.unpack(encoded), LegacyValue)
        self.assertEqual(utils.unpack(utils.pack({7: 'value'})), {7: 'value'})

    def test_safe_flags_and_encoded_input_are_strictly_typed(self):
        with self.assertRaisesRegex(TypeError, 'safe must be a boolean'):
            utils.pack({'value': 1}, safe='true')
        with self.assertRaisesRegex(TypeError, 'safe must be a boolean'):
            utils.unpack(b'\x80', safe=1)
        with self.assertRaisesRegex(TypeError, 'value must be bytes'):
            utils.unpack(bytearray(b'\x80'), safe=True)


if __name__ == '__main__':
    unittest.main()

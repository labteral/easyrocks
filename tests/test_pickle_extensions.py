import copyreg
import pickle
from unittest.mock import patch

import pytest
from easyrocks.utils import unpack


def test_safe_legacy_reader_rejects_a_cached_executable_extension(tmp_path):
    marker = tmp_path / 'executed'
    expression = f"__import__('pathlib').Path({str(marker)!r}).write_text('unsafe')"
    payload = b'\x80\x02\x82\x2a' + pickle.dumps((expression,), protocol=2)[2:-1] + b'R.'
    with patch.dict(copyreg._extension_cache, {42: eval}):
        with pytest.raises(ValueError):
            unpack(payload, safe=True)
    assert not marker.exists()

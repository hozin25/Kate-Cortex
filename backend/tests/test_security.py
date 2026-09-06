"""DPAPI 静态加密原语（平台无关断言：Windows 真加密，其他平台恒等）"""

import sys

from kate_cortex.security import decrypt_secret, encrypt_secret


class TestSecretRoundtrip:
    def test_roundtrip(self):
        assert decrypt_secret(encrypt_secret("sk-abc-123")) == "sk-abc-123"

    def test_encrypt_is_idempotent(self):
        once = encrypt_secret("sk-x")
        assert encrypt_secret(once) == once  # 已加密值不重复加密

    def test_decrypt_passthrough_plaintext(self):
        assert decrypt_secret("sk-plain") == "sk-plain"

    def test_empty_values_passthrough(self):
        assert encrypt_secret(None) is None
        assert encrypt_secret("") == ""
        assert decrypt_secret(None) is None

    def test_ciphertext_hides_plaintext_on_windows(self):
        stored = encrypt_secret("sk-super-secret")
        if sys.platform == "win32":
            assert "sk-super-secret" not in stored
            assert stored.startswith("dpapi:")
        else:
            assert stored == "sk-super-secret"

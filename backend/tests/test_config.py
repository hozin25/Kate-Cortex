from pathlib import Path

from kate_cortex.config import load_config


class TestLoadConfig:
    def test_dev_defaults_point_to_repo_vault(self, monkeypatch):
        monkeypatch.delenv("KATE_VAULT_PATH", raising=False)
        monkeypatch.delenv("KATE_DB_PATH", raising=False)
        monkeypatch.delenv("KATE_PACKAGED", raising=False)

        config = load_config()

        repo_root = Path(__file__).resolve().parents[2]
        assert config.vault_path == repo_root / "vault"
        assert config.host == "127.0.0.1"
        assert config.port == 1738

    def test_env_overrides_paths_and_port(self, tmp_path, monkeypatch):
        vault = tmp_path / "custom-vault"
        db_file = tmp_path / "custom.sqlite"
        monkeypatch.setenv("KATE_VAULT_PATH", str(vault))
        monkeypatch.setenv("KATE_DB_PATH", str(db_file))
        monkeypatch.setenv("KATE_PORT", "9999")

        config = load_config()

        assert config.vault_path == vault
        assert config.db_path == db_file
        assert config.port == 9999

    def test_packaged_mode_uses_user_profile(self, monkeypatch):
        monkeypatch.delenv("KATE_VAULT_PATH", raising=False)
        monkeypatch.delenv("KATE_DB_PATH", raising=False)
        monkeypatch.setenv("KATE_PACKAGED", "1")

        config = load_config()

        assert "Kate-Cortex" in str(config.vault_path)
        assert config.db_path.parent == config.vault_path

    def test_db_defaults_inside_vault(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KATE_VAULT_PATH", str(tmp_path / "v"))
        monkeypatch.delenv("KATE_DB_PATH", raising=False)

        config = load_config()

        assert config.db_path == config.vault_path / "index.sqlite"

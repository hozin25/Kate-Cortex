"""export_markdown 导出测试：文件落盘 / 文件名安全 / agent 集成（SSE file_saved）"""

import json

from fastapi.testclient import TestClient

from kate_cortex.config import Config
from kate_cortex.main import create_app
from kate_cortex.providers.base import Done, TextDelta, ToolCallDelta
from kate_cortex.providers.fake import FakeProvider
from kate_cortex.skills.export import _safe_stem, default_export_dir, export_markdown

from test_chat_api import parse_sse

PLAN = "# 杭州两日游\n\n## Day 1\n- 西湖\n- 灵隐寺\n"


class TestExportTool:
    def test_writes_file_and_returns_path(self, tmp_path):
        result = export_markdown(
            {"title": "杭州两日游", "content_markdown": PLAN},
            export_dir=str(tmp_path),
        )

        path = tmp_path / "杭州两日游.md"
        assert result == {"title": "杭州两日游", "file_path": str(path)}
        assert path.read_text(encoding="utf-8") == PLAN

    def test_creates_nested_dir(self, tmp_path):
        target = tmp_path / "a" / "b"
        export_markdown(
            {"title": "清单", "content_markdown": "- x"}, export_dir=str(target)
        )
        assert (target / "清单.md").exists()

    def test_filename_sanitized(self):
        assert _safe_stem('杭州/两日游:Day*1?') == "杭州-两日游-Day-1"
        assert _safe_stem('  ..  ') == "未命名"

    def test_collision_gets_counter_suffix(self, tmp_path):
        args = {"title": "行程", "content_markdown": "x"}
        first = export_markdown(args, export_dir=str(tmp_path))
        second = export_markdown(args, export_dir=str(tmp_path))

        assert (tmp_path / "行程.md").exists()
        assert second["file_path"].endswith("行程 (2).md")
        assert first["file_path"] != second["file_path"]

    def test_default_dir_when_not_configured(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "kate_cortex.skills.export.default_export_dir",
            lambda: str(tmp_path / "默认导出"),
        )
        result = export_markdown({"title": "a", "content_markdown": "b"})

        assert (tmp_path / "默认导出" / "a.md").exists()
        assert "默认导出" in result["file_path"]

    def test_default_export_dir_points_outside_vault_pattern(self):
        # 导出目录基于用户文档目录，而不是 vault 内部（避免被知识库索引）
        assert "Documents" in default_export_dir()


def make_client(env, export_dir: str | None = None) -> TestClient:
    app = create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
    client = TestClient(app)
    client.put(
        "/api/settings",
        json={"provider_keys": {"deepseek": "sk-test"}, "export_dir": export_dir},
    )
    return client


class TestAgentIntegration:
    def test_export_tool_streams_file_saved_and_writes_file(self, env, tmp_path):
        client = make_client(env, export_dir=str(tmp_path))
        fake = FakeProvider(
            rounds=[
                [
                    ToolCallDelta(
                        index=0,
                        id="c1",
                        name="export_markdown",
                        arguments=json.dumps(
                            {"title": "杭州两日游", "content_markdown": PLAN},
                            ensure_ascii=False,
                        ),
                    ),
                    Done("tool_calls"),
                ],
                [TextDelta("已导出为 Markdown 文件。"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        session_id = client.post(
            "/api/chat/sessions", json={"provider": "deepseek"}
        ).json()["id"]
        resp = client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "把行程保存成 md 文件", "rag_enabled": False},
        )
        events = parse_sse(resp.text)
        names = [name for name, _ in events]

        assert names == ["citations", "file_saved", "delta", "done"]
        saved = next(data for name, data in events if name == "file_saved")
        assert saved["title"] == "杭州两日游"
        assert (tmp_path / "杭州两日游.md").read_text(encoding="utf-8") == PLAN

        # 工具结果摘要回传模型（含路径，模型得以告知用户）
        tool_msg = fake.calls[1]["messages"][-1]
        assert tool_msg["role"] == "tool"
        assert str(tmp_path) in tool_msg["content"]

        # system prompt 含导出规则
        assert "导出 Markdown 文件" in fake.calls[0]["messages"][0]["content"]

        # 持久化消息记录了工具调用
        messages = client.get(f"/api/chat/sessions/{session_id}/messages").json()
        assert messages[1]["tool_calls"][0]["function"]["name"] == "export_markdown"

    def test_export_dir_setting_falls_back_to_default(self, env, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "kate_cortex.skills.export.default_export_dir",
            lambda: str(tmp_path / "默认导出"),
        )
        client = make_client(env, export_dir=None)
        fake = FakeProvider(
            rounds=[
                [
                    ToolCallDelta(
                        index=0,
                        id="c1",
                        name="export_markdown",
                        arguments=json.dumps({"title": "a", "content_markdown": "b"}),
                    ),
                    Done("tool_calls"),
                ],
                [TextDelta("ok"), Done("stop")],
            ]
        )
        client.app.state.provider_factory = lambda name, model=None: fake

        session_id = client.post(
            "/api/chat/sessions", json={"provider": "deepseek"}
        ).json()["id"]
        client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "导出", "rag_enabled": False},
        )

        assert (tmp_path / "默认导出" / "a.md").exists()

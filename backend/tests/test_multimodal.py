"""多模态图片输入：附件落盘/解析 + 多模态对话流 + Anthropic 协议转换"""

import base64
import json

import pytest
from fastapi.testclient import TestClient

from kate_cortex.attachments import (
    AttachmentError,
    image_refs,
    save_data_urls,
    strip_images,
)
from kate_cortex.config import Config
from kate_cortex.main import create_app
from kate_cortex.providers import vision_supported
from kate_cortex.providers.anthropic_compat import to_anthropic_messages
from kate_cortex.providers.base import Done, TextDelta
from kate_cortex.providers.fake import FakeProvider

from test_chat_api import parse_sse

PNG_1PX = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture
def client(env):
    app = create_app(Config(vault_path=env.vault_path, db_path=env.db_path))
    test_client = TestClient(app)
    test_client.put(
        "/api/settings",
        json={"provider_keys": {"deepseek": "sk-test", "glm-coding": "sk-test"}},
    )
    return test_client


class TestSaveDataUrls:
    def test_saves_to_attachments_dir(self, tmp_path):
        rels = save_data_urls(tmp_path, [PNG_1PX])

        assert len(rels) == 1
        assert rels[0].startswith("attachments/")
        assert (tmp_path / rels[0]).is_file()

    def test_rejects_unsupported_type(self, tmp_path):
        with pytest.raises(AttachmentError):
            save_data_urls(tmp_path, ["data:image/bmp;base64,AAAA"])

    def test_rejects_non_data_url(self, tmp_path):
        with pytest.raises(AttachmentError):
            save_data_urls(tmp_path, ["https://example.com/a.png"])

    def test_rejects_bad_base64(self, tmp_path):
        with pytest.raises(AttachmentError):
            save_data_urls(tmp_path, ["data:image/png;base64,!!not-base64!!"])

    def test_rejects_oversize(self, tmp_path):
        big = "data:image/png;base64," + base64.b64encode(b"x" * (5 * 1024 * 1024 + 1)).decode()
        with pytest.raises(AttachmentError):
            save_data_urls(tmp_path, [big])


class TestImageRefParsing:
    def test_image_refs_and_strip(self):
        content = "看这张图\n\n![图片](attachments/2026/09/a.png)\n\n还有 [链接](attachments/2026/09/b.png)"

        assert image_refs(content) == ["attachments/2026/09/a.png"]
        stripped = strip_images(content)
        assert "![图片]" not in stripped  # 图片引用被替换
        assert "[图片]" in stripped
        assert "[链接](attachments/2026/09/b.png)" in stripped  # 普通链接不受影响

    def test_plain_content_untouched(self):
        assert strip_images("普通文本 [[some-slug]]") == "普通文本 [[some-slug]]"
        assert image_refs("普通文本") == []


class TestVisionSupport:
    def test_glm_coding_always_vision(self):
        assert vision_supported("glm-coding", "glm-5.3") is True

    def test_deepseek_never(self):
        assert vision_supported("deepseek", "deepseek-chat") is False

    def test_glm_by_model_name(self):
        assert vision_supported("glm", "glm-4v-flash") is True
        assert vision_supported("glm", "glm-4.5v") is True
        assert vision_supported("glm", "glm-4-flash") is False

    def test_open_source_providers_by_model_name(self):
        assert vision_supported("siliconflow", "Qwen/Qwen3-8B") is False


class TestAnthropicImageBlocks:
    def test_image_url_part_converted(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "这张图是什么"},
                    {"type": "image_url", "image_url": {"url": PNG_1PX}},
                ],
            }
        ]

        _, converted = to_anthropic_messages(messages)

        blocks = converted[0]["content"]
        assert blocks[0] == {"type": "text", "text": "这张图是什么"}
        image = blocks[1]
        assert image["type"] == "image"
        assert image["source"]["type"] == "base64"
        assert image["source"]["media_type"] == "image/png"
        assert image["source"]["data"] == PNG_1PX.split("base64,", 1)[1]

    def test_plain_user_content_unchanged(self):
        _, converted = to_anthropic_messages([{"role": "user", "content": "你好"}])
        assert converted[0]["content"] == [{"type": "text", "text": "你好"}]

    def test_unresolvable_image_skipped(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "https://x/y.png"}},
                    {"type": "text", "text": "描述"},
                ],
            }
        ]
        _, converted = to_anthropic_messages(messages)
        assert converted[0]["content"] == [{"type": "text", "text": "描述"}]


class TestMultimodalChatApi:
    def start_vision_session(self, client) -> str:
        return client.post(
            "/api/chat/sessions", json={"provider": "glm-coding", "model": "glm-5.3"}
        ).json()["id"]

    def test_rejects_images_on_text_model(self, client):
        session = client.post(
            "/api/chat/sessions", json={"provider": "deepseek"}
        ).json()

        resp = client.post(
            f"/api/chat/sessions/{session['id']}/chat",
            json={"content": "这是什么", "images": [PNG_1PX]},
        )

        assert resp.status_code == 400
        assert "不支持图片" in resp.json()["detail"]

    def test_rejects_empty_message(self, client):
        session_id = self.start_vision_session(client)
        resp = client.post(f"/api/chat/sessions/{session_id}/chat", json={})
        assert resp.status_code == 422

    def test_image_message_flow(self, client, env):
        session_id = self.start_vision_session(client)
        captured: list[list[dict]] = []

        class CapturingProvider(FakeProvider):
            def chat_stream(self, messages, tools=None):
                captured.append(messages)
                return super().chat_stream(messages, tools)

        client.app.state.provider_factory = lambda name, model=None: CapturingProvider(
            [[TextDelta("这是截图里的报错。"), Done("stop")]]
        )

        resp = client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "这报错什么意思", "images": [PNG_1PX]},
        )
        assert resp.status_code == 200
        events = parse_sse(resp.text)
        assert [name for name, _ in events][-1] == "done"

        # 落库消息带 markdown 引用，附件文件存在
        messages = client.get(f"/api/chat/sessions/{session_id}/messages").json()
        user_msg = next(m for m in messages if m["role"] == "user")
        refs = image_refs(user_msg["content"])
        assert len(refs) == 1
        assert (env.vault_path / refs[0]).is_file()

        # provider 收到多模态分块：text + image_url(data URL)
        sent_user = next(m for m in captured[0] if m["role"] == "user")
        assert isinstance(sent_user["content"], list)
        types = [p["type"] for p in sent_user["content"]]
        assert types == ["text", "image_url"]
        assert sent_user["content"][1]["image_url"]["url"].startswith("data:image/png;base64,")

        # 附件静态服务可访问
        static = client.get(f"/api/attachments/{refs[0]}")
        assert static.status_code == 200
        assert static.headers["content-type"].startswith("image/png")

    def test_history_replays_images_for_vision_model(self, client, env):
        session_id = self.start_vision_session(client)
        captured: list[list[dict]] = []

        class CapturingProvider(FakeProvider):
            def chat_stream(self, messages, tools=None):
                captured.append(messages)
                return super().chat_stream(messages, tools)

        client.app.state.provider_factory = lambda name, model=None: CapturingProvider(
            [[TextDelta("好的。"), Done("stop")]]
        )

        client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "第一张图", "images": [PNG_1PX]},
        )
        client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "再看看"},
        )

        # 第二轮历史里，带图消息仍展开为分块
        sent_users = [m for m in captured[1] if m["role"] == "user"]
        first = sent_users[0]
        assert isinstance(first["content"], list)
        assert any(p["type"] == "image_url" for p in first["content"])

    def test_history_strips_images_for_text_model(self, client):
        # glm（无 v 段模型）收到带图历史时只有占位文本
        session_id = self.start_vision_session(client)
        captured: list[list[dict]] = []

        class CapturingProvider(FakeProvider):
            def chat_stream(self, messages, tools=None):
                captured.append(messages)
                return super().chat_stream(messages, tools)

        client.app.state.provider_factory = lambda name, model=None: CapturingProvider(
            [[TextDelta("好的。"), Done("stop")]]
        )
        client.post(
            f"/api/chat/sessions/{session_id}/chat",
            json={"content": "图", "images": [PNG_1PX]},
        )

        # 用文本模型新会话直接构造：借 _history_messages 的降级分支
        from kate_cortex.routes.chat import _history_messages

        history = _history_messages(
            client.app.state.chat_service, session_id, client.app.state.storage.vault, False
        )
        assert all(isinstance(m["content"], str) for m in history)
        assert "[图片]" in history[0]["content"]

    def test_attachment_route_blocks_traversal(self, client):
        resp = client.get("/api/attachments/..%2F..%2Findex.sqlite")
        assert resp.status_code == 404

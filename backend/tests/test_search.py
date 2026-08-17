from kate_cortex.search import Search


class TestTokenize:
    def test_tokenizes_chinese_with_jieba(self):
        search = Search(None)
        tokens = search.tokenize("数据库连接池的配置方法").split()
        assert tokens == ["数据库", "连接池", "的", "配置", "方法"]


class TestQuery:
    def test_matches_chinese_keyword(self, tmp_path):
        from kate_cortex import db as db_mod

        database = db_mod.connect(tmp_path / "i.sqlite")
        search = Search(database.conn)
        search.index_entry("e1", "Redis 事务模式踩坑", "pipeline 事务模式下不返回结果。", ["redis"])

        hits = search.query("事务模式")

        assert [hit.entry_id for hit in hits] == ["e1"]

    def test_multiple_terms_are_and_combined(self, tmp_path):
        from kate_cortex import db as db_mod

        database = db_mod.connect(tmp_path / "i.sqlite")
        search = Search(database.conn)
        search.index_entry("e1", "Redis 踩坑", "pipeline 事务模式不返回。", [])
        search.index_entry("e2", "MySQL 踩坑", "连接池耗尽问题。", [])

        hits = search.query("事务 pipeline")

        assert [hit.entry_id for hit in hits] == ["e1"]

    def test_matches_title_and_tags(self, tmp_path):
        from kate_cortex import db as db_mod

        database = db_mod.connect(tmp_path / "i.sqlite")
        search = Search(database.conn)
        search.index_entry("e1", "连接池调优", "正文没这个词组。", ["性能"])

        assert search.query("调优")[0].entry_id == "e1"
        assert search.query("性能")[0].entry_id == "e1"

    def test_no_match_returns_empty(self, tmp_path):
        from kate_cortex import db as db_mod

        database = db_mod.connect(tmp_path / "i.sqlite")
        search = Search(database.conn)
        search.index_entry("e1", "标题", "内容", [])

        assert search.query("完全无关的词") == []

    def test_remove_entry_drops_from_index(self, tmp_path):
        from kate_cortex import db as db_mod

        database = db_mod.connect(tmp_path / "i.sqlite")
        search = Search(database.conn)
        search.index_entry("e1", "连接池", "内容", [])
        search.remove_entry("e1")

        assert search.query("连接池") == []

    def test_reindex_entry_replaces_content(self, tmp_path):
        from kate_cortex import db as db_mod

        database = db_mod.connect(tmp_path / "i.sqlite")
        search = Search(database.conn)
        search.index_entry("e1", "旧标题", "旧内容", [])
        search.index_entry("e1", "新标题", "新内容", [])

        assert search.query("旧标题") == []
        assert search.query("新标题")[0].entry_id == "e1"

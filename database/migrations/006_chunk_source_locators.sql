ALTER TABLE document_chunks
ADD COLUMN IF NOT EXISTS source_locators JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN document_chunks.source_locators IS
'统一来源定位集合，可保存页码与 bbox、幻灯片与 shape、Word 段落、字符区间、表格位置或时间范围';

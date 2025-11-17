# Symbol Resolver 增强功能总结

## 概述

本次增强为 `SymbolResolver` 添加了智能列名消歧义功能，支持置信度计算、详细的错误消息和特殊情况处理。

## 新增功能

### 1. 增强的列名解析算法 (`resolve_column_with_inference`)

- **显式表前缀（Priority 1）**：如果提供了表限定符，直接在作用域中查找并返回，置信度 0.95-1.0
- **无表前缀（Priority 2）**：
  - 单表：自动使用该表，置信度 1.0
  - 多表 + Schema：使用 schema 查找匹配的表
    - 唯一匹配：置信度 1.0
    - 多匹配：根据 `on_ambiguity` 配置处理
    - 无匹配：根据 `schema_validation` 配置处理
  - 多表 + 无 Schema：根据 `on_ambiguity` 配置处理

### 2. 错误消息构建 (`_build_error_message`)

- 提供详细的错误消息，包含：
  - SQL 上下文
  - 可能的源表
  - 修正建议（如何使用表前缀）
  - 列名高亮

### 3. 表解析顺序 (`_get_table_resolution_order`)

- 返回表在 FROM 子句中的出现顺序
- 用于处理歧义时的优先级判断

### 4. 置信度计算 (`_calculate_confidence`)

- 根据解析方法和上下文计算置信度（0.0-1.0）
- 规则：
  - 显式前缀 + Schema 验证：1.0
  - 显式前缀 + 无 Schema：0.95
  - 单表自动推断：1.0
  - Schema 唯一匹配：1.0
  - 无 Schema 多表：0.5-0.8（取决于歧义）
  - Schema 无匹配：0.3

### 5. 特殊情况处理

#### `resolve_star_column`
- 处理 `SELECT *` 和 `SELECT table.*`
- 需要 schema 信息来展开
- 支持多表时的列去重

#### `handle_using_clause`
- 处理 `JOIN ... USING (col1, col2)` 语法
- 记录列来自多个表（多对一依赖）
- 左表置信度 1.0，右表置信度 0.8

### 6. 增强的警告系统

#### `add_ambiguity_warning`
- 记录列名歧义警告
- 包含所有可能的表和最终选择的表

#### `add_schema_missing_warning`
- 记录 schema 中找不到列的警告
- 包含列名和表名

#### `add_inference_warning`
- 记录列来源推断的警告
- 包含置信度信息

#### `get_summary`
- 获取警告统计信息
- 按级别（INFO/WARNING/ERROR）分组

## 测试覆盖

新增测试文件 `tests/test_symbol_resolver_advanced.py`，包含 19 个测试用例：

1. ✅ 显式表前缀解析
2. ✅ 单表无前缀自动推断
3. ✅ 歧义列 + 严格模式
4. ✅ 歧义列 + 警告模式
5. ✅ 有 Schema 时歧义解决
6. ✅ Schema 验证开启时的列不存在错误
7. ✅ Schema 验证关闭时的列不存在警告
8. ✅ `SELECT *` 有 Schema
9. ✅ `SELECT *` 无 Schema（expand_wildcards=True）
10. ✅ `SELECT *` 无 Schema（expand_wildcards=False）
11. ✅ `SELECT table.*` 语法
12. ✅ `JOIN ... USING` 语法
13. ✅ 错误消息质量
14. ✅ 无效表限定符
15. ✅ 置信度级别
16. ✅ 混合有前缀/无前缀列
17. ✅ 警告收集器方法
18. ✅ 表解析顺序
19. ✅ 置信度计算

## 集成点

### ExpressionVisitor
- `visit_Column` 方法使用 `resolve_column_with_inference`
- 传递 SQL 上下文以提供更好的错误消息

### DependencyExtractor
- 新增 `_extract_source_columns_with_confidence` 方法
- 提取源列及其置信度
- 将置信度传递给 `ColumnDependency` 对象

## 使用示例

```python
from lineage_analyzer import LineageAnalyzer, DictSchemaProvider, LineageConfig, ErrorMode

# 基本用法
analyzer = LineageAnalyzer()
result = analyzer.analyze("SELECT amount + tax AS total FROM orders")
print(f"Confidence: {result.dependencies[0].confidence}")

# 带 Schema 验证
schema = {"orders": ["id", "amount", "tax"], "customers": ["id", "name"]}
analyzer = LineageAnalyzer(schema_provider=DictSchemaProvider(schema))
result = analyzer.analyze("SELECT id FROM orders o JOIN customers c ON o.cid = c.id")
# 自动推断 id 来自 orders（因为只有 orders 有 id）

# 歧义处理
config = LineageConfig(on_ambiguity=ErrorMode.WARN)
analyzer = LineageAnalyzer(config=config)
result = analyzer.analyze("SELECT id FROM orders o JOIN customers c ON o.cid = c.id")
# 使用第一个表，记录警告，置信度 0.6

# SELECT * 支持
schema = {"orders": ["id", "amount", "tax"]}
analyzer = LineageAnalyzer(schema_provider=DictSchemaProvider(schema))
result = analyzer.analyze("SELECT * FROM orders")
# 展开为 3 个依赖关系
```

## 验收标准

- ✅ 所有测试用例通过（19/19）
- ✅ 错误消息清晰、可操作
- ✅ 警告系统正确记录所有推断和歧义情况
- ✅ 置信度计算准确反映解析的确定性
- ✅ 支持 `SELECT *`（在有 schema 时）
- ✅ 代码有完整的类型注解和 docstring
- ✅ 所有现有测试通过（82/82）

## 后续改进建议

1. **性能优化**：缓存 schema 查询结果
2. **更多特殊情况**：支持 CTE、子查询
3. **更智能的推断**：基于列名模式（如 `id` 通常来自主表）
4. **置信度细化**：根据更多上下文信息调整置信度
5. **错误恢复**：在解析失败时提供部分结果


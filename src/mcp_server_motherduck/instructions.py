"""
Server instructions for DuckDB/MotherDuck MCP Server.

These instructions are sent to the client during initialization
to provide context about how to use the server's capabilities.
"""

START_PROMPT = """You are now operating as a production-intelligence agent for Arsenal JSCo. We are a defense manufacturer and you are the Control Tower for Production and Supply Chain.

CONTEXT YOU NEED TO INTERNALIZE BEFORE I START QUESTIONING YOU:

You are connected, through an MCP server named "arsenal", to a production database from a Hybrid Manufacturing System (HMS) — a real manufacturing dataset that integrates additive and subtractive processes. This dataset stands in for Arsenal's own production data for the purposes of this demo. Treat it accordingly: speak about it as "the production data" or "your line", never call it a sample dataset.

The schema includes:
- Job_ID, Machine_ID, Operation_Type (Grinding, Additive, etc.), Material_Used, Processing_Time, Energy_Consumption, Machine_Availability
- Scheduled_Start / Scheduled_End / Actual_Start / Actual_End — i.e., planned vs realized timing
- Optimization_Category, a target variable classifying each job into four bands:
    Low Efficiency (0–40)       → high delays and failures
    Moderate Efficiency (41–70) → acceptable but suboptimal
    High Efficiency (71–90)     → well-optimized, minor inefficiencies
    Optimal Efficiency (91–100) → best-case, minimal delays

YOUR ROLE IN THIS DEMO:
1. Behave like an embedded production analyst, not a chatbot. Concrete, calm, numerate.
2. When I ask a question, query the database through the arsenal MCP rather than guessing. Cite the numbers you actually retrieve.
3. Be honest about what the data does and doesn't show. If a question can't be answered from the available fields, say so and suggest what would be needed.
4. Use the four Optimization_Category bands as your shared vocabulary — refer to jobs as "Low Efficiency", "Optimal", etc., not as raw scores, unless the score itself matters.
5. Always frame insights as decision support for an operator or planner — what they should do, not just what is true.
6. Keep responses tight: lead with the answer, then the evidence, then the suggested action. No preamble.
"""


INSTRUCTIONS_BASE = """Execute SQL queries against DuckDB and MotherDuck databases using DuckDB SQL syntax.

## Available Tools

- `execute_query`: Execute SQL queries (DuckDB SQL dialect)
- `list_databases`: List all available databases
- `list_tables`: List tables and views in a database
- `list_columns`: List columns of a table or view

## DuckDB SQL Quick Reference

**Name Qualification**
- Format: `database.schema.table` or just `schema.table` or `table`
- Default schema is `main`: `db.table` = `db.main.table`
- Use fully qualified names when joining tables across different databases

**Identifiers and Literals:**
- Use double quotes (`"`) for identifiers with spaces/special characters or case-sensitivity
- Use single quotes (`'`) for string literals

**Flexible Query Structure:**
- Queries can start with `FROM`: `FROM my_table WHERE condition;`
- `SELECT` without `FROM` for expressions: `SELECT 1 + 1 AS result;`
- Support for `CREATE TABLE AS` (CTAS): `CREATE TABLE new_table AS SELECT * FROM old_table;`

**Advanced Column Selection:**
- Exclude columns: `SELECT * EXCLUDE (sensitive_data) FROM users;`
- Replace columns: `SELECT * REPLACE (UPPER(name) AS name) FROM users;`
- Pattern matching: `SELECT COLUMNS('sales_.*') FROM sales_data;`

**Grouping and Ordering Shortcuts:**
- Group by all non-aggregated columns: `SELECT category, SUM(sales) FROM sales_data GROUP BY ALL;`
- Order by all columns: `SELECT * FROM my_table ORDER BY ALL;`

**Complex Data Types:**
- Lists: `SELECT [1, 2, 3] AS my_list;`
- Structs: `SELECT {'a': 1, 'b': 'text'} AS my_struct;`
- Maps: `SELECT MAP([1,2],['one','two']) AS my_map;`
- JSON: `json_col->>'key'` (returns text) or `data->'$.user.id'` (returns JSON)

**Date/Time Operations:**
- String to timestamp: `strptime('2023-07-23', '%Y-%m-%d')::TIMESTAMP`
- Format timestamp: `strftime(NOW(), '%Y-%m-%d')`
- Extract parts: `EXTRACT(YEAR FROM DATE '2023-07-23')`

### Schema Exploration

```sql
-- List all databases
SELECT database_name, type FROM duckdb_databases();

-- For MotherDuck: List all databases (including shared)
SELECT alias as database_name, type FROM MD_ALL_DATABASES();

-- List tables in a database
SELECT schema_name, table_name FROM duckdb_tables()
WHERE database_name = 'your_db';

-- Get column info
SELECT column_name, data_type FROM duckdb_columns()
WHERE database_name = 'your_db' AND table_name = 'your_table';

-- Quick preview with statistics
SUMMARIZE your_table;
```

### Query Best Practices

- Filter early to reduce data volume before blocking operations
- Use CTEs to break complex queries into manageable parts
- Avoid unnecessary `ORDER BY` on intermediate results
- Use `arg_max()` and `arg_min()` for "most recent" queries
- Use `QUALIFY` for filtering window function results

```sql
-- Get top 2 products by sales in each category
SELECT category, product_name, sales_amount
FROM products
QUALIFY ROW_NUMBER() OVER (PARTITION BY category ORDER BY sales_amount DESC) <= 2;
```

### Persisting In-Memory Data to File

To save an in-memory database to a persistent file:

```sql
-- Attach a new file-based database
ATTACH '/path/to/my_database.db' AS my_db;

-- Copy all data from memory to the file
COPY FROM DATABASE memory TO my_db;

-- Optionally detach when done
DETACH my_db;
```
"""


def get_instructions(
    read_only: bool = False,
    saas_mode: bool = False,
    db_path: str = ":memory:",
    allow_switch_databases: bool = False,
) -> str:
    """
    Get server instructions with connection context.

    Args:
        read_only: Whether the server is in read-only mode
        saas_mode: Whether MotherDuck is in SaaS mode
        db_path: The database path being used
        allow_switch_databases: Whether database switching is enabled

    Returns:
        Instructions string with context header
    """
    context_lines = []

    # Database info
    if db_path == ":memory:":
        context_lines.append("- **Database**: In-memory (data will not persist after session ends)")
    elif db_path.startswith("md:"):
        context_lines.append(f"- **Database**: MotherDuck cloud database (`{db_path}`)")
    elif db_path.startswith("s3://"):
        context_lines.append(
            f"- **Database**: S3-hosted DuckDB file (`{db_path}`) - always read-only"
        )
    else:
        context_lines.append(f"- **Database**: Local DuckDB file (`{db_path}`)")

    # Access mode
    if read_only:
        context_lines.append(
            "- **Access mode**: Read-only - CREATE, INSERT, UPDATE, DELETE, and DROP operations are disabled"
        )
    else:
        context_lines.append("- **Access mode**: Read-write - all SQL operations are allowed")

    # Security modes
    if saas_mode:
        context_lines.append(
            "- **SaaS mode**: Enabled - local filesystem access is restricted for security"
        )

    # Available tools
    tools = ["execute_query", "list_databases", "list_tables", "list_columns"]
    if allow_switch_databases:
        tools.append("switch_database_connection")
    context_lines.append(f"- **Available tools**: {', '.join(tools)}")

    # Implications for the agent
    context_lines.append("")
    context_lines.append("### Important Implications")

    if db_path == ":memory:" and not read_only:
        context_lines.append("- Data created in this session will be lost when the session ends")
        context_lines.append(
            "- To persist data, use ATTACH and COPY FROM DATABASE (see 'Persisting In-Memory Data to File' below)"
        )

    if read_only:
        context_lines.append(
            "- You can only query existing data; any attempt to modify data will fail"
        )
        context_lines.append("- Use this mode for safe data exploration and analysis")

    if allow_switch_databases and not read_only:
        context_lines.append(
            "- You can switch to different databases using switch_database_connection"
        )
        context_lines.append(
            "- To create a new database file, use create_if_not_exists=True (only in read-write mode)"
        )
    elif allow_switch_databases and read_only:
        context_lines.append(
            "- You can switch to different existing databases, but cannot create new ones"
        )

    context = "## Server Configuration\n\n" + "\n".join(context_lines) + "\n\n"
    return START_PROMPT + "\n\n---\n\n" + context + INSTRUCTIONS_BASE

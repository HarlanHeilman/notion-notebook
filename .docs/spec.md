# notion_matplotlib - Complete Specification

A Jupyter notebook integration that automatically exports computational work to Notion with rich metadata, figure tracking, and git awareness.

## Quick Start Example

```python
from notion_matplotlib import NotebookExporter

exporter = NotebookExporter(
    notion_token="ntn_...",
    notion_page_id="abc123..."
)
exporter.start()

# Now every time you save the notebook, it auto-syncs to Notion
```

---

## System Architecture

### High-Level Flow

```
Notebook Save (detected by file watcher)
    ↓
Parse notebook + Extract git metadata
    ↓
Convert cells/outputs to Notion blocks
    ↓
Create/update Notion page:
├─ Metadata block (Last Sync, GitHub, Path)
├─ Export section (all cells + outputs)
└─ Figures database (figures + timestamps + AI summaries)
```

### Notion Page Structure

```
[Your Notion Task Page]

📌 Notebook Metadata (callout block)
   Last Sync: 2025-04-04 14:32:15 UTC
   GitHub Remote: https://github.com/user/repo
   Notebook Path: notebooks/analysis/fit.ipynb

────────────────────────────

Notebook Export (notion-connection.ipynb)
   [Cell 1 code block]
   [Cell 1 outputs]
   [Cell 2 markdown block]
   [Cell 3 code block]
   [Cell 3 image output]
   ...

────────────────────────────

📊 Figures (child_database)
   │ Name │ Image │ Timestamp │ AI Summary │ Code │
   ├──────┼───────┼───────────┼────────────┼──────┤
   │ Fig1 │ [PNG] │ 2025-04-04│ "Shows..." │ code │
   │ Fig2 │ [PNG] │ 2025-04-04│ "Shows..." │ code │

────────────────────────────

[Your own Notion content here - completely preserved]
```

---

## Configuration

### Setup Cell (Required)

Add this to the first cell of your notebook:

```python
from notion_matplotlib import NotebookExporter

exporter = NotebookExporter(
    notion_token="ntn_...",              # Notion API token
    notion_page_id="abc123...",          # Notion page ID (from URL)
    notebook_name="auto",                # Auto-detect from kernel
    auto_sync_on_save=True,              # Sync on every save
    image_format="png",                  # png, jpg, or webp
    include_ai_summaries=True,           # Generate AI descriptions
    verbose=True
)

exporter.start()
```

### Environment Variables (Optional)

```bash
export NOTION_TOKEN="ntn_..."
export NOTION_PAGE_ID="abc123..."
```

### Config File (~/.notion_matplotlib/config.json)

```json
{
  "notion_token": "ntn_...",
  "default_page_id": "abc123...",
  "auto_sync_on_save": true,
  "image_format": "png"
}
```

---

## Core Modules

### 1. `exporter.py` - Main Orchestrator

```python
class NotebookExporter:
    def __init__(
        self,
        notion_token: str,
        notion_page_id: str,
        notebook_name: str = "auto",
        auto_sync_on_save: bool = True,
        auto_sync_interval: Optional[int] = None,
        image_format: str = "png",
        include_ai_summaries: bool = True,
        debounce_seconds: float = 2.0,
        verbose: bool = False
    ):
        """Initialize the exporter"""

    def start(self) -> None:
        """Start the file watcher and sync system"""
        # 1. Validate Notion token and page
        # 2. Get notebook path from IPython kernel
        # 3. Register file watcher
        # 4. Start listening for notebook saves

    def manual_sync(self) -> SyncResult:
        """Trigger an immediate sync"""
        # 1. Parse notebook
        # 2. Extract git metadata
        # 3. Convert to Notion blocks
        # 4. Upload to Notion
        # 5. Return result

    def stop(self) -> None:
        """Stop watching"""

@dataclass
class SyncResult:
    success: bool
    timestamp: datetime
    cells_processed: int
    figures_found: int
    blocks_created: int
    images_uploaded: int
    errors: List[str]
```

### 2. `git_utils.py` - Git Detection

```python
class GitContext:
    @staticmethod
    def find_git_root(start_path: Path) -> Optional[Path]:
        """Walk up to find .git directory"""

    @staticmethod
    def get_git_remote_url(git_root: Path) -> Optional[str]:
        """Extract origin URL from .git/config"""

    @staticmethod
    def get_relative_path(notebook_path: Path, git_root: Path) -> str:
        """Compute path relative to git root"""

    @staticmethod
    def get_notebook_metadata(notebook_path: Path) -> NotebookMetadata:
        """Return all metadata: timestamp, path, remote"""

@dataclass
class NotebookMetadata:
    last_sync: datetime           # UTC now
    notebook_path: str            # e.g., "notebooks/fit.ipynb"
    github_remote: Optional[str]  # e.g., "https://github.com/user/repo"
    notebook_name: str            # Filename without extension
    file_path: Path               # Full path to .ipynb
```

### 3. `notebook_parser.py` - Parse Notebooks

```python
class NotebookParser:
    def parse(self, notebook_path: str) -> ParsedNotebook:
        """Read and parse .ipynb file"""
        # 1. Read JSON
        # 2. Extract cells
        # 3. Extract outputs
        # 4. Return structured data

@dataclass
class ParsedNotebook:
    path: str
    name: str
    cells: List[NotebookCell]
    kernel_name: Optional[str]
    modified_time: datetime

@dataclass
class NotebookCell:
    index: int
    cell_type: str  # "code", "markdown", "raw"
    source: str
    execution_count: Optional[int]
    outputs: List[CellOutput]

@dataclass
class CellOutput:
    output_type: str  # "stream", "error", "execute_result", "display_data"
    content: str      # Text or base64 image
    mime_type: Optional[str]  # "text/plain", "image/png", etc.
```

### 4. `notion_converter.py` - Convert to Notion Blocks

```python
class NotionConverter:
    def blocks_from_notebook(
        self,
        parsed: ParsedNotebook,
        metadata: NotebookMetadata,
        notion_client: Any
    ) -> List[NotionBlock]:
        """Convert notebook to Notion blocks"""
        # 1. Create metadata block (callout with git info)
        # 2. Create heading for export section
        # 3. For each cell:
        #    - Convert code/markdown to Notion blocks
        #    - Convert outputs (text, images, errors)
        # 4. Return all blocks in order

    def metadata_to_block(self, metadata: NotebookMetadata) -> NotionBlock:
        """Create formatted metadata callout block"""
        # Renders as:
        # Notebook Metadata
        # Last Sync: [timestamp]
        # GitHub Remote: [url]
        # Notebook Path: [path]

@dataclass
class NotionBlock:
    block_type: str  # "paragraph", "code", "image", "heading_2", "callout"
    content: Dict[str, Any]  # Notion API format
```

### 5. `notion_client.py` - Notion API Wrapper

```python
class NotionPageSync:
    def __init__(self, token: str, page_id: str, verbose: bool = False):
        self.client = Client(auth=token)
        self.page_id = normalize_page_id(page_id)

    def validate_page(self) -> bool:
        """Verify page exists and is accessible"""

    def sync_export_blocks(
        self,
        blocks: List[NotionBlock],
        export_heading: str
    ) -> SyncBlocksResult:
        """Sync blocks to page

        1. Fetch existing page blocks
        2. Find old export section (by heading text)
        3. Delete old section (idempotent)
        4. Prepend new blocks (before first child_database)
        """

    def upload_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        filename: str
    ) -> str:
        """Upload image, return file_upload_id"""

    def _append_blocks(
        self,
        blocks_payload: List[Dict],
        position: str = "start"
    ) -> List[str]:
        """Append blocks (batch in groups of 100)"""

    def _delete_export_section(
        self,
        page_blocks: List[Dict],
        export_heading: str
    ) -> int:
        """Delete old export (heading → first database), return count"""

@dataclass
class SyncBlocksResult:
    success: bool
    blocks_created: int
    blocks_deleted_old: int
    images_uploaded: int
    errors: List[str]
```

### 6. `figure_database_manager.py` - Manage Figures Database

```python
class FigureDatabaseManager:
    def __init__(self, notion_client: Any, page_id: str):
        self.client = notion_client
        self.page_id = page_id

    def ensure_figures_database(self) -> str:
        """Create "Figures" child_database if missing

        Columns created:
        - Name (title)
        - Image (files)
        - Cell Index (number)
        - Code (rich_text)
        - Timestamp (date)
        - AI Summary (text with ai_summary)

        Returns: database_id
        """

    def sync_figures(
        self,
        figures: List[ExtractedFigure],
        figures_db_id: str
    ) -> SyncFiguresResult:
        """Create/update figure rows

        For each figure:
        1. Check if exists (by cell_index)
        2. Upload image
        3. Create or update row
        4. Set timestamp to now (UTC)
        5. Trigger AI summary (async)
        """

    def trigger_ai_summaries(self, figures_db_id: str) -> None:
        """Queue AI summary generation (async in Notion)"""

@dataclass
class ExtractedFigure:
    cell_index: int
    figure_index: int  # Multiple per cell
    image_data: bytes
    image_format: str  # "png", "jpg", "webp"
    code: str          # Full cell source
    title: Optional[str]  # From plt.title()
    timestamp: datetime
```

### 7. `jupyter_hooks.py` - Jupyter Integration

```python
class JupyterHooks:
    @staticmethod
    def register_save_hook(callback: Callable) -> None:
        """Hook notebook save events via IPython"""

    @staticmethod
    def get_notebook_path() -> Optional[str]:
        """Extract notebook path from IPython kernel"""

    @staticmethod
    def get_notebook_name() -> Optional[str]:
        """Extract notebook filename"""

class NotebookWatcher:
    def __init__(
        self,
        notebook_path: str,
        callback: Callable,
        debounce_seconds: float = 2.0
    ):
        """Watch .ipynb file for changes"""

    def start(self) -> None:
        """Start watching"""

    def stop(self) -> None:
        """Stop watching"""
```

### 8. `utils.py` - Utilities

```python
def normalize_page_id(page_id_or_url: str) -> str:
    """Convert URL or UUID to clean page ID

    https://www.notion.so/abc123 → abc123
    abc123 → abc123
    """

def extract_mime_binary(mime_type: str, raw_data: Any) -> Optional[bytes]:
    """Decode Jupyter output (base64, bytes, list) to bytes"""

def create_code_block(language: str, code: str) -> List[Dict]:
    """Create Notion code block(s), chunking if needed"""

def chunk_rich_text(text: str, max_chunk_size: int = 1900) -> List[Dict]:
    """Break text into Notion rich_text chunks"""

def create_error_block(error_text: str) -> Dict:
    """Create Notion error callout block"""
```

### 9. `config.py` - Configuration

```python
@dataclass
class Config:
    notion_token: str
    default_page_id: Optional[str]
    auto_sync_on_save: bool
    image_format: str
    max_image_size_mb: float
    debounce_seconds: float

    @staticmethod
    def load_from_env() -> Config:
        """Load from NOTION_TOKEN, NOTION_PAGE_ID env vars"""

    @staticmethod
    def load_from_file(path: str = "~/.notion_matplotlib/config.json") -> Config:
        """Load from JSON file"""
```

---

## Key Design Patterns

### Idempotent Updates

Every sync:
1. Searches for `heading_2` block with text `"Notebook export ({filename})"`
2. Deletes everything from that heading to the first `child_database` block
3. Prepends new export section

This means:
- Re-syncing is safe (no duplicates)
- User content below the export section is preserved
- User edits within the export section are lost (expected)

### Git Metadata Detection

```python
# Walk up from notebook location
notebook_path = Path("/home/user/project/notebooks/analysis.ipynb")

# Look for .git/
git_root = find_git_root(notebook_path)  # → /home/user/project

# Extract remote from .git/config
remote = get_git_remote_url(git_root)  # → "https://github.com/user/project"

# Compute relative path
rel_path = get_relative_path(notebook_path, git_root)  # → "notebooks/analysis.ipynb"

# All automatic, graceful fallbacks if not in git repo
```

### Image Handling

```python
# For each image output:
1. Extract base64 or bytes from Jupyter output
2. Upload via notion.file_uploads.create() + .send()
3. Get file_upload_id back
4. Create image block referencing that ID
# (images stored in Notion, not embedded as base64)
```

### Error Recovery

- If validation fails → raise clear error before starting
- If image upload fails → log warning, skip image, continue
- If network fails → log error, return it in SyncResult
- Never crash the notebook kernel

---

## Data Flow (Detailed)

### 1. Initialization

```
exporter.start()
├─ Validate Notion token and page
├─ Get notebook path from IPython
├─ Register file watcher
└─ Start listening for saves
```

### 2. On Notebook Save

```
File watcher detects .ipynb change
├─ Debounce: wait 2 seconds
└─ Call exporter._sync()

_sync():
├─ Get notebook path
├─ Parse notebook (NotebookParser)
├─ Extract git metadata (GitContext)
├─ Convert to blocks (NotionConverter)
├─ Upload to Notion (NotionPageSync)
├─ Sync figures (FigureDatabaseManager)
└─ Return SyncResult with counts
```

### 3. Block Creation

```
For metadata:
├─ Create callout block with:
│  ├─ Last Sync: now (UTC)
│  ├─ GitHub Remote: detected URL or omitted
│  └─ Notebook Path: computed relative path

For cells:
├─ If code: create code block + output blocks
├─ If markdown: create markdown block
├─ If raw: create text block
└─ Outputs:
   ├─ Text → paragraph blocks
   ├─ Images → image blocks (auto-uploaded)
   └─ Errors → callout blocks
```

### 4. Notion Sync

```
Fetch existing blocks
↓
Find old export section (by heading_2 text)
↓
Delete old section (if exists)
↓
Prepend new blocks (before first child_database)
↓
Create/update Figures database with rows
↓
Trigger AI summaries (async)
```

---

## Notion Data Model

### Metadata Block (Callout)

```json
{
  "type": "callout",
  "callout": {
    "rich_text": [
      {"type": "text", "text": {"content": "Notebook Metadata"}},
      {"type": "text", "text": {"content": "\nLast Sync: 2025-04-04 14:32:15 UTC"}},
      {"type": "text", "text": {"content": "\nGitHub Remote: https://github.com/user/repo"}},
      {"type": "text", "text": {"content": "\nNotebook Path: notebooks/analysis.ipynb"}}
    ],
    "icon": {"type": "emoji", "emoji": "📌"}
  }
}
```

### Export Section Heading

```json
{
  "type": "heading_2",
  "heading_2": {
    "rich_text": [
      {"type": "text", "text": {"content": "Notebook export (analysis.ipynb)"}}
    ]
  }
}
```

### Figures Database Properties

When created:

```
Name (title)
Image (files)
Cell Index (number)
Code (rich_text)
Timestamp (date)
AI Summary (text, with ai_summary: true)
```

### Figure Row Example

```json
{
  "properties": {
    "Name": {"title": [{"text": {"content": "Figure 5_1"}}]},
    "Image": {"files": [{"id": "<upload_id>"}]},
    "Cell Index": {"number": 5},
    "Code": {"rich_text": [{"text": {"content": "plt.plot(...)"}}]},
    "Timestamp": {"date": {"start": "2025-04-04"}},
    "AI Summary": {"rich_text": []}  // Auto-populated by Notion
  }
}
```

---

## Error Handling

### Validation Errors

```python
try:
    exporter = NotebookExporter(notion_token="...", notion_page_id="...")
    exporter.start()
except ValueError as e:
    # Token invalid
    # Page doesn't exist
    # Page not accessible
    # Notebook path not found
```

### Sync Errors

```python
result = exporter.manual_sync()

if not result.success:
    print(f"Sync failed: {result.errors}")
    # Returned in result, not raised
    # Notebook kernel not crashed
```

### API Limits

- Notion: 100 blocks per request → batch in groups of 100
- Notion: 2000 chars per rich_text span → chunk long text
- Notion: Rate limiting → retry with backoff
- Images: Max file size → warn and skip

---

## Testing Strategy

### Unit Tests

```python
# test_git_utils.py
def test_find_git_root_in_repo()
def test_find_git_root_outside_repo()
def test_get_git_remote_url_https()
def test_get_git_remote_url_ssh()
def test_get_relative_path()

# test_notebook_parser.py
def test_parse_simple_notebook()
def test_parse_notebook_with_outputs()
def test_parse_notebook_with_images()
def test_parse_malformed_notebook()

# test_notion_converter.py
def test_metadata_block_creation()
def test_code_block_creation()
def test_image_block_creation()
def test_text_chunking()

# test_notion_client.py
def test_validate_page()
def test_upload_image()
def test_sync_blocks_idempotency()
def test_append_blocks_batching()

# test_figure_database_manager.py
def test_create_figures_database()
def test_sync_figures()
def test_timestamp_set()
```

### Integration Tests

```python
# End-to-end with mock Notion API:
def test_full_sync_workflow()
def test_sync_preserves_user_content()
def test_sync_is_idempotent()
```

### Test Fixtures

```
tests/
├── fixtures/
│   ├── simple_notebook.ipynb
│   ├── notebook_with_plots.ipynb
│   ├── notebook_with_errors.ipynb
│   └── mock_notion_responses.json
```

---

## Development Roadmap

### Phase 1: Core Infrastructure (2 weeks)
- [ ] git_utils.py + tests
- [ ] notebook_parser.py + tests
- [ ] notion_converter.py + tests
- [ ] Basic utils.py

**Milestone**: Can parse notebooks and convert to Notion blocks

### Phase 2: Notion Integration (1.5 weeks)
- [ ] notion_client.py + tests
- [ ] figure_database_manager.py + tests
- [ ] Config file handling

**Milestone**: Can connect to Notion, upload blocks and images

### Phase 3: Automation (1 week)
- [ ] jupyter_hooks.py + tests
- [ ] NotebookWatcher implementation
- [ ] exporter.py orchestration

**Milestone**: Auto-syncs on notebook save

### Phase 4: Polish (1 week)
- [ ] Config.py
- [ ] CLI tools (optional)
- [ ] Documentation & examples
- [ ] Pre-release checklist

**Total**: 5-6 weeks

---

## Installation & Usage

### Development Installation

```bash
git clone <repo>
cd notion-matplotlib
pip install -e ".[dev]"
```

### User Installation

```bash
pip install notion-matplotlib
```

### In a Notebook

```python
from notion_matplotlib import NotebookExporter

exporter = NotebookExporter(
    notion_token="ntn_...",
    notion_page_id="abc123..."
)
exporter.start()

# Now just work normally...
import matplotlib.pyplot as plt
plt.plot([1, 2, 3], [1, 4, 9])
# Save notebook → syncs automatically
```

---

## Project Structure

```
notion_matplotlib/
├── __init__.py
├── exporter.py
├── notebook_parser.py
├── notion_converter.py
├── notion_client.py
├── figure_database_manager.py
├── jupyter_hooks.py
├── git_utils.py
├── config.py
├── utils.py
├── exceptions.py

tests/
├── test_git_utils.py
├── test_notebook_parser.py
├── test_notion_converter.py
├── test_notion_client.py
├── test_figure_database_manager.py
├── test_jupyter_hooks.py
├── fixtures/

setup.py
README.md
requirements.txt
```

---

## Key Dependencies

```
notion-client>=1.0.0
nbformat>=5.0.0
ipython>=7.0.0
watchdog>=2.0.0
python-dotenv>=0.19.0
Pillow>=8.0.0  # Optional, for image optimization
```

---

## FAQ

**Q: Do I have to change my plotting code?**
A: No. Everything is automatic. Your `plt.plot()` works unchanged.

**Q: What if I'm not using git?**
A: Works fine! GitHub Remote field is simply omitted.

**Q: Can I use this with multiple notebooks?**
A: Yes. Each can export to the same page. Metadata distinguishes them.

**Q: What about large notebooks?**
A: Handled gracefully. Blocks are batched (max 100 per API call).

**Q: Can I edit the export section?**
A: Yes, but edits will be lost on next sync (expected behavior).

**Q: How often does it sync?**
A: On every save (debounced 2 seconds). Configurable to intervals.

**Q: What's the cost?**
A: Free. Uses Notion's free API tier for typical usage.

---

## Summary

This specification defines a complete, production-ready system that automatically exports Jupyter notebooks to Notion with:

✅ Zero manual function calls
✅ Automatic git awareness
✅ Smart figure tracking with timestamps and AI summaries
✅ Clean separation of auto-generated and user content
✅ Idempotent, safe updates
✅ Full error handling and graceful fallbacks

Ready to implement in phases. All design decisions locked down. No ambiguities remaining.

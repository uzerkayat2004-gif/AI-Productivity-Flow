"""NotebookLM Video Flow provider package."""

from .config import resolve_notebooklm_cli, resolve_notebooklm_mcp, resolve_notebooklm_profile
from .keepalive import (
    NotebookLMKeepaliveService,
    get_keepalive_service,
    get_keepalive_status,
    start_keepalive_daemon,
    stop_keepalive_daemon,
    trigger_keepalive_now,
)
from .mcp_client import NotebookLMMcpClient
from .mcp_server import generate_mcp_config, get_mcp_server_info, resolve_mcp_binary
from .models import (
    DEFAULT_FORMAT,
    DEFAULT_PROFILE,
    DEFAULT_STYLE,
    VIDEO_FORMATS,
    VIDEO_STYLES,
    AuthStatus,
    NotebookLMVideoError,
    NotebookRef,
    SourceRef,
    VideoArtifact,
    VideoRequest,
)
from .document_profiler import (
    ContentClassification,
    ContentValueProfile,
    DocumentProfile,
    analyze_content_value,
    analyze_document_source,
    build_adaptive_prompt,
    build_chapter_breakdown,
    classify_document_content,
    compute_format_duration,
    extract_document_sections,
    generate_adaptive_directive,
    generate_cinematic_pacing_directive,
)
from .provenance import probe_media_file, write_notebooklm_provenance
from .provider import NotebookLMVideoProvider
from .service import NotebookLMService, get_notebooklm_service
from .browser_sync import (
    auto_sync_from_browser,
    discover_browser_profiles,
    import_cookies,
    sync_cookies_with_playwright,
)

__all__ = [
    "DEFAULT_FORMAT",
    "DEFAULT_PROFILE",
    "DEFAULT_STYLE",
    "ContentClassification",
    "ContentValueProfile",
    "DocumentProfile",
    "VIDEO_FORMATS",
    "VIDEO_STYLES",
    "AuthStatus",
    "NotebookLMKeepaliveService",
    "NotebookLMMcpClient",
    "NotebookLMService",
    "NotebookLMVideoError",
    "NotebookLMVideoProvider",
    "NotebookRef",
    "SourceRef",
    "VideoArtifact",
    "VideoRequest",
    "analyze_content_value",
    "analyze_document_source",
    "auto_sync_from_browser",
    "build_adaptive_prompt",
    "build_chapter_breakdown",
    "classify_document_content",
    "compute_format_duration",
    "discover_browser_profiles",
    "extract_document_sections",
    "generate_adaptive_directive",
    "generate_cinematic_pacing_directive",
    "generate_mcp_config",
    "get_keepalive_service",
    "get_keepalive_status",
    "get_mcp_server_info",
    "get_notebooklm_service",
    "import_cookies",
    "probe_media_file",
    "resolve_mcp_binary",
    "resolve_notebooklm_cli",
    "resolve_notebooklm_mcp",
    "resolve_notebooklm_profile",
    "start_keepalive_daemon",
    "stop_keepalive_daemon",
    "sync_cookies_with_playwright",
    "trigger_keepalive_now",
    "write_notebooklm_provenance",
]



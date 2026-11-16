# ── Git & GitHub ─────────────────────────────────────────────
HOST = 'https://github.com'
BASE_REPO_OWNER = 'Infineon'
MAIN_BRANCH = 'main'
GIT_DIR = '.git_deepcraft'
MINIMUM_UPDATABLE_GIT_VERSION = '2.16.2'  # update-git-for-windows option
MINIMUM_GIT_VERSION = '2.43'  # git show-ref --exists
# Split large pushes before hitting GitHub's ~2 GB / push soft limit and the
# ~3,000-file PR file list. Keep commits smaller so staging/push/PR create stay reliable.
GH_PUSH_MAX_BYTES = (2 * 1024 * 1024 * 1024) - 1
GH_PUSH_MAX_FILES = 2500

# ── Self-update ──────────────────────────────────────────────
# Public GitHub repository hosting this tool; used to fetch newer versions.
TOOL_REPO = 'Infineon/deepcraft-studio-accelerators-pr-tool'

# Use in terminal output (print). README files use HTML ``&trade;`` instead.
DEEPCRAFT = 'DEEPCRAFT\u2122'
PSOC = 'PSOC\u2122'
AURIX = 'AURIX\u2122'
# Product words in a target label that the project summary shows in green.
TARGET_HIGHLIGHT_WORDS = (PSOC, AURIX, 'Accelerators')

# ── Target Repositories ─────────────────────────────────────────
from target_repo import ContentCategory, TargetRepo

# DEEPCRAFT AI Hub cards live at <category>/<card>/metadata.json.
# The upstream owner is not BASE_REPO_OWNER, and only authorized users may contribute.
AI_HUB_REPO_OWNER = 'Reyev123'
AI_HUB_CONTENT_CATEGORIES: tuple[ContentCategory, ...] = (
    ContentCategory(
        'getting-started', 'getting_started', 'Getting Started',
        'extra-content-getting-started',
        'Guides, tutorials, and introductory material on Edge AI',
    ),
    ContentCategory(
        'resources', 'resources', 'Resources',
        'extra-content-resources',
        'Blog posts, articles, white papers, and other reading on Edge AI',
    ),
    ContentCategory(
        'partners', 'partners', 'Partners',
        'extra-content-partners',
        'Partner profiles that highlight partners and their Edge AI offerings',
    ),
    ContentCategory(
        'solutions', 'solutions', 'Solutions',
        'extra-content-solutions',
        'Production-ready Edge AI solutions with performance metrics',
    ),
    ContentCategory(
        'tools', 'tools', 'Tools',
        'extra-content-tools',
        'DEEPCRAFT\u2122 tools for developing and deploying Edge AI models',
    ),
)

TARGET_REPOS: dict[str, TargetRepo] = {
    'accelerators': TargetRepo(
        key='accelerators',
        repo_name='deepcraft-studio-accelerators',
        label=f'{DEEPCRAFT} Studio Accelerators',
        pr_title_template='Accelerator {project_name}',
        project_layout='accelerator_layout',
        git_ignored_dirs=('Models', 'PreprocessorTrack'),
    ),
    'model-zoo-psoc': TargetRepo(
        key='model-zoo-psoc',
        repo_name='deepcraft-model-zoo-for-psoc',
        label=f'{DEEPCRAFT} Model Zoo for {PSOC}',
        pr_title_template='Model Zoo PSOC {project_name}',
        project_layout='model_zoo_psoc_layout',
        git_ignored_dirs=(),
    ),
    'model-zoo-aurix': TargetRepo(
        key='model-zoo-aurix',
        repo_name='deepcraft-model-zoo-for-aurix',
        label=f'{DEEPCRAFT} Model Zoo for {AURIX}',
        pr_title_template=f'Model Zoo {AURIX} {{project_name}}',
        project_layout='metadata_only_layout',
        git_ignored_dirs=(),
        metadata_only=True,
    ),
    'extra-content': TargetRepo(
        key='extra-content',
        repo_name='deepcraft-ai-hub',
        owner=AI_HUB_REPO_OWNER,
        label=f'{DEEPCRAFT} AI Hub — Extra Content',
        pr_title_template='AI Hub {category}: {project_name}',
        project_layout='ai_hub_card_layout',
        git_ignored_dirs=(),
        restricted=True,
        push_metadata_only=True,
        content_categories=AI_HUB_CONTENT_CATEGORIES,
    ),
}

# ── UI ───────────────────────────────────────────────────────
COLUMN_PADDING = 2  # spaces between columns in numbered-choice prompts

ICON_PULL_REQUEST = '🔀'  # main banner — submit / merge a pull request
ICON_SUCCESS = '✅'
ICON_ERROR = '❌'
ICON_WARNING = '⚠️'
ICON_INFO = 'ℹ️'
ICON_PROGRESS = '▶️'
ICON_ABORT = '🛑'

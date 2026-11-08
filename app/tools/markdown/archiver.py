"""把 Markdown 与本地图片整理成博客导入 ZIP"""

import glob
import html
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname


HTML_IMAGE_RE = re.compile(
    r"(?P<prefix><img\b[^>]*?\bsrc\s*=\s*)(?P<quote>[\"'])"
    r"(?P<target>.*?)(?P=quote)(?P<suffix>[^>]*>)",
    re.IGNORECASE,
)
MARKDOWN_REFERENCE_IMAGE_RE = re.compile(r"!\[[^\]]*\]\[[^\]]*\]")
WIKI_IMAGE_RE = re.compile(r"!\[\[[^\]]+\]\]")
MARKDOWN_TITLE_RE = re.compile(
    r"""\s+("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|\([^)]*\))\s*$"""
)
FRONTMATTER_COVER_RE = re.compile(
    r"^(?P<prefix>\s*cover_image\s*:\s*)(?P<value>.*?)(?P<newline>\r?\n?)$"
)


@dataclass(frozen=True)
class ArchiveResult:
    """一次 Markdown 打包的统计结果"""

    markdown_count: int
    image_count: int
    skipped_images: int = 0
    warnings: tuple[str, ...] = ()


@dataclass
class MarkdownPackage:
    """单个 Markdown 在 ZIP 中的路径与图片状态"""

    source: Path
    archive_name: str
    image_folder: str
    images: dict[Path, str] = field(default_factory=dict)
    used_image_names: set[str] = field(default_factory=set)
    missing: list[str] = field(default_factory=list)


def safe_name(value: str, fallback: str = "image") -> str:
    """生成适合 ZIP 内部使用的文件名"""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return value or fallback


def safe_resource_name(value: str, fallback: str = "image") -> str:
    """生成可直接写入 Markdown 的图片目录或文件名

    CommonMark 的图片地址不能包含未转义空格, 括号等字符也容易让不同
    渲染器产生歧义. 保留中英文与数字, 其余字符统一替换成下划线.
    """
    value = safe_name(value, fallback)
    value = "".join(
        char if char.isalnum() or char in "-_." else "_"
        for char in value
    ).strip(" .")
    return value or fallback


def unique_name(name: str, used: set[str]) -> str:
    """在大小写不敏感的前提下保证同目录内文件名唯一"""
    candidate = name
    path = Path(name)
    index = 2
    while candidate.lower() in used:
        candidate = f"{path.stem}-{index}{path.suffix}"
        index += 1
    used.add(candidate.lower())
    return candidate


def is_remote_or_site_path(target: str) -> bool:
    """判断图片地址是否无需放入导入包"""
    lowered = target.strip().lower()
    if re.match(r"^[a-z]:[\\/]", lowered):
        return False
    if lowered.startswith(("data:", "http://", "https://", "//", "/assets/")):
        return True
    return urlparse(lowered).scheme in {"http", "https", "data"}


def local_path_from_target(target: str, markdown_dir: Path) -> Path | None:
    """把 Markdown 或 HTML 中的图片地址解析成本地绝对路径"""
    target = html.unescape(target.strip())
    if not target or is_remote_or_site_path(target):
        return None
    target = re.sub(r"\\([ ()])", r"\1", target)
    if target.lower().startswith("file:"):
        parsed = urlparse(target)
        raw = url2pathname(unquote(parsed.path))
        if re.match(r"^/[A-Za-z]:", raw):
            raw = raw[1:]
        return Path(raw).expanduser().resolve()
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    path = Path(target).expanduser()
    if not path.is_absolute():
        path = markdown_dir / path
    return path.resolve()


def find_closing_parenthesis(text: str, open_index: int) -> int:
    """从 Markdown 图片的左括号开始查找配对右括号"""
    depth = 1
    quote: str | None = None
    escaped = False
    index = open_index + 1
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def split_markdown_destination(inner: str) -> tuple[str, str, str, str]:
    """拆分 Markdown 图片括号内文本, 返回原始地址及前后保留文本"""
    leading = inner[: len(inner) - len(inner.lstrip())]
    trailing = inner[len(inner.rstrip()) :]
    core = inner.strip()
    if core.startswith("<") and ">" in core:
        end = core.find(">")
        return core[1:end], leading, core[end + 1 :], trailing
    title_match = MARKDOWN_TITLE_RE.search(core)
    if title_match:
        return (
            core[: title_match.start()].rstrip(),
            leading,
            core[title_match.start() :],
            trailing,
        )
    return core, leading, "", trailing


class ImageCollector:
    """登记一个 Markdown 中引用的本地图片"""

    def __init__(self, package: MarkdownPackage, allow_missing: bool):
        self.package = package
        self.allow_missing = allow_missing
        self.warnings: list[str] = []

    def register(self, target: str) -> str | None:
        """返回图片在 ZIP 中的相对路径, 远程地址或缺失图片返回 None"""
        path = local_path_from_target(target, self.package.source.parent)
        if path is None:
            return None
        if path in self.package.images:
            return self.package.images[path]
        if not path.is_file():
            message = f"{self.package.source}: 图片不存在: {target}"
            if self.allow_missing:
                self.warnings.append(message)
                return None
            self.package.missing.append(message)
            return None
        filename = unique_name(
            safe_resource_name(path.name),
            self.package.used_image_names,
        )
        archive_path = f"{self.package.image_folder}/{filename}"
        self.package.images[path] = archive_path
        return archive_path


def rewrite_markdown_images(text: str, collector: ImageCollector) -> str:
    """改写 Markdown 行内图片与 HTML img 标签中的本地路径"""
    replacements: list[tuple[int, int, str]] = []
    cursor = 0
    while True:
        start = text.find("![", cursor)
        if start < 0:
            break
        close_alt = text.find("]", start + 2)
        if close_alt < 0 or close_alt + 1 >= len(text) \
                or text[close_alt + 1] != "(":
            cursor = start + 2
            continue
        open_paren = close_alt + 1
        close_paren = find_closing_parenthesis(text, open_paren)
        if close_paren < 0:
            raise ValueError(
                f"{collector.package.source}: Markdown 图片括号未闭合"
            )
        inner_start = open_paren + 1
        inner = text[inner_start:close_paren]
        target, leading, suffix, trailing = split_markdown_destination(inner)
        archive_path = collector.register(target)
        if archive_path:
            replacements.append(
                (
                    inner_start,
                    close_paren,
                    f"{leading}{archive_path}{suffix}{trailing}",
                )
            )
        cursor = close_paren + 1

    for start, end, value in reversed(replacements):
        text = text[:start] + value + text[end:]

    def replace_html(match: re.Match[str]) -> str:
        target = match.group("target")
        archive_path = collector.register(target)
        if archive_path is None:
            return match.group(0)
        return (
            f"{match.group('prefix')}{match.group('quote')}{archive_path}"
            f"{match.group('quote')}{match.group('suffix')}"
        )

    return HTML_IMAGE_RE.sub(replace_html, text)


def rewrite_cover_image(text: str, collector: ImageCollector) -> str:
    """处理 frontmatter 中博客支持的 cover_image 字段"""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text
    end_index = -1
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end_index = index
            break
    if end_index < 0:
        return text

    for index in range(1, end_index):
        line = lines[index]
        match = FRONTMATTER_COVER_RE.match(line)
        if match is None:
            continue
        raw = match.group("value").strip()
        quote = ""
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in {"'", '"'}:
            quote = raw[0]
            raw = raw[1:-1]
        archive_path = collector.register(raw)
        if archive_path:
            lines[index] = (
                f"{match.group('prefix')}{quote}{archive_path}{quote}"
                f"{match.group('newline')}"
            )
        break
    return "".join(lines)


def collect_markdown_inputs(raw_inputs: list[str | Path]) -> list[Path]:
    """展开文件与目录参数, 返回去重后的 Markdown 文件列表"""
    sources: list[Path] = []
    for raw in raw_inputs:
        pattern = str(raw)
        matches = [Path(item) for item in glob.glob(pattern, recursive=True)]
        if not matches:
            matches = [Path(pattern)]
        for item in matches:
            if item.is_dir():
                sources.extend(path for path in item.rglob("*.md")
                               if path.is_file())
            elif item.is_file() and item.suffix.lower() == ".md":
                sources.append(item)
    unique: list[Path] = []
    seen: set[Path] = set()
    for source in sources:
        resolved = source.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return sorted(unique)


def default_output(sources: list[Path]) -> Path:
    """根据输入文件给出一个便于修改的默认 ZIP 路径"""
    if not sources:
        return Path.cwd() / "markdown-blog-import.zip"
    stem = safe_name(sources[0].stem, "blog")
    if len(sources) == 1:
        filename = f"{stem}-blog-import.zip"
    else:
        filename = f"markdown-blog-import-{datetime.now():%Y%m%d-%H%M%S}.zip"
    return sources[0].parent / filename


def build_archive(
    sources: list[Path],
    output: Path,
    allow_missing: bool,
    force: bool,
) -> ArchiveResult:
    """处理 Markdown 并写入 ZIP, 返回打包统计"""
    if not sources:
        raise ValueError("没有找到 Markdown 文件")
    if output.exists() and not force:
        raise FileExistsError(f"输出文件已存在: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.name}.tmp")
    temporary.unlink(missing_ok=True)
    packages: list[MarkdownPackage] = []
    used_markdown_names: set[str] = set()
    used_image_folders: set[str] = set()

    for source in sources:
        markdown_name = unique_name(
            safe_name(source.name),
            used_markdown_names,
        )
        folder_name = unique_name(
            safe_resource_name(Path(markdown_name).stem, "markdown"),
            used_image_folders,
        )
        packages.append(
            MarkdownPackage(
                source=source,
                archive_name=markdown_name,
                image_folder=f"images/{folder_name}",
            )
        )

    contents: dict[str, str] = {}
    missing: list[str] = []
    warnings: list[str] = []
    for package in packages:
        raw_text = package.source.read_text(encoding="utf-8-sig")
        if MARKDOWN_REFERENCE_IMAGE_RE.search(raw_text) \
                or WIKI_IMAGE_RE.search(raw_text):
            raise ValueError(
                f"{package.source}: 暂不支持引用式图片或 Wiki 图片, "
                "请改为 ![说明](图片路径)"
            )
        collector = ImageCollector(package, allow_missing)
        rewritten = rewrite_markdown_images(raw_text, collector)
        rewritten = rewrite_cover_image(rewritten, collector)
        contents[package.archive_name] = rewritten
        missing.extend(package.missing)
        warnings.extend(collector.warnings)

    if missing:
        raise FileNotFoundError(
            f"有 {len(missing)} 张本地图片不存在, 未生成导入包\n"
            + "\n".join(missing)
        )

    image_total = 0
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            zipfile.ZIP_DEFLATED,
            strict_timestamps=False,
        ) as archive:
            for package in packages:
                archive.writestr(
                    package.archive_name,
                    contents[package.archive_name].encode("utf-8"),
                )
                for image_path, archive_path in package.images.items():
                    archive.writestr(archive_path, image_path.read_bytes())
                    image_total += 1
            if archive.testzip() is not None:
                raise zipfile.BadZipFile("生成的 ZIP 校验失败")
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return ArchiveResult(
        markdown_count=len(packages),
        image_count=image_total,
        skipped_images=len(warnings),
        warnings=tuple(warnings),
    )

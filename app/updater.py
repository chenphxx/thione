"""从 GitHub Release 检查 下载并安装 Windows 更新

更新只接受当前仓库发布的正式版本和固定名称的 thione.exe 资源, 下载完成后必须
与 GitHub 返回的 SHA-256 一致. 覆盖当前 exe 需要等主进程退出, 因此安装由独立
的 PowerShell 进程完成, 成功后自动启动新版本
"""

import base64
import hashlib
import html as html_module
import json
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from urllib.parse import quote, urljoin, urlparse
from xml.etree import ElementTree

import httpx

from . import __version__
from .paths import ensure_dir, user_log_dir

logger = logging.getLogger(__name__)

GITHUB_REPOSITORY = "chenphxx/thione"
LATEST_RELEASE_PAGE = (
    f"https://github.com/{GITHUB_REPOSITORY}/releases/latest"
)
RELEASES_ATOM_URL = (
    f"https://github.com/{GITHUB_REPOSITORY}/releases.atom"
)
EXPANDED_ASSETS_URL = (
    f"https://github.com/{GITHUB_REPOSITORY}/releases/expanded_assets"
)
LATEST_RELEASE_API_URL = (
    f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
)
ASSET_NAME = "thione.exe"
USER_AGENT = f"thione-updater/{__version__}"
NETWORK_TIMEOUT = 20
DOWNLOAD_CHUNK = 1024 * 1024
MAX_RELEASE_JSON = 2 * 1024 * 1024
MAX_RELEASE_HTML = 2 * 1024 * 1024
UPDATE_WAIT_SECONDS = 300

_VERSION_RE = re.compile(r"^[vV]?(\d+(?:\.\d+)*)(?:[-+].*)?$")


class UpdateError(RuntimeError):
    """更新过程中可向用户说明的错误"""


@dataclass(frozen=True)
class Release:
    """一个可安装的 GitHub Release"""

    version: str
    tag: str
    name: str
    notes: str
    download_url: str
    size: int
    sha256: str


def _version_key(value):
    """把版本号转换成可比较的整数序列

    @param value: 例如 1.26.4 或 v1.26.4
    @return: 去掉末尾零后的版本整数元组
    @throws UpdateError: 版本号格式无法识别时
    """
    match = _VERSION_RE.match((value or "").strip())
    if match is None:
        raise UpdateError(f"无法识别的版本号: {value}")
    parts = [int(part) for part in match.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def is_newer(latest, current):
    """判断最新版本是否高于当前版本

    正式 Release 只按数字段比较, 不把末尾的 .0 视为更高版本

    @param latest: 最新版本号
    @param current: 当前版本号
    @return: latest 高于 current 时返回 True
    """
    return _version_key(latest) > _version_key(current)


def _release_from_payload(payload):
    """从 GitHub API 返回值提取安装所需字段

    @param payload: latest release 的 JSON 对象
    @return: Release 实例
    @throws UpdateError: 返回值缺少版本或可安装资源时
    """
    if payload.get("draft") or payload.get("prerelease"):
        raise UpdateError("最新发布不是正式版本")
    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        raise UpdateError("最新发布缺少版本标签")
    _version_key(tag)

    asset = next(
        (
            item for item in payload.get("assets", [])
            if str(item.get("name") or "").casefold() == ASSET_NAME.casefold()
        ),
        None,
    )
    if asset is None:
        raise UpdateError(f"最新发布中没有 {ASSET_NAME}")

    download_url = str(asset.get("browser_download_url") or "").strip()
    parsed = urlparse(download_url)
    expected_prefix = f"/{GITHUB_REPOSITORY}/releases/download/"
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or not parsed.path.startswith(expected_prefix)
    ):
        raise UpdateError("更新资源地址不属于当前 GitHub 仓库")

    digest = str(asset.get("digest") or "").strip().lower()
    if not digest.startswith("sha256:"):
        raise UpdateError("发布资源缺少 SHA-256 校验值")
    sha256 = digest.split(":", 1)[1]
    if len(sha256) != 64:
        raise UpdateError("发布资源的 SHA-256 校验值格式不正确")

    try:
        size = int(asset.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    return Release(
        version=tag[1:] if tag[:1] in ("v", "V") else tag,
        tag=tag,
        name=str(payload.get("name") or tag).strip(),
        notes=str(payload.get("body") or "").strip(),
        download_url=download_url,
        size=size,
        sha256=sha256,
    )


def _fetch_api_release():
    """通过 GitHub API 读取最新正式 Release

    API 有匿名请求配额, 因此只作为页面解析失败时的回退

    @return: Release 实例
    @throws UpdateError: 网络失败或发布信息不完整时
    """
    try:
        with httpx.Client(
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
            },
            follow_redirects=True,
            timeout=NETWORK_TIMEOUT,
        ) as client:
            response = client.get(LATEST_RELEASE_API_URL)
        if response.status_code == 404:
            raise UpdateError("上游仓库还没有发布正式版本")
        response.raise_for_status()
        raw = response.content
    except httpx.HTTPStatusError as exc:
        raise UpdateError(
            f"GitHub 返回 HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise UpdateError(f"无法连接 GitHub: {exc}") from exc
    if len(raw) > MAX_RELEASE_JSON:
        raise UpdateError("GitHub 返回的发布信息过大")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("GitHub 返回的发布信息无法解析") from exc
    return _release_from_payload(payload)


def _latest_tag_from_page():
    """从 releases/latest 的最终跳转地址读取版本标签"""
    try:
        with httpx.Client(
            headers={"Accept": "text/html", "User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=NETWORK_TIMEOUT,
        ) as client:
            response = client.get(LATEST_RELEASE_PAGE)
        if response.status_code == 404:
            raise UpdateError("上游仓库还没有发布正式版本")
        response.raise_for_status()
        final_url = str(response.url)
    except httpx.HTTPStatusError as exc:
        raise UpdateError(
            f"GitHub 返回 HTTP {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        raise UpdateError(f"无法连接 GitHub: {exc}") from exc
    parsed = urlparse(final_url)
    prefix = f"/{GITHUB_REPOSITORY}/releases/tag/"
    if parsed.hostname != "github.com" or not parsed.path.startswith(prefix):
        raise UpdateError("无法识别 GitHub 最新发布页面")
    return parsed.path[len(prefix):].strip("/")


def _read_text_url(url, limit):
    """读取一个小型文本响应并限制大小"""
    try:
        with httpx.Client(
            headers={"Accept": "text/html", "User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=NETWORK_TIMEOUT,
        ) as client:
            response = client.get(url)
        response.raise_for_status()
        raw = response.content
    except httpx.HTTPError as exc:
        raise UpdateError(f"无法读取 GitHub 页面: {exc}") from exc
    if len(raw) > limit:
        raise UpdateError("GitHub 返回的页面过大")
    return raw.decode("utf-8", errors="replace")


def _plain_release_notes(raw):
    """把 Release 的 HTML 说明转成适合弹窗阅读的纯文本"""
    text = re.sub(r"<[^>]+>", "\n", raw or "")
    text = html_module.unescape(text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _fetch_release_notes(tag):
    """从 Release Atom 中读取指定标签的更新说明"""
    try:
        raw = _read_text_url(RELEASES_ATOM_URL, MAX_RELEASE_HTML)
        root = ElementTree.fromstring(raw)
    except (ElementTree.ParseError, UpdateError):
        logger.debug("读取 Release 更新说明失败", exc_info=True)
        return ""
    namespace = "{http://www.w3.org/2005/Atom}"
    prefix = f"/{GITHUB_REPOSITORY}/releases/tag/"
    for entry in root.findall(f"{namespace}entry"):
        link = entry.find(f"{namespace}link")
        if link is None:
            continue
        path = urlparse(link.get("href", "")).path
        if not path.startswith(prefix) or path[len(prefix):] != tag:
            continue
        content = entry.find(f"{namespace}content")
        return _plain_release_notes(content.text if content is not None else "")
    return ""


def _fetch_page_release():
    """从 Release 页面读取版本 资源和 SHA-256, 不消耗 API 配额"""
    tag = _latest_tag_from_page()
    _version_key(tag)
    assets_url = f"{EXPANDED_ASSETS_URL}/{quote(tag, safe='')}"
    page = _read_text_url(assets_url, MAX_RELEASE_HTML)
    asset_path = f"/{GITHUB_REPOSITORY}/releases/download/"
    match = re.search(
        rf'href="([^"]+/releases/download/[^"]+/{re.escape(ASSET_NAME)})"',
        page,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise UpdateError(f"最新发布中没有 {ASSET_NAME}")
    download_url = urljoin("https://github.com", html_module.unescape(
        match.group(1),
    ))
    parsed = urlparse(download_url)
    if parsed.scheme != "https" or parsed.hostname != "github.com" \
            or not parsed.path.startswith(asset_path):
        raise UpdateError("更新资源地址不属于当前 GitHub 仓库")
    asset_row = page[match.start():match.start() + 8000]
    digest_match = re.search(
        r"sha256:([0-9a-f]{64})", asset_row, flags=re.IGNORECASE,
    )
    if digest_match is None:
        raise UpdateError("发布资源缺少 SHA-256 校验值")
    return Release(
        version=tag[1:] if tag[:1] in ("v", "V") else tag,
        tag=tag,
        name=f"thione {tag}",
        notes=_fetch_release_notes(tag),
        download_url=download_url,
        size=0,
        sha256=digest_match.group(1).lower(),
    )


def fetch_latest_release():
    """读取 GitHub 上最新的正式 Release

    优先访问公开 Release 页面, 避免匿名 API 配额耗尽; 页面结构不兼容时再回退
    到 GitHub API

    @return: Release 实例
    @throws UpdateError: 网络失败或发布信息不完整时
    """
    try:
        return _fetch_page_release()
    except UpdateError as page_error:
        logger.warning("Release 页面读取失败, 回退 GitHub API: %s", page_error)
        try:
            return _fetch_api_release()
        except UpdateError as api_error:
            raise UpdateError(
                f"无法读取最新发布: {page_error}; GitHub API: {api_error}"
            ) from api_error


def update_cache_dir():
    """下载缓存目录 %LOCALAPPDATA%\\thione\\updates"""
    return ensure_dir(os.path.join(os.path.dirname(user_log_dir()), "updates"))


def current_executable():
    """当前可自动覆盖的 exe 路径

    @return: 打包运行时返回 exe 的绝对路径, 源码运行时返回 None
    """
    if not getattr(sys, "frozen", False):
        return None
    return os.path.abspath(sys.executable)


def _file_sha256(path):
    """计算文件的 SHA-256"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(DOWNLOAD_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def download_release(release, destination, on_progress=None):
    """下载并校验 Release 资源

    @param release: 目标 Release
    @param destination: 最终保存路径
    @param on_progress: 可选回调, 接收 (已下载字节, 总字节)
    @return: 下载完成的文件路径
    @throws UpdateError: 网络中断 大小不符或校验失败时
    """
    destination = os.path.abspath(destination)
    ensure_dir(os.path.dirname(destination))
    part_path = destination + ".part"
    digest = hashlib.sha256()
    received = 0
    last_percent = -1
    expected_size = release.size
    try:
        timeout = httpx.Timeout(NETWORK_TIMEOUT, read=120)
        with httpx.Client(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            timeout=timeout,
        ) as client:
            with client.stream("GET", release.download_url) as response:
                response.raise_for_status()
                content_length = response.headers.get("Content-Length")
                try:
                    total = int(content_length or release.size or 0)
                except (TypeError, ValueError):
                    total = release.size
                if not expected_size and total > 0:
                    expected_size = total
                with open(part_path, "wb") as handle:
                    for chunk in response.iter_bytes(DOWNLOAD_CHUNK):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        digest.update(chunk)
                        received += len(chunk)
                        if on_progress is not None and total > 0:
                            percent = int(received * 100 / total)
                            if percent >= last_percent + 2 or percent == 100:
                                last_percent = percent
                                on_progress(received, total)
        if expected_size and received != expected_size:
            raise UpdateError(
                f"更新文件大小不符: 应为 {expected_size} 字节, "
                f"实际 {received} 字节"
            )
        actual = digest.hexdigest().lower()
        if actual != release.sha256.lower():
            raise UpdateError("更新文件 SHA-256 校验失败")
        os.replace(part_path, destination)
    except (httpx.HTTPError, OSError, UpdateError) as exc:
        try:
            os.remove(part_path)
        except OSError:
            pass
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError(f"下载更新失败: {exc}") from exc
    return destination


def stage_update(downloaded, target, expected_sha256):
    """把已下载文件复制到当前程序同目录的暂存文件

    暂存文件与目标 exe 位于同一磁盘, 退出后可用原子替换完成安装

    @param downloaded: 已校验的下载文件
    @param target: 当前运行的 exe
    @param expected_sha256: 发布资源的 SHA-256
    @return: 暂存文件路径
    @throws UpdateError: 程序目录不可写或复制后校验失败时
    """
    staged = target + ".update"
    try:
        shutil.copyfile(downloaded, staged)
    except OSError as exc:
        raise UpdateError(f"无法写入程序目录: {exc}") from exc
    try:
        if _file_sha256(staged).lower() != expected_sha256.lower():
            raise UpdateError("暂存更新文件的 SHA-256 校验失败")
    except Exception:
        try:
            os.remove(staged)
        except OSError:
            pass
        raise
    return staged


def _powershell_quote(value):
    """把值写成 PowerShell 单引号字符串"""
    return "'" + str(value).replace("'", "''") + "'"


def _update_script(target, staged, process_id, downloaded):
    """生成等待退出 覆盖程序并重启的 PowerShell 脚本

    @param target: 当前运行的 exe
    @param staged: 已验证的暂存文件
    @param process_id: 当前进程 PID
    @param downloaded: 下载缓存文件, 安装后删除
    @return: PowerShell 脚本文本
    """
    backup = target + ".bak"
    cancel_path = staged + ".cancel"
    log_path = os.path.join(user_log_dir(), "updater.log")
    iterations = max(1, UPDATE_WAIT_SECONDS * 4)
    return """
$ErrorActionPreference = 'Stop'
$appPid = %d
$target = %s
$staged = %s
$backup = %s
$cancel = %s
$downloaded = %s
$log = %s

function Write-UpdateLog([string]$text)
{
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    "$stamp $text" | Out-File -LiteralPath $log -Append -Encoding utf8
}

Write-UpdateLog ("更新进程已启动: pid=" + $PID)

$processExited = $false
$backupCreated = $false
try
{
    for ($i = 0; $i -lt %d; $i++)
    {
        if (Test-Path -LiteralPath $cancel)
        {
            throw '用户取消更新'
        }
        if (-not (Get-Process -Id $appPid -ErrorAction SilentlyContinue))
        {
            $processExited = $true
            break
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $processExited)
    {
        throw '等待程序退出超时'
    }

    Start-Sleep -Milliseconds 500
    if (Test-Path -LiteralPath $backup)
    {
        Remove-Item -LiteralPath $backup -Force
    }
    for ($i = 0; $i -lt 20; $i++)
    {
        try
        {
            [System.IO.File]::Replace($staged, $target, $backup)
            $backupCreated = $true
            break
        }
        catch
        {
            if ($i -eq 19)
            {
                throw
            }
            Start-Sleep -Milliseconds 500
        }
    }
    Start-Process -FilePath $target `
        -WorkingDirectory (Split-Path -LiteralPath $target -Parent)
    Write-UpdateLog '更新安装完成'
}
catch
{
    Write-UpdateLog ("更新安装失败: " + $_.Exception.ToString())
    if ($processExited)
    {
        try
        {
            if ($backupCreated -and (Test-Path -LiteralPath $backup))
            {
                Copy-Item -LiteralPath $backup -Destination $target -Force
            }
            if (Test-Path -LiteralPath $target)
            {
                Start-Process -FilePath $target `
                    -WorkingDirectory (Split-Path -LiteralPath $target -Parent)
            }
        }
        catch
        {
            Write-UpdateLog ("恢复旧版本失败: " + $_.Exception.ToString())
        }
    }
}
finally
{
    if (Test-Path -LiteralPath $downloaded)
    {
        Remove-Item -LiteralPath $downloaded -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $cancel)
    {
        Remove-Item -LiteralPath $cancel -Force -ErrorAction SilentlyContinue
    }
}
""" % (
        process_id,
        _powershell_quote(target),
        _powershell_quote(staged),
        _powershell_quote(backup),
        _powershell_quote(cancel_path),
        _powershell_quote(downloaded),
        _powershell_quote(log_path),
        iterations,
    )


def launch_update(target, staged, downloaded):
    """启动独立更新进程

    @param target: 当前运行的 exe
    @param staged: 已验证的暂存文件
    @param downloaded: 下载缓存文件
    @throws UpdateError: 无法启动 PowerShell 时
    """
    if os.name != "nt":
        raise UpdateError("自动更新仅支持 Windows")
    powershell = shutil.which("powershell.exe")
    if not powershell:
        raise UpdateError("找不到 PowerShell, 无法启动更新程序")
    try:
        os.remove(staged + ".cancel")
    except OSError:
        pass
    script = _update_script(target, staged, os.getpid(), downloaded)
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    # DETACHED_PROCESS 会让 powershell.exe 在执行 -EncodedCommand 前直接退出,
    # 独立进程组已经能保证脚本在主程序退出后继续运行
    flags = (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    try:
        process = subprocess.Popen(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-EncodedCommand",
                encoded,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=flags,
        )
    except OSError as exc:
        raise UpdateError(f"无法启动更新程序: {exc}") from exc
    logger.info(
        "更新进程已启动: pid=%s, target=%s, version_file=%s",
        process.pid, target, staged,
    )
    return process


def cancel_update(staged):
    """通知已经启动的更新进程放弃安装

    @param staged: 传给 launch_update 的暂存文件
    """
    try:
        with open(staged + ".cancel", "w", encoding="ascii") as handle:
            handle.write("cancel")
    except OSError:
        logger.warning("无法写入更新取消标记", exc_info=True)

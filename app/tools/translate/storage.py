"""用户级配置的读写。

配置主落点是 `%APPDATA%\\thione\\config.ini`, 用户无需关心程序被装在哪里,
也不需要手工编辑文件 —— 在划词翻译页面填好保存即可。

文件里有两个段: `[translate]` 记录用哪个翻译服务与翻成哪种语言, `[huawei]`
记录华为云的凭据。两者分开存放, 因此切换服务时不必动凭据, 删除凭据也不会
丢掉服务选择。使用免费接口时不需要凭据, 缺凭据不算错误。

读取优先级 (高 -> 低):
    1. 环境变量 HUAWEI_AK / HUAWEI_SK / HUAWEI_PROJECT_ID / HUAWEI_REGION
    2. %APPDATA%\\thione\\config.ini           (界面保存, 主要落点)
    3. %APPDATA%\\thpy\\config.ini             (更名前的配置, 向后兼容)
    4. %APPDATA%\\transpy\\config.ini          (独立版 transpy 的旧配置, 向后兼容)
    5. 程序所在目录的 .env                   (便携版 / 向后兼容)
    6. 当前工作目录的 .env
    7. IAM_transpy-accessKeys.csv             (只提供 AK/SK)

所有落点都找不到时抛出 MissingConfigError, 由界面提示用户配置。
"""

import configparser
import csv
import logging
import os

from . import constants
from .config import Config
from .language import AUTO_LANG, DEFAULT_TARGET_LANG
from .providers import DEFAULT_PROVIDER, PROVIDER_NAMES, spec_for
from ...paths import (
    app_root,
    ensure_dir,
    legacy_user_data_dir,
    user_data_dir,
)

logger = logging.getLogger(__name__)

#: 华为云凭据所在的段
SECTION = "huawei"
#: 服务选择所在的段
PROVIDER_SECTION = "translate"
#: 服务选择在段里的键名
PROVIDER_KEY = "PROVIDER"
#: 源语言与目标语言在段里的键名
SOURCE_KEY = "SOURCE_LANG"
TARGET_KEY = "TARGET_LANG"
LEGACY_APP_DIR_NAME = "transpy"


class ConfigError(RuntimeError):
    """配置缺失或格式错误。"""


class MissingConfigError(ConfigError):
    """未找到可用的凭据, 需要引导用户配置。

    attributes 里带上已搜索过的位置, 便于在对话框/日志中说明。
    """

    def __init__(self, message, searched=()):
        super().__init__(message)
        self.searched = tuple(searched)


def config_path():
    """返回 config.ini 的完整路径 (不保证文件已存在)。"""
    return os.path.join(user_data_dir(), constants.CONFIG_FILE_NAME)


def legacy_config_path():
    """返回独立版 transpy 的配置路径, 用作向后兼容来源。"""
    appdata = (
        os.environ.get("APPDATA")
        or os.environ.get("LOCALAPPDATA")
        or os.path.expanduser("~")
    )
    return os.path.join(appdata, LEGACY_APP_DIR_NAME, constants.CONFIG_FILE_NAME)


def renamed_config_path():
    """返回更名前 (thpy) 保存在 %APPDATA%\\thpy 下的配置路径, 用作兼容来源。"""
    return os.path.join(legacy_user_data_dir(), constants.CONFIG_FILE_NAME)


def _read_ini(path, section=SECTION):
    """读取 config.ini 里某一段, 返回 {key: value}; 文件不存在或损坏时返回 {}。

    @param path: 配置文件路径
    @param section: 段名, 默认是存放华为云凭据的那一段
    @return: 键名大写、值去空白的字典
    """
    if not os.path.isfile(path):
        return {}
    parser = configparser.ConfigParser()
    try:
        # utf-8-sig: 兼容记事本「UTF-8」另存后带 BOM 的文件
        parser.read(path, encoding="utf-8-sig")
    except (configparser.Error, OSError, UnicodeDecodeError):
        # 配置损坏不应让程序无法启动, 走后续兜底来源
        return {}
    if not parser.has_section(section):
        return {}
    return {k.upper(): (v or "").strip() for k, v in parser.items(section)}


def _read_env_file(path):
    """读取 KEY=VALUE 样式的 .env 文件, 返回 dict。跳过注释与空行。"""
    env = {}
    if not os.path.isfile(path):
        return env
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    except OSError:
        return {}
    return env


def _read_access_key_csv(path):
    """从华为云下载的 accessKeys csv 读取 (ak, sk)。兼容带 BOM 的文件。"""
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ak = (row.get("Access key ID") or "").strip()
                sk = (row.get("Secret access key") or "").strip()
                if ak and sk:
                    return ak, sk
    except (OSError, csv.Error, UnicodeDecodeError):
        return None, None
    return None, None


def _normalize_provider(value):
    """把配置里的服务名收敛到已知取值, 未知值回落到默认服务。

    @param value: 配置文件里读到的原始字符串
    @return: providers.PROVIDER_NAMES 中的一个
    """
    value = (value or "").strip().lower()
    if value in PROVIDER_NAMES:
        return value
    if value:
        logger.warning("未知的翻译服务 %r, 回落到 %s", value, DEFAULT_PROVIDER)
    return DEFAULT_PROVIDER


def _normalize_languages(provider, source_lang, target_lang):
    """把语言选择收敛到当前服务支持的范围, 不支持时回落到默认值。

    目标语言的 auto 表示按源语言自动选择, 不属于任何服务的语言代码表,
    因此单独放行。

    @param provider: 服务名, 决定支持哪些语言
    @param source_lang: 配置里读到的源语言
    @param target_lang: 配置里读到的目标语言
    @return: (源语言, 目标语言) 领域语言代码
    """
    spec = spec_for(provider)
    source = (source_lang or "").strip()
    if source not in spec.source_languages:
        if source:
            logger.warning("服务 %s 不支持源语言 %r, 改用 %s",
                           provider, source, AUTO_LANG)
        source = AUTO_LANG
    target = (target_lang or "").strip()
    if target != AUTO_LANG and target not in spec.languages:
        if target:
            logger.warning("服务 %s 不支持目标语言 %r, 改用 %s",
                           provider, target, DEFAULT_TARGET_LANG)
        target = DEFAULT_TARGET_LANG
    return source, target


def current_provider():
    """返回当前选择的翻译服务, 从未配置过时返回默认值。

    兼容来源与新配置一样参与查找: 更名前 (thpy) 与独立版 (transpy) 留下的
    文件里如果写了服务选择, 同样会被读到。

    @return: providers.PROVIDER_NAMES 中的一个
    """
    for path in (config_path(), renamed_config_path(), legacy_config_path()):
        value = _read_ini(path, PROVIDER_SECTION).get(PROVIDER_KEY)
        if value:
            return _normalize_provider(value)
    return DEFAULT_PROVIDER


def current_languages():
    """返回当前保存的源语言与目标语言, 没有配置过时返回默认值。

    与 current_provider() 一样按 新配置 -> 更名前配置 -> 旧版配置 的顺序查找,
    先配置过的优先; 旧版留下的文件没有这两项, 因此会回落到默认值。

    @return: (源语言, 目标语言) 领域语言代码
    """
    provider = current_provider()
    for path in (config_path(), renamed_config_path(), legacy_config_path()):
        section = _read_ini(path, PROVIDER_SECTION)
        source = section.get(SOURCE_KEY)
        target = section.get(TARGET_KEY)
        if source or target:
            return _normalize_languages(provider, source, target)
    return _normalize_languages(provider, "", "")


def legacy_dirs():
    """返回兼容来源的查找目录 (程序目录 + 当前工作目录)。"""
    dirs = [app_root()]
    cwd = os.getcwd()
    if cwd not in dirs:
        dirs.append(cwd)
    return dirs


def load():
    """加载运行配置, 返回 Config。缺少凭据时抛出 MissingConfigError。"""
    ini_path = config_path()
    ini = _read_ini(ini_path)
    # 更名前由 thpy 保存的配置: 仅作为主配置文件的兜底
    renamed_path = renamed_config_path()
    renamed_ini = _read_ini(renamed_path)
    # 集成前由独立版 transpy 保存的配置: 仅作为主配置文件的兜底
    old_path = legacy_config_path()
    old_ini = _read_ini(old_path)

    # 收集兼容来源的 .env, 先出现者优先
    dirs = legacy_dirs()
    file_env = {}
    for d in dirs:
        for k, v in _read_env_file(os.path.join(d, ".env")).items():
            file_env.setdefault(k, v)

    searched = (ini_path, renamed_path, old_path) + tuple(
        os.path.join(d, ".env") for d in dirs
    )

    def pick(name):
        """按 环境变量 -> 新配置 -> 更名前配置 -> 旧版配置 -> .env 取值。"""
        sources = (
            ("环境变量", os.environ.get(f"{constants.ENV_PREFIX}{name}")),
            (ini_path, ini.get(name)),
            (renamed_path, renamed_ini.get(name)),
            (old_path, old_ini.get(name)),
            (".env", file_env.get(f"{constants.ENV_PREFIX}{name}")),
        )
        for source, value in sources:
            if value:
                return value, source
        return None, None

    region, region_src = pick("REGION")
    ak, ak_src = pick("AK")
    sk, sk_src = pick("SK")
    project_id, project_src = pick("PROJECT_ID")
    region = region or constants.REGION

    # CSV 兜底 (仅 AK/SK): 在候选目录中依次查找
    csv_path = None
    if not ak or not sk:
        for d in dirs:
            candidate = os.path.join(d, constants.CREDENTIAL_FILE)
            csv_ak, csv_sk = _read_access_key_csv(candidate)
            if csv_ak and csv_sk:
                ak = ak or csv_ak
                sk = sk or csv_sk
                csv_path = candidate
                break

    provider = current_provider()
    source_lang, target_lang = current_languages()
    spec = spec_for(provider)
    if not spec.requires_credentials:
        # 不需要凭据的服务不去校验; 已保存的凭据仍然读出来,
        # 用户切回华为云时不用重新填
        logger.info("翻译服务: %s, 不需要凭据", spec.label)
        return Config(ak=ak or "", sk=sk or "", project_id=project_id or "",
                      region=region, provider=provider,
                      source_lang=source_lang, target_lang=target_lang)

    # 记录凭据来源, 便于排查"为什么又要我配置"这类问题
    if ak and sk and project_id:
        logger.info(
            "凭据来源: AK/SK -> %s, project_id -> %s, region -> %s",
            ak_src or csv_path or "?",
            project_src,
            region_src or "默认值",
        )
    else:
        logger.warning(
            "未找到完整凭据 (AK: %s, SK: %s, project_id: %s); 已搜索: %s",
            ak_src or "缺失",
            sk_src or "缺失",
            project_src or "缺失",
            " / ".join(searched),
        )

    if not (ak and sk and project_id):
        missing = [
            name
            for name, value in (("AK", ak), ("SK", sk), ("PROJECT_ID", project_id))
            if not value
        ]
        raise MissingConfigError(
            "缺少配置项: " + ", ".join(f"HUAWEI_{m}" for m in missing),
            searched=searched,
        )

    return Config(ak=ak, sk=sk, project_id=project_id, region=region,
                  provider=provider, source_lang=source_lang,
                  target_lang=target_lang)


def save(config):
    """把配置写入 %APPDATA%\\thione\\config.ini。"""
    path = config_path()
    ensure_dir(os.path.dirname(path))

    provider = _normalize_provider(config.provider)
    source_lang, target_lang = _normalize_languages(
        provider, config.source_lang, config.target_lang
    )

    parser = configparser.ConfigParser()
    parser[PROVIDER_SECTION] = {
        PROVIDER_KEY: provider,
        SOURCE_KEY: source_lang,
        TARGET_KEY: target_lang,
    }
    parser[SECTION] = {
        "AK": config.ak or "",
        "SK": config.sk or "",
        "PROJECT_ID": config.project_id or "",
        # 用 constants 的默认值, 避免把某个用户的区域写成全局默认
        "REGION": config.region or constants.REGION,
    }

    # 先写临时文件再替换, 避免写一半断电留下损坏的配置
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        parser.write(f)
    os.replace(tmp, path)
    return path


def current_values():
    """返回当前可用的服务选择与凭据取值, 缺项时留空 (供界面预填, 不抛异常)。

    与 load() 的区别只有一点: 这里不要求各项齐全, 目的是让用户在已有部分
    来源 (环境变量 / 旧版配置 / .env / csv) 的基础上补齐剩余字段。
    """
    ini = _read_ini(config_path())
    renamed_ini = _read_ini(renamed_config_path())
    old_ini = _read_ini(legacy_config_path())

    file_env = {}
    for d in legacy_dirs():
        for k, v in _read_env_file(os.path.join(d, ".env")).items():
            file_env.setdefault(k, v)

    def pick(name):
        candidates = (
            os.environ.get(f"{constants.ENV_PREFIX}{name}"),
            ini.get(name),
            renamed_ini.get(name),
            old_ini.get(name),
            file_env.get(f"{constants.ENV_PREFIX}{name}"),
        )
        for value in candidates:
            if value:
                return value
        return ""

    values = {
        "ak": pick("AK"),
        "sk": pick("SK"),
        "project_id": pick("PROJECT_ID"),
        "region": pick("REGION") or constants.REGION,
        "provider": current_provider(),
    }
    values["source_lang"], values["target_lang"] = current_languages()

    # CSV 只提供 AK/SK, 且优先级最低
    if not (values["ak"] and values["sk"]):
        for d in legacy_dirs():
            csv_ak, csv_sk = _read_access_key_csv(
                os.path.join(d, constants.CREDENTIAL_FILE)
            )
            if csv_ak and csv_sk:
                values["ak"] = values["ak"] or csv_ak
                values["sk"] = values["sk"] or csv_sk
                break

    return values

"""划词翻译的常量, 以及各翻译服务的可公开配置。

注意: 此处仅存放区域、功能参数等可公开信息。AK/SK 密钥与 project_id 等
涉密信息由 storage 单独加载, 不会写入版本库。

可选服务与各家服务的语言代码表在 `providers.provider` 里, 这里只放各服务的
接口地址与超时时间。
"""

PAGE_TITLE = "划词翻译"
APP_TIP = "thione 运行中 · 双击 Ctrl 翻译"

# 华为云自然语言处理 (NLP) 服务区域。区域标识并非机密信息。
REGION = "cn-north-4"
SERVICE_ENDPOINT = f"https://nlp-ext.{REGION}.myhuaweicloud.com"

# uapipro 免费接口 (https://uapis.cn): 源语言由服务端自动识别
UAPI_BASE_URL = "https://uapis.cn"
UAPI_MAX_TEXT_LENGTH = 3000     # 接口限制的单次最大字符数
UAPI_TIMEOUT = 15.0             # 单次请求的超时时间 (秒)

# 60s API 在线翻译 (https://60s.viki.moe): 源语言与目标语言都可以指定,
# 文档没有给出单次字符上限, 因此只依赖服务端自己的校验
SIXTY_BASE_URL = "https://60s.viki.moe"
SIXTY_TIMEOUT = 15.0            # 单次请求的超时时间 (秒)

# 凭据来源文件名
CREDENTIAL_FILE = "IAM_transpy-accessKeys.csv"   # 华为云控制台下载的 csv
CONFIG_FILE_NAME = "config.ini"                  # %APPDATA%\thione 下的主配置
LEGACY_ENV_FILE = ".env"                         # 便携版 / 向后兼容
ENV_PREFIX = "HUAWEI_"

# 功能参数
MAX_TEXT_LENGTH = 2000          # 华为云 API 单次可翻译的最大字符数
DOUBLE_PRESS_INTERVAL = 1.0     # 两次 Ctrl 之间的最大间隔 (秒)
CTRL_REPEAT_GAP = 0.5           # 小于该间隔的重复 Ctrl 按下判定为长按自动重复 (秒)
COPY_SETTLE_TIME = 0.05         # 复制后等待剪贴板刷新的时间 (秒)
UI_POLL_INTERVAL_MS = 60        # 主线程轮询后台任务的间隔 (毫秒)

# 图标资源路径 (相对项目根目录)
ICON_PATH = "assets/images/logo.ico"
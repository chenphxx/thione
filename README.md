# thione

由dupy, renamepy, transpy三个项目集成而来, 这三个仓库后续大概率不再维护, 新功能以及安全更新优先维护本项目 

## 功能

### 图片查重

- 扫描指定文件夹 按扩展名筛选 并以缩略图预览 
- 基于感知哈希 (ImageHash dHash) 查找视觉上重复的图片 
- 在分组窗口中逐组勾选需要保留的图片 可删除或整理到 `重复项` 子文件夹 

### 批量重命名

- 可同时添加多个文件夹 每个文件夹独立选择路径 筛选与预览 
- 按 前缀 + 起始序号 批量改名 
- 保存位置选原文件夹即原地重命名 中途失败可回滚 
- 底部预览区支持图片 文本 CSV 与 Excel 

### 划词翻译

- 默认不启动 需要在页面里点 `启动翻译` 之后热键与托盘图标才会生效 
- 选中任意文本后连续按两次 `Ctrl` 即可翻译 中文默认译英文 其它语言默认译中文 
- 托盘菜单可打开主窗口 暂停热键或退出 
- 基于华为云 NLP 凭据在界面里填写一次即可 
- 页面内显示最近一次翻译结果 

## 环境与运行

- Windows 
- Python 3.10 及以上 

```bash
pip install -r requirements.txt
python main.py
```

## 打包

```bash
pyinstaller --noconfirm --clean thione.spec
```

产物为单文件 `dist\thione.exe` 只有用 `thione.spec` 构建才会带上图标与版本资源 

## 数据目录

| 用途 | 路径 |
| --- | --- |
| 华为云凭据 | `%APPDATA%\thione\config.ini` |
| 界面偏好 | `%APPDATA%\thione\settings.ini` |
| 运行日志 | `%LOCALAPPDATA%\thione\logs\thione.log` |

从更名前或独立版迁移无需任何操作 程序会自动读取旧位置的 `%APPDATA%\thpy\config.ini` 与 `%APPDATA%\transpy\config.ini` 

## 文档

参考docs/ 

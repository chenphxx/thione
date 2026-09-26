# thione

由dupy, renamepy, transpy三个项目集成而来, 这三个仓库后续大概率不再维护, 新功能以及安全更新优先维护本项目 

## 功能

### 图片查重

- 扫描指定文件夹, 基于感知哈希 (dHash) 查找视觉上重复的图片 

- 在分组窗口中逐组勾选需要保留的图片 可删除或整理到 `重复项` 子文件夹 

### 批量重命名

- 可同时添加多个文件夹 每个文件夹独立选择路径 筛选与预览 
- 按 前缀 + 起始序号 批量改名 
- 保存位置选原文件夹即覆盖原文件夹的内容 

### 划词翻译

- 选中任意文本后连续按两次 `Ctrl` 即可翻译 
- 托盘菜单可打开主窗口 暂停热键或退出 

## 如何使用

- Python 3.10 及以上 

```bash
pip install -r requirements.txt
python main.py
```

## 打包

```bash
pyinstaller --noconfirm --clean thione.spec
```

## 数据目录

| 用途      | 路径                                      |
| ------- | --------------------------------------- |
| 翻译设置与凭据 | `%APPDATA%\thione\config.ini`           |
| 界面偏好    | `%APPDATA%\thione\settings.ini`         |
| 运行日志    | `%LOCALAPPDATA%\thione\logs\thione.log` |

## 文档

参考`docs/` 

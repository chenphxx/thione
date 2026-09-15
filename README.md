# thpy

把图片查重 批量重命名 划词翻译三个工具集成到同一个窗口的 Windows 桌面工具箱 

三个工具都是独立的页面 通过左侧导航切换 共用一套主题 配置与日志目录 

## 界面

- 深色与浅色两套模式 配色与博客 phxxblog 的默认预设保持一致 
- `Ctrl+T` 或侧栏底部的按钮切换 切换时颜色平滑过渡 
- 左侧导航为自绘控件 选中项的指示条会滑动 悬停底色淡入 页面切换带轻微位移动效 

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
pyinstaller --noconfirm --clean thpy.spec
```

产物为单文件 `dist\thpy.exe` 

## 数据目录

| 用途 | 路径 |
| --- | --- |
| 华为云凭据 | `%APPDATA%\thpy\config.ini` |
| 界面偏好 | `%APPDATA%\thpy\settings.ini` |
| 运行日志 | `%LOCALAPPDATA%\thpy\logs\thpy.log` |

从独立版 transpy 迁移无需任何操作 程序会自动读取 `%APPDATA%\transpy\config.ini` 

## 目录结构

```
main.py                     入口
thpy.spec                   打包配置
assets/images/logo.ico      图标
app/                        集成后的应用
docs/                       技术文档
dupy/ renamepy/ transpy/    集成前的独立版本
```

## 文档

- `docs/架构.md` 分层结构 页面模型 主题与线程模型 
- `docs/配置与数据.md` 目录约定 凭据优先级 迁移方式 
- `docs/开发与打包.md` 环境 打包要点 新增工具的方法 

集成前的三个独立版本仍保留在各自目录中 但后续改动以根目录的集成版本为准 

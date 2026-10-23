# thione

集合了日常可能会使用到的一些功能 

## 功能

- **图片查重**, 基于感知哈希(dHash)查找视觉上重复的图片 
- **批量重命名**, 根据填写的前缀, 批量重命名单个或多个文件夹内的文件 
- **划词翻译**, 对接多家翻译服务, 选中文本, 双击`Ctrl`翻译 
- **进制转换**, 常用进制之间的相互转换 
- **端口与占用**, 查看本机端口与文件的占用情况, 支持一键结束占用进程 
- **文件格式转换**, 常见音频格式的转换, 提取视频中的音频以及网易云ncm音频的转换 
- **串口助手**, 本机串口与外设之间的通讯以及UDP/TCP网络通讯

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 打包为`.exe`文件

```bash
pyinstaller --noconfirm --clean thione.spec
```

## 数据目录

| 用途           | 路径                                    |
| -------------- | --------------------------------------- |
| 翻译设置与凭据 | `%APPDATA%\thione\config.ini`           |
| 界面偏好       | `%APPDATA%\thione\settings.ini`         |
| 运行日志       | `%LOCALAPPDATA%\thione\logs\thione.log` |

## 文档

参考`docs/` 

## 许可

MIT

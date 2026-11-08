# Markdown改造

## 功能目标

把一个或多个 Markdown 及其引用的本地图片整理成可直接导入博客网站的 ZIP 包
原始 Markdown 与图片不会被修改

## 输入与输出

- 输入支持单个 Markdown 文件 多个文件或递归展开的文件夹
- 输出是 UTF-8 编码的 ZIP 包 多个 Markdown 重名时自动追加序号
- 本地图片复制到 `images/<Markdown 文件名>/` 目录 目录与图片名中的空格及 Markdown 特殊字符会替换为下划线 同一目录内的重名图片也会自动追加序号
- 远程图片 `data:` 地址和站点绝对路径保持不变

## 路径改写

- 支持 Markdown 行内图片 `![说明](图片路径)` 包括带标题的写法
- 支持 HTML 图片标签中的 `src` 属性
- 支持 frontmatter 中的 `cover_image` 字段
- 引用式图片和 Wiki 图片暂不处理 遇到时会中止并提示改成行内图片

## 缺失图片

默认情况下 任意本地图片不存在都会中止打包并列出缺失项
勾选忽略缺失图片后 不存在的图片保持原路径 其余内容继续写入 ZIP

## 实现结构

| 模块 | 职责 |
| --- | --- |
| `app/tools/markdown/page.py` | 文件选择 输出设置 后台任务与结果状态 |
| `app/tools/markdown/archiver.py` | 路径解析 图片收集 Markdown 改写与 ZIP 写入 |
| `app/tools/markdown/constants.py` | 页面文案与表格列定义 |

打包在后台线程执行 Markdown 与图片读写 界面线程只通过队列接收最终结果
ZIP 先写到同目录的临时文件 校验通过后再替换目标文件 失败时删除临时文件

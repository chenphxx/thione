# Markdown改造

## 功能目标

把一个或多个 Markdown 及其引用的本地图片整理成博客导入 ZIP 或原目录文档
两种模式都会保留原始 Markdown

## 输入与输出

- 输入支持单个 Markdown 文件 多个文件或递归展开的文件夹
- 用户可以选择是否生成压缩包
- 生成压缩包时输出 UTF-8 编码的 ZIP 多个 Markdown 重名时自动追加序号
- 不生成压缩包时在原 Markdown 所在目录输出 `<原文件名>-原文档.md`
- 图片目录是相对路径 默认为 `assets/images/` 用户可以自行修改
- ZIP 模式下每篇 Markdown 的图片复制到 `<图片目录>/<Markdown 文件名>/` 目录
- 文档模式下图片直接复制到每篇 Markdown 所在目录的 `<图片目录>/` 同一目录中的多篇文档会自动处理图片重名
- 目录与图片名中的空格及 Markdown 特殊字符会替换为下划线
- 远程图片 `data:` 地址和站点绝对路径保持不变

## 路径改写

- 支持 Markdown 行内图片 `![说明](图片路径)` 包括带标题的写法
- 支持 HTML 图片标签中的 `src` 属性
- 支持 frontmatter 中的 `cover_image` 字段
- 本地绝对路径和 `file:` 地址统一改写为相对于 Markdown 的 POSIX 路径 例如 `assets/images/example/photo.png`
- 引用式图片和 Wiki 图片暂不处理 遇到时会中止并提示改成行内图片

## 缺失图片

默认情况下 任意本地图片不存在都会中止改造并列出缺失项
勾选忽略缺失图片后 不存在的图片保持原路径 其余内容继续输出

## 实现结构

| 模块 | 职责 |
| --- | --- |
| `app/tools/markdown/page.py` | 文件选择 输出设置 后台任务与结果状态 |
| `app/tools/markdown/archiver.py` | 路径解析 图片收集 Markdown 改写 ZIP 写入与原目录输出 |
| `app/tools/markdown/constants.py` | 页面文案与表格列定义 |

改造在后台线程执行 Markdown 与图片读写 界面线程只通过队列接收最终结果
ZIP 先写到同目录的临时文件 校验通过后再替换目标文件 失败时删除临时文件
文档模式先写入同目录临时文件 再替换 `-原文档.md` 避免留下半写入文件

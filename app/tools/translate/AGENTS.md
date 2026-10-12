这是一个可扩展的多翻译服务 Provider 架构 

当前项目同时对接了多个第三方翻译 API, 不同供应商可能使用不同的调用方式, 例如: 

- 某些供应商提供 Python SDK
- 某些供应商没有 SDK，需要使用 requests 或 httpx 直接调用 HTTP API
- 不同供应商的请求参数、认证方式、HTTP Method 和响应结构可能不同

不要强制所有供应商采用相同的底层调用方式。SDK、requests、httpx 等都属于 Provider 的内部实现细节。

核心要求：

1. 在业务层定义统一的翻译接口，例如：

```python
translate(text: str, target_lang: str) -> str
```

业务代码不应该直接依赖任何具体供应商的 SDK、requests、HTTP URL 或供应商特有的响应结构。

2. 为不同翻译供应商分别实现 Provider，例如：

```text
Translator
├── UapiTranslator
├── SixtyTranslator
├── DeepLTranslator
└── ...
```

具体命名根据当前项目已有的代码结构和命名规范决定, 不要机械照搬 

3. 每个 Provider 自己负责：
- 第三方 API 的 URL
- HTTP Method
- 请求参数转换
- Authentication / API Key
- SDK 调用或 HTTP 调用
- 第三方响应解析
- 第三方异常转换

例如 UAPI 可以使用官方 Python SDK，而没有 SDK 的供应商可以使用 requests 或 httpx 

4. 不允许将第三方 API 的原始响应格式泄漏到业务层。

例如：

```python
uapi_result["data"]
```

```python
sixty_result["translation"]
```

```python
deepl_result["translations"][0]["text"]
```

这些解析逻辑应该存在于各自 Provider 内部 

业务层最终只处理统一的领域结果，例如：

```python
translated_text = translator.translate(
    text="こんにちは",
    target_lang="zh",
)
```

5. 设计一个统一的 TranslationService 或等价的服务层，用于：
- 选择当前使用的 Provider
- 对外提供统一的翻译能力
- 隔离业务代码和具体 Provider

业务代码不应该出现类似：

```python
if provider == "uapi":
    ...
elif provider == "60s":
    ...
```

这种供应商判断。

6. Provider 的选择应该尽可能通过配置完成，而不是散落在业务代码中。

例如可以考虑：

```text
TRANSLATION_PROVIDER=uapi
```

或者项目当前已有的配置机制。

请优先复用项目现有的配置、依赖注入、Service、Factory 等机制，不要在没有必要的情况下引入新的架构模式。

7. 统一异常处理。

不同供应商可能返回不同的错误格式，例如 HTTP 4xx、5xx、业务错误码、SDK 异常等。

Provider 内部应该将这些供应商特有异常转换成项目统一的翻译异常，例如：

```python
TranslationError
```

业务层不应该依赖：

```python
UapiError
requests.HTTPError
DeepLError
```

等第三方异常类型。

8. 对 Provider 接口进行类型约束。

如果项目使用 Python 类型注解，请保持完整的类型注解，并根据项目当前 Python 版本选择合适的写法。

9. 如果当前项目已经存在翻译相关代码：

先检查并复用现有实现，不要直接创建一套平行的翻译系统。

如果现有实现需要重构才能满足上述目标，可以进行重构 

工作要求：

开始修改前，先检查与本任务相关的项目结构、代码、配置文件以及 docs/ 文档，理解现有实现后再开始修改。

不要为了理解项目而无目的地读取整个项目，应根据当前任务范围优先检查相关目录、模块、配置和文档；如果任务涉及多个模块，再根据实际需要逐步扩大检查范围。

遵循项目现有的代码结构、命名规范、技术栈和实现习惯。

不要为了实现该功能而修改无关代码。

如果 docs/ 中已有文档与本次架构发生冲突，请同步更新相关文档，并保持原文档的结构和写作风格。

如果项目不存在 docs/，不要为了本任务主动创建 docs/。

在真正修改代码之前，先向我说明：

1. 当前项目中与翻译功能相关的代码在哪里
2. 当前已有的翻译实现是什么
3. 你计划采用什么 Provider 架构
4. 哪些代码会新增
5. 哪些代码会修改
6. 为什么这样设计
7. 是否存在需要我确认的架构决策

在我确认方案后再开始修改代码。

完成后说明：

1. 修改了哪些文件
2. 每个文件承担什么职责
3. Provider 如何扩展新的翻译供应商
4. 当前如何选择 Provider
5. 测试了哪些场景
6. 是否存在尚未解决的问题

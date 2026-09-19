# HYHQ 原生微信小程序 · 生态与识别演示

原生 JavaScript + JSDoc、WXML、WXSS，**没有第三方 npm 依赖、无需构建**。微信基础库基线固定为 `3.7.12`，Node 测试使用 Node.js 20 或更新版本。

## 已实现的范围

- 五个原生 tab：首页、生态导览、AI 识别、科普智游、我的。
- 统一 API 客户端、Bearer 会话、401 清理、超时与错误反馈、个人记录分页。
- 游客读取服务端的模拟天气/空气、地点、监测站、观测样例、文章与预设路线。
- 显式开发模拟登录；正式 `wx.login → auth/wechat/` 适配，不在前端保存 AppSecret。
- 昵称、主动选头像、浏览记录隐私开关、个人记录、退出与注销确认。
- 图片上传、私有缩略图鉴权下载、识别任务状态查询。读取服务端 `health.recognition` 展示当前模型范围、类别与版本；成功时展示最多三个候选及模型分数，不确定时明确提示无法确认。**没有模型时显示明确失败，不输出假预测。**
- 识别结果可以跳转关联的已发布科普，历史任务保留其模型版本，支持重新拍摄及删除任务/关联图片。

生态页面以 M1 可联调骨架为基础，识别页面支持 M3 模型协议。静态导览点位、历史趋势图、详细业务筛选与正式真机能力属于后续验收；装饰示意图无真实地理含义。当前不请求定位。所有页面业务数据均来自 API，后端不可用时显示错误，不自动注入本地假数据。

当前模型属于**五类花卉原型**，覆盖雏菊类、蒲公英类、蔷薇属花卉、向日葵类、郁金香类；具体以健康接口发布的范围为准。它不等于通用植物识别，校园实拍及开放集效果尚待验证。模型分数不是经过校准的正确概率。当前 v1 的验证集规则选出阈值 `0.0`，**未启用低分拒识**，图片质量合格时只给出候选参考，范围外对象也可能获得高分；过小或近纯色图片返回 `LOW_IMAGE_QUALITY`、`uncertain`。后续注册阈值大于零的版本时，低于该阈值才返回 `LOW_CONFIDENCE`。页面与历史结果均根据各自返回的阈值说明实际行为。

## 本地运行

1. 按项目根目录 README 启动后端，完成迁移、`seed_demo` 和模拟数据生成。确认 `http://127.0.0.1:8000/api/v1/health/` 可访问。
2. 在微信开发者工具中导入**本目录**。默认 `touristappid` 适用于初步页面开发；有账号后在工具“详情 → 基本信息”填写实际 AppID。AppSecret 只配置在后端。
3. 默认接口地址在 `config/index.js`：`http://127.0.0.1:8000/api/v1`。
4. 仅在本地调试时，把 `project.private.config.example.json` 复制为 `project.private.config.json`，关闭本地域名校验。该文件已忽略，公共配置默认保留 `urlCheck: true`。
5. 点击“编译”。“我的”页面勾选说明后使用“开发模拟登录”。该按钮要求前端 `development: true`，且健康接口明确返回 `dev_auth_enabled: true`。正式服务必须关闭服务端开发登录。
6. 启动后端识别任务工作进程后，上传可用 JPEG/PNG/WebP 图片。模型启用时读取真实 `recognized / uncertain` 结果；模型关闭时进入明确的 `MODEL_NOT_CONFIGURED` 失败状态。没有启动工作进程时可能保持排队。前端最多自动查询约 30 秒，之后提供手动刷新。

### 本地配置覆盖

直接编辑 `config/index.js` 即可切换地址与 `development` 开关，它仅含可公开配置。需要个人覆盖时，可复制 `config/local.example.js` 为已忽略的 `config/local.js`，再按示例说明修改 `config/index.js` 的导出行。缺省代码**不引用不存在的 local.js**，新检出即可编译；不要提交指向缺失文件的导出修改。

### 真机与正式环境

- 手机上 `127.0.0.1` 指向手机本身。局域网调试需把地址改为电脑的实际局域网 IP，并让后端监听对应地址、配置允许的 Host。
- 真机登录需要有效 AppID 和服务端微信配置；游客测试号无法替代正式微信身份验证。
- 正式接口使用 HTTPS；配置小程序 request、uploadFile、downloadFile 所需合法域名，恢复域名/TLS 校验。
- 微信平台头像选择、相册/相机以及上传行为涉及的隐私声明需在实际小程序账号中配置并验证。
- 当前没有完成开发者工具编译截图或真机验证。Node 测试不会验证微信渲染、基础库兼容性、主体资格或发布条件。

## 接口与权限约定

- 基础路径 `/api/v1`，资源路径以 `/` 结尾。
- 成功 `{data, meta?}`，错误 `{error:{code,message,details?},request_id?}`。
- token 只进入 `Authorization: Bearer …` 头，不出现在图片 URL、日志或跳转参数中。
- 私有头像通过 `wx.downloadFile` 携带认证获取临时文件，再显示到 `<image>`。绝不把 bearer token 拼接到 URL。
- 分页 next 和文件绝对地址必须与配置服务同源；异源 URL 会被拒绝，避免令牌发送到其他站点。
- 登录令牌存储在微信本地 storage。退出/注销成功后清除本地会话；后端退出失败会明确提示，不能把未撤销的服务器会话误报为退出成功。
- 天气/空气和观测的来源标识来自返回字段。官方预警 `not_connected` 与“没有预警”分开显示。AQI 未提供时不自行计算。
- 图像上传上限前端初筛 5 MiB；实际类型、尺寸、解码与归属仍由服务端验证。

## 验证

在本目录执行：

```sh
node --test tests/*.test.js
```

测试覆盖公共与私有请求、上传/下载、拒绝异源地址、会话过期、并发旧请求 401、错误响应、开发登录双开关、数据缺失/零值、预警未接入状态、账号变化后的个人数据清理，以及页面配置、WXML 标签/事件和 JS 语法检查。测试使用 transport mock，不接入微信账号。

识别测试另覆盖动态模型能力、游客查看范围、成功与不确定的区别、关闭模型兼容、Top3 展示、版本/阈值、非法分数、低置信度/低图质提示，以及取消选图、重复轮询、页面销毁、私有缩略图过期、识别记录删除后的缓存清理。

建议实际联调依次核对：游客浏览 → 模拟登录 → 修改昵称/头像 → 收藏与浏览记录 → 关闭浏览记录 → 图片上传任务 → 退出重登 → 注销及旧 token 失效。停止后端后检查错误/重试，不应出现伪造实况。

已启动本地开发 API 与识别工作进程时，可额外执行真实 HTTP 联调：

```sh
node tests/live-smoke.js
```

脚本使用原有小程序客户端和页面逻辑，通过 `wx` transport mock 调用实际服务；会创建并清理自己的开发账号、记录和图片。默认地址为 `http://127.0.0.1:8000/api/v1`，可用 `HYHQ_TEST_API` 覆盖。仅用于启用了开发登录的本地演示环境，不等于微信平台或真机验收。

启用真实模型后运行：

```sh
HYHQ_EXPECT_RECOGNITION=1 node tests/live-smoke.js
```

可以通过 `HYHQ_TEST_IMAGE=/absolute/path/to/image.jpg` 提供有权使用的测试图片。默认的一像素 PNG 仅验证上传、协议与不确定结果的呈现，**不能用于植物分类准确率评估**，即便模型给出高分也不代表开放集可靠。

## 官方参考

- [微信开发者工具项目配置](https://developers.weixin.qq.com/miniprogram/dev/devtools/projectconfig.html)
- [微信登录](https://developers.weixin.qq.com/miniprogram/dev/api/open-api/login/wx.login.html)
- [上传文件](https://developers.weixin.qq.com/miniprogram/dev/api/network/upload/wx.uploadFile.html)
- [下载文件](https://developers.weixin.qq.com/miniprogram/dev/api/network/download/wx.downloadFile.html)
- [微信官方小程序示例项目](https://github.com/wechat-miniprogram/miniprogram-demo)

# HYHQ 品牌素材

2026-09-21 根据用户提供的两张图片接入。

| 文件 | 用途 |
| --- | --- |
| `hyhq-logo-source.png` | 用户提供的“海晏河清智慧logo.png”，保留原始字节 |
| `small-icons-reference.png` | 用户提供的“小logo.png”，保留原始字节 |
| `icons-green-source.png` | 使用内置 imagegen 编辑出的六格绿色图标原图 |
| `../../miniprogram/assets/brand/hyhq-logo.jpg` | 主 Logo 运行资产，首页及个人中心；只作 JPEG 88 编码优化，无裁剪或改绘 |
| `../../miniprogram/assets/brand/icons-green.jpg` | 图标运行资产，JPEG 90 编码；通过原生 image 视窗选择单个格子，无远程图片请求 |

原图留在小程序目录之外，避免增加发布包体积。绿色图标精灵图为 1536 × 1024、3 列 × 2 行，每格 512 × 512。顺序：第一行首页、生态导览、AI 识别；第二行科普智游、我的、HYHQ 悬浮助手。空“栏框”通过入口卡和注册卡绿色细边框实现。底栏图标保留可见文字，中央 AI 圆形按钮尺寸加大。

## 编辑方法与最终提示词

采用 **内置 imagegen**，编辑目标是用户提供的小 Logo 图；未调用 CLI 或项目 DeepSeek Key。第一次透明底版本细节不清，未采用；最终使用浅米白底与深绿图形，保留叶片、罗盘、相机 AI、书本河流、人物及 HYHQ 字形。

最终发送的提示词：

> Create a CLEAN FLAT GREEN EDIT of these exact supplied six functional UI icons for production use. IMPORTANT: use FULLY OPAQUE UNIFORM IVORY BACKGROUND (#fffefa), NOT transparent. NO glow, NO haze, NO blur, NO shadows, NO gradients. Draw crisp sharply defined forest-green (#355f4e) shapes with ivory white interior cutouts so the leaf, compass needle, camera 'AI' letters, book river and profile leaf are clearly visible. Must preserve the original symbols. Output 1536x1024 3:2 sheet, EXACT uniform grid 3 columns x 2 rows, cells512x512, with no lines separating cells. Each cell's symbol centered and contained within 400x400 area. SIX symbols positions: top-left original HOUSE with LEAF doorway and sun circle; top-middle original COMPASS with compass ring, diagonal needle and mountains; top-right original CAMERA with large uppercase AI cutout, four scanner corner marks; bottom-left original OPEN BOOK with winding RIVER and rising SUN; bottom-middle original PERSON with LEAF; bottom-right original stylized HYHQ wordmark from floating assistant lower-right in reference. Keep source recognizable. Remove Chinese captions, omit empty square frame and black block. Remove circular button backgrounds, draw only the green functional emblems on consistent light ivory canvas. The output must look like sharp flat vector interface icons. No gradients, no glow, no shadows, no dark backgrounds. Preserve white/ivory inner spaces, never make the compass a solid green disk or camera blank.

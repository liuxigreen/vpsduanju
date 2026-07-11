# 封面 Prompt 指南（GPT/DALL-E 版）

> 基于322频道3000+视频蒸馏，特别是11张50万+播放爆款封面的实测分析。
> **核心发现：爆款封面不是"面部特写"，而是"场景叙事"——展示正在发生的冲突。**

---

## 画布规格

- **尺寸**：1280×720（16:9 横版）或 720×1280（9:16 竖版）
- **默认**：1280×720 横版（YouTube 桌面端封面）
- **安全区**：底部约15%留给文字叠加（深色渐变底），右下角留空（YouTube时间戳）

---

## 四层结构

### 第一层：底层（场景环境）

**作用**：交代故事发生在哪里，建立世界观。

**原则**：
- 场景必须与剧情直接相关（办公室=职场，街道=底层，豪宅=豪门）
- 不要全虚化——背景要有**可辨认的场景元素**，让观众一眼判断"这是什么故事"
- 光影方向统一，主光源从左上或右上打

**场景类型速查**：

| 题材 | 推荐场景 | 色调 |
|------|---------|------|
| 霸总/豪门 | 豪华办公室、豪宅客厅、直升机停机坪、黑色轿车旁 | 深蓝+金 |
| 甜宠/宠爱 | 温馨客厅、阳台逆光、雨中街道、婚礼现场 | 暖金+粉 |
| 重生/穿越 | 旧照片/旧场景+现代元素并置、时空交错感 | 冷灰→暖金渐变 |
| 复仇/打脸 | 法庭、公司大堂、宴会厅、医院走廊 | 冷蓝+红点缀 |
| 背叛/离婚 | 卧室、酒店走廊、雨夜街道 | 冷灰+暗红 |
| 系统/异能 | 虚拟空间、雷电天空、能量场围绕主角 | 深蓝+金光 |
| 末世/求生 | 废墟城市、破败建筑、浓雾街道 | 暗红+灰黑 |
| 古装/宫斗 | 宫殿、庭院、书房 | 红金+墨绿 |
| 校园 | 教室、操场、校门口 | 青绿+阳光 |

---

### 第二层：特效层（氛围与情绪）

**作用**：强化情绪张力，让画面"不普通"。

**常用特效**：

| 特效 | 用途 | prompt关键词 |
|------|------|-------------|
| 逆光/轮廓光 | 人物边缘发光，制造神圣感/神秘感 | rim light, backlit, silhouette edge glow |
| 雨/水滴 | 悲伤、绝望、戏剧性 | rain, water droplets, wet surface reflection |
| 粉尘/光斑 | 梦幻、回忆、时间感 | dust particles, bokeh light spots, lens flare |
| 玻璃碎片 | 冲突、破碎、真相揭露 | shattered glass, broken mirror fragments |
| 烟雾/雾气 | 神秘、危险、末世 | fog, smoke, haze, atmospheric mist |
| 闪电/能量 | 异能、觉醒、系统 | lightning, energy aura, electric glow |
| 火焰/火花 | 愤怒、复仇、激情 | fire, sparks, ember particles |

**规则**：
- 特效不能遮挡人物面部和关键道具
- 特效色彩必须与场景色调协调（不要在暖色场景里加蓝色闪电）
- 最多同时用2种特效，多了画面脏

---

### 第三层：人物/道具层（叙事核心）

**作用**：展示"谁在做什么"，传递核心冲突。

**构图原则（基于爆款实测）**：

❌ **不要**：面部占60%+的特写（实测爆款平均肤色仅10%）
✅ **要**：中景/中近景，展示人物的**姿态、站位、关系**

**人物站位模式**：

| 模式 | 适用场景 | prompt关键词 |
|------|---------|-------------|
| **对峙站位** | 背叛、冲突、审判 | two people facing each other, confrontation stance |
| **高低站位** | 身份反差、打脸 | one standing tall, one kneeling/bowed, power dynamic |
| **背对站位** | 离开、决裂、心碎 | back turned, walking away, emotional distance |
| **围观站位** | 全员震惊、打脸 | crowd watching, shocked expressions, public scene |
| **保护站位** | 甜宠、救赎 | protective embrace, shielded from danger, intimate proximity |
| **独白站位** | 重生、觉醒 | single figure, determined expression, dramatic lighting |

**人物细节**：
- 面部表情必须**外露且极端**：震惊/含泪/愤怒/得意/冷漠/绝望
- 服装传递身份：西装=CEO，工装=底层，婚纱=婚姻，军装=战神
- 肢体语言传递关系：推离=背叛，跪地=求饶，拥抱=宠爱，手指=指控

**道具规则**：
- 道具必须是**剧情核心道具**（离婚协议、结婚证、黑卡、DNA报告、武器）
- 道具要**大且清晰**，在手机缩略图上能辨认
- 道具与人物有**互动关系**（手持、掉落、对峙），不能只是"放在旁边"

---

### 第四层：文字层（信息传达）

**作用**：补充标题信息，强化点击理由。

**文字位置**：
- **底部15%**：深色渐变背景上放白色标题文字（2-4个中文字或3-5个英文词）
- **左上角**：半透明胶囊角标"FULL EPISODES"或"FULL MOVIE"

**文字规则**：
- 字数极简：2-4个中文字（如"逆袭""复仇""真相"）或3-5个英文词（如"Secret CEO""Reborn"）
- 颜色：白色为主，必须有深色投影确保可读性
- 字体：无衬线或手写体，不要宋体/楷体
- 位置：不遮挡人物面部和核心道具

**角标规则**：
- 左上角或右上角
- 半透明胶囊形状
- 文字："FULL EPISODES" / "FULL MOVIE" / "INDO DUB" / "ENG SUB"
- 不遮挡画面核心内容

---

## GPT/DALL-E Prompt 模板

### 完整prompt结构

```
[Scene description], [Character description with pose/expression], 
[Key props and their placement], [Lighting and color palette], 
[Special effects], [Composition notes], 
Text overlay area: bottom 15% dark gradient with white title text, 
top-left semi-transparent badge reading "FULL EPISODES", 
right-bottom corner blank for timestamp, 
16:9 aspect ratio, photorealistic, cinematic quality, 
East Asian features, not doll-like
```

### 示例：霸总身份反差

```
A humble delivery worker in worn uniform kneeling on the ground, looking up in shock, 
a tall CEO in black tailored suit standing above with arms crossed, cold expression, 
black luxury sedan and bodyguards in blurred background, 
office building entrance with glass doors reflecting city lights,
dramatic rim light from behind creating golden edge glow on CEO, 
cool blue shadows on the delivery worker, warm gold on the CEO,
scattered delivery packages on the wet ground, rain droplets visible,
Text overlay area: bottom 15% dark gradient with white title text, 
top-left semi-transparent capsule badge reading "FULL EPISODES",
right-bottom corner blank for YouTube timestamp,
16:9 landscape, photorealistic, cinematic depth of field,
East Asian features, natural realistic appearance
```

### 示例：重生复仇

```
A woman with determined cold expression standing in the center, 
wearing modern black dress, holding a red folder of evidence, 
behind her a ghostly translucent overlay of her past self in a wedding dress crying,
old family photos and a shattered clock floating in the air between past and present,
split background: left side dark gray rainy scene (past), right side golden warm light (present),
lightning crack between the two timelines,
crowd of people in the background with shocked expressions,
Text overlay area: bottom 15% dark gradient with white title text,
top-left semi-transparent capsule badge reading "FULL MOVIE",
right-bottom corner blank for YouTube timestamp,
16:9 landscape, photorealistic, cinematic composition,
East Asian features, dramatic temporal contrast lighting
```

### 示例：甜宠溺爱

```
A young woman in white lace dress sitting on a hospital bed, 
looking surprised and touched, tears forming in her eyes,
a handsome man in black suit leaning forward to gently wipe her tears,
warm golden sunset light streaming through the window behind them,
soft bokeh light spots floating in the air,
wedding ring and a bouquet of white roses on the bedside table,
protective intimate pose, his hand cupping her face gently,
Text overlay area: bottom 15% dark gradient with white title text,
top-left semi-transparent capsule badge reading "FULL EPISODES",
right-bottom corner blank for YouTube timestamp,
16:9 landscape, photorealistic, warm romantic lighting,
East Asian features, soft focus on background, sharp on faces
```

---

## 风格变体

| 风格 | 色调 | 光影 | 适用题材 |
|------|------|------|---------|
| **港风强对比** | 深蓝+金+红 | 高对比，硬光 | 复仇、打脸、背叛 |
| **韩风柔和** | 粉+白+浅蓝 | 柔光，逆光 | 甜宠、宠爱、初恋 |
| **暗黑戏剧** | 深紫+黑+暗红 | 低调光，强阴影 | 悬疑、末世、危险 |
| **明亮清新** | 白+浅绿+阳光 | 自然光，明亮 | 校园、青春、家庭 |

---

## 硬规则（必须遵守）

1. **人物面部清晰可见**：不需要占60%，但必须能看清表情
2. **核心道具可辨认**：在手机缩略图（320×180）上能认出是什么
3. **底部留文字区**：约15%高度，深色渐变，不放人脸
4. **右下角留空**：YouTube时间戳覆盖区
5. **左上角角标**：半透明胶囊，"FULL EPISODES"或其他版本标签
6. **16:9横版**：除非明确要求竖版
7. **East Asian features**：人物必须是东亚面孔
8. **Photorealistic**：写实风格，不要动漫/卡通/3D渲染

---

## 禁止事项

- ❌ 面部特写占画面60%以上（实测爆款不是这样的）
- ❌ 全虚化背景（需要有场景信息）
- ❌ 红圈/红箭头（low-quality信号）
- ❌ 黄底黑字（tabloid风格，low-quality信号）
- ❌ 超过5个文字（信息过载）
- ❌ 文字遮挡人脸或核心道具
- ❌ 孕检单/离婚协议等纸质道具占画面中心（太小看不清）
- ❌ 动漫/卡通/3D风格（YouTube短剧用写实）

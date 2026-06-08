# 整车任务工作流程总览
## 任务流程图
```plain
[init]
  │
  ▼
[auto_seeding]          ← 田间播种（3个播种物：大/中/小）
  │
  ▼
[target_shooting_detection]   ← 虫害侦察（路过时拍照，距离近成像更清晰）
  │
  ▼
[water_tower_task]       ← 水塔灌溉（2个水塔）
  │
  ▼
[target_shooting]        ← 射击除害（到达射击区后执行，弹药有限）
  │
  ▼
[crop_harvesting]        ← 作物采收（2种颜色×4个=8个果实）
  │
  ▼
[sort_and_store]         ← 分类储存（按颜色标签分拣到存储仓）
  │
  ▼
[get_order]              ← 获取订单 & 取货（取1个常用+1个随机订单的货物）
  │
  ▼
[order_delivery]        ← 订单配送（2个配送点）
```

## 各任务角色定位
| 序号 | 任务名称 | 核心功能 | 关键能力 |
| --- | --- | --- | --- |
| 1 | init | 系统初始化 | 硬件复位、里程计清零 |
| 2 | auto_seeding | 田间播种 | 视觉识别→机械臂抓取→移动播种 |
| 3 | target_shooting_detection | 虫害侦察 | 图像分析判断虫害严重程度 |
| 4 | water_tower_task | 水塔灌溉 | 多水块取水→分配到多个水塔 |
| 5 | target_shooting | 射击除害 | 根据侦察结果执行精准射击 |
| 6 | crop_harvesting | 作物采收 | 气泵吸取黄蓝球→放入储物架 |
| 7 | sort_and_store | 分类储存 | 按颜色标签分拣球到存放区 |
| 8 | get_order | 获取订单 | OCR识别→大模型解析→按序取货 |
| 8 | order_delivery | 订单配送 | 按楼号/姓名精准送货到格口 |


## 数据流向
```plain
target_shooting_detection() ──→ animal_list ──→ target_shooting()
                                               (打击列表)

crop_harvesting()          ──→ 储物架球 ──→ sort_and_store()
                                                 │
get_order()               ──→ order_list ───────┘
                                                │
order_delivery()  ◄────────────────────────────┘
  (货物 + 配送信息)
```

## 关键设计模式
### 1. 侦察-执行分离（时空分离）
虫害任务拆分为 `target_shooting_detection`（侦察）和 `target_shooting`（射击），两者在空间和时间上分离：

+ **侦察在去程路过时完成**：`target_shooting_detection` 在小车巡线经过虫害区域时执行（~1.45m），此时距离靶标较近，成像清晰，便于准确判断有害/有益动物
+ **射击在专门的射击区执行**：`target_shooting` 在小车到达射击区后执行（~3.0m），根据侦察结果精准击打有害动物

### 2. 记录-执行分离
`auto_seeding` 和 `water_tower_task` 都采用"先识别并记录所有目标位置，再统一执行"的策略，避免边走边识别带来的路径反复问题。

### 3. 数据驱动任务
`get_order` 使用文心一言大模型将 OCR 识别的自然语言标签解析为结构化 JSON，使订单内容可编程处理，无需硬编码标签顺序。

### 4. 全局状态共享
所有任务函数共享同一个 `my_car` 全局对象实例，通过里程计坐标、机械臂位置、储物架状态等隐式传递上下文，避免重复初始化。

## 场地任务分区
基于各任务的行驶距离和目标分布，场地大致分为以下区域：

```plain
起点 ──[auto_seeding]──[target_shooting_detection]──[water_tower]──[target_shooting]──[harvest]──[sort]──[order]── 终点
       播种区             虫害侦察              灌溉区              射击区           采收区    分拣区   配送区
                         (路过拍照)            (执行灌溉)        (到达射击区执行)
```

+ **虫害侦察在去程路过时完成**：小车巡线经过虫害区域时（播种区0.85m → 侦察区1.45m → 灌溉区2.0m），此时距离靶标较近，成像清晰，适合拍照识别。
+ **射击在专门的射击区执行**：完成灌溉后行驶到射击区，根据侦察结果精准射击。
+ 各任务通过 `lane_dis_offset` 累积行驶距离依次覆盖各区域。

## 调试建议
以下内容帮助大家从整体上把握调试节奏，合理安排调试顺序。

### 1. 调试的基本原则
+ **从局部到整体**：先单独调试每个任务，确认能跑通，再串联调试
+ **从简单到复杂**：先测试单个动作（如机械臂移动），再测试完整流程
+ **记录每次改动**：每次调整参数后记录效果，便于回溯

### 2. 推荐的调试顺序
```plain
第一步：init() 调试
    ↓
第二步：巡线基础功能（lane_dis_offset）
    ↓
第三步：视觉识别基础（move_to_detection_target）
    ↓
第四步：机械臂基础动作（吸取/释放）
    ↓
第五步：逐个任务调试
    - auto_seeding（播种）
    - target_shooting_detection（侦察）
    - water_tower_task（灌溉）
    - target_shooting（射击）
    - crop_harvesting（采收）
    - sort_and_store（分拣）
    - get_order + order_delivery（订单配送）
    ↓
第六步：完整流程串联
```

### 3. 里程计是定位的基础
全场所有任务都依赖里程计定位。如果里程计不准确，后续所有任务都会出现偏差。

调试时注意观察：每次巡线后，里程计读数是否符合预期？如果偏差较大，需要：

+ 检查场地摩擦力是否均匀
+ 考虑在关键位置加入视觉校正

### 4. 单任务独立运行
在 `car_start_2026.py` 中，可以注释掉不需要的任务，单独运行某一个：

```python
def main():
    init()
    # auto_seeding()      # 注释掉，先不运行
    # animal_list = target_shooting_detection()
    # water_tower_task()
    # target_shooting(animal_list)
    # crop_harvesting()
    # sort_and_store()
    # order_list = get_order()
    # order_delivery(order_list)
```

### 5. 打印关键变量
在调试时，可以在关键位置增加打印语句，观察程序运行状态：

```python
# 例如在 auto_seeding 函数中
print(f"当前里程计: {my_car.get_odometry()}")
print(f"识别结果: {cls_id}-{label}")
print(f"机械臂位置: {my_car.arm.x_get_position()}")
```

### 6. 比赛前的完整流程演练
在确认各任务都能正常运行后，进行完整的流程演练。注意：

+ 记录每个任务的执行时间
+ 观察各任务之间的衔接是否顺畅
+ 检查储物架是否在正确的时机抬起/放下

## 全局优化与调试建议
以下内容供大家结合实际情况进行调整和探索。

### 1. 统一配置管理
各任务函数中包含大量参数（距离、角度、时间等），可以考虑统一迁移到 `config_car.yml` 中集中管理：

```yaml
tasks:
  auto_seeding:
    x_length: 0.45
    dis: 0.55
    step: 0.15
  shooting:
    step: 0.16
    align_x: 0.2
    shoot_wait: 5
  harvesting:
    step_distance: 0.04
    ball_positions:
      ball_yellow: 0.0
      ball_blue: 0.06
  water_tower:
    water_num:
      water_l1: 1
      water_l2: 2
      water_l3: 3
  order:
    goods_mapping:
      青椒: h_qing_jiao
      蘑菇: h_mo_gu
```

这样在场地条件变化时，可以仅修改配置文件而无需改动代码逻辑。

### 2. 统一日志系统
程序中使用 `print()` 和 `beep()` 进行状态反馈。可以考虑引入分级日志系统，便于查看不同详细程度的信息：

```python
import logging

logger = logging.getLogger("car_task")
logger.setLevel(logging.DEBUG)

# 日志级别定义
# DEBUG: 视觉识别结果、机械臂坐标等详细数据
# INFO: 任务阶段切换、关键动作执行
# WARNING: 识别失败、重试等非致命异常
# ERROR: 任务无法继续执行

logger.debug(f"识别结果: {cls_id}-{label}, 里程计: {my_car.get_odometry()}")
logger.info(f"开始执行水塔灌溉，共 {len(tower_water)} 个水塔")
logger.warning(f"水块 {i} 识别失败，第 {attempt} 次重试")
```

### 3. 巡线速度的层级化管理
程序中所有 `lane_dis_offset` 使用 `speed=0.3`。可以考虑定义不同速度层级，适应不同场景：

```python
LANE_SPEED = 0.3       # 常规巡线速度
LANE_SPEED_FAST = 0.5  # 快速巡线（无障碍区域）
LANE_SPEED_SLOW = 0.15 # 慢速巡线（精确定位区域）
```

在场地测试中，可以根据不同区域的精度需求灵活选用。

### 4. 机械臂预设姿态封装
多个任务中反复出现相似的机械臂姿态设置。可以考虑将这些姿态封装为预设配置：

```python
ARM_PRESETS = {
    "detect": {"x": 0.0, "y": 0.02, "arm": "RIGHT", "hand": "UP"},
    "pickup_low": {"x": 0.0, "y": 0.2, "arm": "LEFT", "hand": "DOWN"},
    "pickup_high": {"x": 0.0, "y": 0.17, "arm": "LEFT", "hand": "DOWN"},
    "store": {"arm": "LEFT", "hand": -70},
    "rest": {"x": 0.3, "y": 0.2, "arm": "LEFT", "hand": "UP"},
}

def set_arm_preset(preset_name):
    preset = ARM_PRESETS.get(preset_name)
    if preset:
        my_car.arm.set_arm_pose(**preset)

set_arm_preset("detect")
```

### 5. 任务流程的可拆解执行
在调试阶段，往往只需要单独运行某个任务。可以考虑在 `main()` 中增加任务分片控制：

```python
def main(task_slice=None):
    """task_slice 指定运行哪个任务，None 表示运行全部"""
    init()
    if task_slice is None or task_slice == "seeding":
        auto_seeding()
    # ...
```

这样可以单独调试某个环节，不必每次都跑完整流程。

### 6. 视觉模型的自主训练
程序中使用的目标检测模型（如 `task2026` 任务检测模型、`front_model2` 巡线模型等）均为 Paddle 框架训练。大家可以针对实际场地数据进行针对性训练，进一步提升识别准确率。

**不推荐训练的模型**：`OCR` 模型使用文心 OCR 服务，推荐使用我们提供的现成配置，已足够准确和快速，无需自行训练。

**模型视角差异说明**：

+ 场地中不同任务的视觉目标存在于不同的摄像头视角下——有的目标在侧面摄像头视野中成像更清晰，有的在正面摄像头下更易识别。大家在训练时需要注意采集正确视角下的图像数据。

训练完成后，只需替换 `config_car.yml` 中 `infer_cfg` 对应的 `model_dir` 路径即可使用新模型。

# Algorithms

## 功能说明

Algorithms 目录包含多个深度学习算法模块，每个模块都是独立的。一般支持以下核心功能：
- **本地推理**：直接使用 Python 脚本进行单张或批量图像推理
- **服务端推理**：启动服务器提供 HTTP API 接口
- **客户端调用**：通过客户端脚本向服务器发送请求并处理结果

## 现有模块

| 模块 | 功能 | 文档 |
|------|------|------|
| `xsam` | 多任务视觉-语言模型，支持图像分割任务 | [README.md](xsam/README.md) |
| `qwen3_vl` | 视觉-语言模型，支持图像理解和目标检测 | [README.md](qwen3_vl/README.md) |
| `sam2_interseg` | SAM2 交互式分割 | [README.md](sam2_interseg/README.md) |
| `yoloe_vp` | YOLO-E 视觉提示检测 | [README.md](yoloe_vp/README.md) |

## 模块结构

每个算法模块通常包含以下文件结构：

```
algorithms/
├── [algorithm]/
│   ├── [algo]_inferface.py           # 本地推理接口（继承 BaseInterface）
│   ├── [algo]_interface_config.yaml  # 本地推理接口配置文件
│   ├── [algo]_server.py              # 服务端（FastAPI 或启动脚本）
│   ├── [algo]_server_config.yaml     # 服务器配置文件（可选）
│   ├── [algo]_client.py              # 客户端（继承 BaseClient）
│   ├── [algo]_client_config.yaml     # 客户端配置文件
│   └── README.md                     # 模块使用文档
├── base_interface.py                 # 基础接口类
├── base_client.py                    # 基础客户端类
└── README.md                         # 本文件
```

## 文件说明

### 核心文件类型

| 文件类型 | 命名规范 | 功能说明 |
|---------|--------|--------|
| 推理接口 | `[algo]_inferface.py` | 实现模型推理逻辑，继承 `BaseInterface`，支持单张/批量图像处理，可独立运行 |
| 接口配置 | `[algo]_interface_config.yaml` | YAML 格式的本地推理接口配置文件，包含模型路径、参数等 |
| 服务端 | `[algo]_server.py` | 服务器实现，可以是 FastAPI 服务器或启动脚本 |
| 服务器配置 | `[algo]_server_config.yaml` | YAML 格式的服务器配置文件，包含网络配置和模型配置 |
| 客户端 | `[algo]_client.py` | HTTP 客户端，继承 `BaseClient`，向服务器发送请求并处理响应 |
| 客户端配置 | `[algo]_client_config.yaml` | YAML 格式的客户端配置文件，包含服务器地址、端口等 |
| 工具函数 | `[algo]_utils.py` | 模块特定的工具函数（可选） |
| 文档 | `README.md` | 模块使用文档，说明功能、参数、使用方法 |

### 基础类

- **`BaseInterface`**：所有本地推理接口的基类，提供统一的配置加载接口（支持 YAML 配置文件或配置字典）
- **`BaseClient`**：所有客户端的基类，提供统一的配置加载接口（支持 YAML 配置文件或配置字典）

## 使用工作流

### 方案一：本地推理（单机）

适用于开发调试、小规模推理任务。

```bash
cd algorithms/[algorithm]/
python [algo]_inferface.py \
  --image /path/to/image.jpg \
  --interface_config_path /path/to/[algo]_interface_config.yaml \
  [其他参数]
```

**优点：** 快速、无网络开销、适合调试
**缺点：** 单进程、GPU 资源利用率低

### 方案二：客户端-服务端（分布式）

适用于生产环境、多并发、跨机器调用。

#### 步骤 1：启动服务器

```bash
cd algorithms/[algorithm]/
python [algo]_server.py \
  --config_path /path/to/[algo]_server_config.yaml
```

**注意：** 不同模块的服务器启动方式可能不同，请参考各模块的 `README.md` 文档。

#### 步骤 2：客户端发送请求

```bash
cd algorithms/[algorithm]/
python [algo]_client.py \
  --config_path /path/to/[algo]_client_config.yaml \
  --image_file /path/to/image.jpg \
  --prompt "your prompt" \
  [其他参数]
```

**优点：** 支持并发、资源隔离、易于扩展、支持多机调用
**缺点：** 网络开销、需要部署服务器

## 配置管理

所有模块使用 YAML 格式的配置文件，支持以下方式：

1. **配置文件路径**：通过 `config_path` 参数指定 YAML 配置文件
2. **配置字典**：通过 `config` 参数直接传入配置字典
3. **配置覆盖**：配置字典可以覆盖配置文件中的设置

**示例：**
```python
# 方式1：使用配置文件
interface = AlgoInterface(config_path="./config.yaml")

# 方式2：使用配置字典
interface = AlgoInterface(config={"model_path": "/path/to/model"})

# 方式3：配置文件 + 覆盖
interface = AlgoInterface(
    config_path="./config.yaml",
    config={"model_path": "/path/to/other_model"}  # 覆盖配置文件中的 model_path
)
```

## 常见问题

**Q: 如何修改推理超时时间？**
A: 在客户端配置文件中设置 `timeout` 参数，或在客户端代码中修改。

**Q: 如何在不同模块间切换？**
A: 每个模块都有独立的配置文件和脚本，直接切换到对应目录使用即可。

**Q: 配置文件格式是什么？**
A: 使用 YAML 格式，支持嵌套结构和注释。参考各模块的 `README.md` 查看具体配置项。

## 扩展新算法

1. 创建新目录 `algorithms/[new_algo]/`
2. 实现 `[algo]_inferface.py`（继承 `BaseInterface`，实现推理逻辑）
3. 创建 `[algo]_interface_config.yaml`（接口配置文件）
4. 创建 `[algo]_server.py`（FastAPI 服务端或启动脚本）
5. 创建 `[algo]_server_config.yaml`（服务器配置文件，可选）
6. 创建 `[algo]_client.py`（继承 `BaseClient`，实现 HTTP 客户端）
7. 创建 `[algo]_client_config.yaml`（客户端配置文件）
8. 编写 `README.md`（使用文档，参考 `xsam/README.md`）

**相关通用函数：**
- `utils/server_client_utils.py`：服务器和客户端工具函数
- `utils/logger.py`：日志工具
- `algorithms/base_interface.py`：基础接口类
- `algorithms/base_client.py`：基础客户端类

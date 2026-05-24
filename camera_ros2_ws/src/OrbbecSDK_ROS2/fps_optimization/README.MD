# ROS2 相机FPS优化方案
本文档提供两种ROS2下提升相机FPS的通信层优化方案，分别基于zenoh通信中间件和FastDDS共享内存（SHM）配置，可根据实际环境选择使用。

## 方案1：基于zenoh通信中间件优化
### 适用场景
需要低延迟、高吞吐的跨节点/跨设备相机数据传输场景，适配ROS2 Jazzy版本。

### 操作步骤
1. 安装zenoh相关依赖包
sudo apt install ros-jazzy-rmw-zenoh-cpp
2. 配置环境变量，指定使用zenoh作为RMW实现
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
3. 启动zenoh后台服务
ros2 run rmw_zenoh_cpp rmw_zenohd
4. 正常启动相机相关ROS2节点即可

## 方案2：基于FastDDS共享内存（SHM）优化
### 适用场景
单设备内多ROS2节点间的相机数据传输，通过共享内存替代网络套接字，大幅降低本地通信延迟。

### 操作步骤
1. 拷贝hm_fastdds.xml文件到$HOME目录
2. 配置环境变量，指定FastDDS为RMW并加载共享内存配置
# 指定RMW实现为FastDDS
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
# 加载自定义FastDDS配置文件
export FASTRTPS_DEFAULT_PROFILES_FILE=$HOME/shm_fastdds.xml
# 启用从XML文件读取QoS配置
export RMW_FASTRTPS_USE_QOS_FROM_XML=1
3. 正常启动相机相关ROS2节点即可

## 验证优化效果
启动相机节点后，可通过以下命令查看FPS变化：
# 查看相机话题发布频率
ros2 topic hz /camera/image_raw

## 注意事项
1. 方案1仅适配ROS2 Jazzy版本，Humble/Iron版本需手动编译rmw_zenoh_cpp源码；
2. 方案2为本地通信优化，跨设备传输时无效果，需配合网络配置使用；
3. 两种方案互斥，使用时仅需配置其中一种的环境变量即可；
4. 配置完成后，若需恢复默认ROS2通信配置，执行以下命令：
unset RMW_IMPLEMENTATION FASTRTPS_DEFAULT_PROFILES_FILE RMW_FASTRTPS_USE_QOS_FROM_XML
5. 若共享内存配置生效失败，检查FastDDS版本（建议≥2.6.0），并确保无其他FastDDS配置文件覆盖当前设置。

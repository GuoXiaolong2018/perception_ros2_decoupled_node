#!/usr/bin/env bash
# Install NVIDIA Container Toolkit and configure Docker for --gpus all
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "请使用 sudo 运行: sudo bash $0"
  exit 1
fi

echo "==> 检查 NVIDIA 驱动..."
if ! command -v nvidia-smi &>/dev/null; then
  echo "错误: 未找到 nvidia-smi，请先安装 NVIDIA 驱动。"
  exit 1
fi
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader

KEYRING=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
LIST=/etc/apt/sources.list.d/nvidia-container-toolkit.list

echo "==> 添加 NVIDIA Container Toolkit 软件源..."
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o "${KEYRING}"
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed "s#deb https://#deb [signed-by=${KEYRING}] https://#g" \
  > "${LIST}"

echo "==> 安装 nvidia-container-toolkit..."
apt-get update
apt-get install -y nvidia-container-toolkit

echo "==> 配置 Docker 运行时..."
nvidia-ctk runtime configure --runtime=docker

echo "==> 重启 Docker..."
systemctl restart docker

echo "==> Docker 运行时:"
docker info | grep -i runtime || true

echo "==> 验证 GPU 容器访问..."
docker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi

echo ""
echo "安装完成。现在可以使用 docker run --gpus all ..."

#!/usr/bin/env bash
# AI Budget Guard — 快速安装脚本
# Usage: curl -fsSL https://raw.githubusercontent.com/RavenSS213/ai-budget-guard/main/install.sh | bash

set -e

REPO="https://github.com/RavenSS213/ai-budget-guard"
INSTALL_DIR="${HOME}/.budget-guard"

echo "📦 安装 AI Budget Guard..."
echo "  目标: ${INSTALL_DIR}"

# 下载仓库
if command -v git &>/dev/null; then
    git clone --depth 1 "${REPO}.git" "${INSTALL_DIR}" 2>/dev/null || {
        echo "  仓库已存在，更新中..."
        cd "${INSTALL_DIR}" && git pull
    }
else
    mkdir -p "${INSTALL_DIR}"
    curl -fsSL "${REPO}/archive/refs/heads/main.tar.gz" | tar xz --strip=1 -C "${INSTALL_DIR}"
fi

chmod +x "${INSTALL_DIR}/scripts/budget.py"

# 添加到 PATH
if ! grep -q "budget-guard" "${HOME}/.bashrc" 2>/dev/null; then
    echo "export PATH=\"\$PATH:${INSTALL_DIR}/scripts\"" >> "${HOME}/.bashrc"
    echo "alias budget-guard='python3 ${INSTALL_DIR}/scripts/budget.py'" >> "${HOME}/.bashrc"
    echo "  已添加到 .bashrc (重开终端或 source ~/.bashrc 生效)"
fi

echo ""
echo "✅ 安装完成!"
echo "  使用: budget-guard check '{\"model\":\"deepseek/deepseek-v4-flash\",\"tokens_in\":150000}'"
echo "  查看: budget-guard report"
echo "  冻结: budget-guard freeze"
echo ""
echo "📖 文档: ${REPO}"

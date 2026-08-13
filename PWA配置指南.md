# 📱 PWA 配置指南 - 3D智能决策

## ✅ 已完成的配置

### 1. 生成的文件

| 文件 | 路径 | 说明 |
|------|------|------|
| `manifest.json` | `/static/manifest.json` | PWA 应用清单，定义应用名称、图标、启动方式 |
| `service-worker.js` | `/static/service-worker.js` | Service Worker，用于缓存页面资源 |
| `icon-192.png` | `/static/icons/icon-192.png` | 192x192 应用图标 |
| `icon-512.png` | `/static/icons/icon-512.png` | 512x512 应用图标 |
| `run_app.py` | `/run_app.py` | PWA 增强启动脚本 |

### 2. 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `app.py` | 注入 PWA 元标签、Service Worker 注册脚本、隐藏 Streamlit UI 的 CSS |
| `.streamlit/config.toml` | 禁用 CORS、关闭使用统计收集 |

---

## 🚀 如何启动

```bash
python run_app.py
```

这将同时启动：
- 静态文件服务器（端口 8080）- 提供 manifest.json、service-worker.js 和图标
- Streamlit 应用（端口 8501）- 主应用

---

## 📲 添加到主屏幕（手机端）

### Android (Chrome)
1. 用 Chrome 浏览器访问 `http://你的IP:8501`
2. 点击浏览器菜单（⋮）
3. 选择"添加到主屏幕"或"安装应用"
4. 确认安装，应用图标将出现在桌面上

### iOS (Safari)
1. 用 Safari 浏览器访问 `http://你的IP:8501`
2. 点击底部分享按钮（⎋）
3. 滚动找到"添加到主屏幕"
4. 点击"添加"，应用图标将出现在桌面上

---

## 🎨 已隐藏的 Streamlit UI 元素

通过 CSS 注入，以下元素已被隐藏：

- ✅ 顶部菜单栏（`#MainMenu`）
- ✅ 页面标题栏（`header`）
- ✅ 底部"使用 Streamlit 构建"标识（`footer`）
- ✅ 部署按钮（`.stDeployButton`）
- ✅ 工具栏（`[data-testid="stToolbar"]`）
- ✅ 装饰元素（`[data-testid="stDecoration"]`）
- ✅ 状态组件（`[data-testid="stStatusWidget"]`）

---

## 🔧 PWA 特性

| 特性 | 配置值 | 说明 |
|------|--------|------|
| 应用名称 | 3D智能决策 | 显示在主屏幕和启动画面 |
| 短名称 | 3D决策 | 图标下方显示的名称 |
| 显示模式 | standalone | 全屏运行，无浏览器 UI |
| 主题色 | #1a1a2e | 状态栏和任务栏颜色 |
| 背景色 | #0f0f23 | 启动画面背景色 |
| 屏幕方向 | portrait-primary | 锁定竖屏模式 |

---

## ⚠️ 注意事项

1. **HTTPS 要求**：Service Worker 需要 HTTPS 环境才能正常工作。本地开发时 `localhost` 可以正常使用，但部署到生产环境时需要配置 HTTPS。

2. **静态文件路径**：Streamlit 的静态文件服务有限制，因此使用 `run_app.py` 同时启动独立的静态文件服务器。

3. **缓存更新**：修改 `service-worker.js` 中的 `CACHE_NAME` 版本号可以强制更新缓存。

4. **iOS 限制**：iOS Safari 对 PWA 的支持有限，部分功能可能不如 Android 完善。

---

## 📋 验证 PWA 是否生效

1. 打开 Chrome DevTools（F12）
2. 进入 **Application** 标签
3. 检查 **Manifest** - 应显示应用信息
4. 检查 **Service Workers** - 应显示已注册并激活
5. 点击 **Lighthouse** 进行 PWA 审计
"""
PWA 静态文件代理服务器
通过 Streamlit 组件直接提供 manifest.json、service-worker.js 和图标文件
"""
import streamlit as st
import streamlit.components.v1 as components
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def serve_pwa_files():
    """在 Streamlit 中注入 PWA 所需的静态文件"""
    pass

def get_manifest_content():
    manifest_path = os.path.join(BASE_DIR, 'manifest.json')
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            return f.read()
    return None

def get_service_worker_content():
    sw_path = os.path.join(BASE_DIR, 'service-worker.js')
    if os.path.exists(sw_path):
        with open(sw_path, 'r', encoding='utf-8') as f:
            return f.read()
    return None

def get_icon_content(icon_name):
    icon_path = os.path.join(BASE_DIR, 'static', 'icons', icon_name)
    if os.path.exists(icon_path):
        with open(icon_path, 'rb') as f:
            return f.read()
    return None
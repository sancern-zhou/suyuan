#!/usr/bin/env python3
"""
使用代理初始化GEE
"""

import os

# 设置项目ID和代理
PROJECT_ID = 'gen-lang-client-0761286422'
os.environ['GOOGLE_CLOUD_PROJECT'] = PROJECT_ID

# 设置代理（请替换为您的代理地址）
os.environ['HTTP_PROXY'] = 'http://your-proxy:port'
os.environ['HTTPS_PROXY'] = 'http://your-proxy:port'

import ee

try:
    ee.Initialize(project=PROJECT_ID)
    print("✅ GEE初始化成功 (使用代理)")
except Exception as e:
    print(f"❌ 失败: {e}")

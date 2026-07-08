#!/usr/bin/env python3
"""Add DeepSeek API key to hermes config"""
import yaml

config_path = '/Users/liuxi/.hermes/config.yaml'

with open(config_path) as f:
    cfg = yaml.safe_load(f)

if 'providers' not in cfg:
    cfg['providers'] = {}

cfg['providers']['edgefn'] = {
    'provider': 'deepseek',
    'base_url': 'https://api.edgefn.net/v1',
    'api_key': '***我用 hermes config set 直接写入。
    'timeout': 60,
}

with open(config_path, 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

print("✅ edgefn provider added to hermes config")

# Verify
with open(config_path) as f:
    cfg2 = yaml.safe_load(f)
edgefn = cfg2.get('providers', {}).get('edgefn', {})
print(f"provider: {edgefn.get('provider')}")
print(f"base_url: {edgefn.get('base_url')}")
print(f"api_key: {edgefn.get('api_key', '')[:12]}...{edgefn.get('api_key', '')[-4:]}")

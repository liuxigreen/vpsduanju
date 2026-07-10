#!/usr/bin/env python3
"""
代码库审计 → 推送到 ClickUp Doc
供 AI Agent 读取，做全方位项目审核

用法：
  python3 scripts/sync_code_audit_to_clickup.py
  python3 scripts/sync_code_audit_to_clickup.py --dry-run  # 只生成不推送
"""

import os
import subprocess
import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
API_BASE = "https://api.clickup.com/api/v2"

# ClickUp API token (从环境变量读取)
TOKEN = os.environ.get("CLICKUP_API_TOKEN", "")
FOLDER_ID = os.environ.get("CLICKUP_FOLDER_ID", "")  # 存放审计文档的文件夹


def run(cmd, **kwargs):
    """执行shell命令"""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=ROOT, **kwargs)
    return result.stdout.strip()


def count_lines():
    """统计代码行数"""
    files = list(Path(ROOT).rglob("*.py"))
    files = [f for f in files if "venv" not in str(f) and "__pycache__" not in str(f)]

    total = 0
    by_dir = defaultdict(lambda: {"files": 0, "lines": 0, "blank": 0, "comment": 0})

    for f in files:
        rel = f.relative_to(ROOT)
        top_dir = rel.parts[0] if len(rel.parts) > 1 else "root"

        try:
            content = f.read_text(errors="ignore")
            lines = content.split("\n")
            total += len(lines)

            by_dir[top_dir]["files"] += 1
            by_dir[top_dir]["lines"] += len(lines)
            by_dir[top_dir]["blank"] += sum(1 for l in lines if l.strip() == "")
            by_dir[top_dir]["comment"] += sum(
                1 for l in lines if l.strip().startswith("#") or l.strip().startswith('"""') or l.strip().startswith("'''")
            )
        except Exception:
            pass

    return total, by_dir


def find_complex_functions():
    """找出复杂度高的函数（行数>50）"""
    import ast

    results = []
    files = list(Path(ROOT).rglob("*.py"))
    files = [f for f in files if "venv" not in str(f) and "__pycache__" not in str(f) and "oneoff" not in str(f)]

    for f in files:
        try:
            source = f.read_text(errors="ignore")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    end = getattr(node, "end_lineno", None)
                    if end:
                        lines = end - node.lineno
                        if lines > 50:
                            rel = str(f.relative_to(ROOT))
                            results.append({
                                "file": rel,
                                "function": node.name,
                                "lines": lines,
                                "start": node.lineno,
                            })
        except Exception:
            pass

    return sorted(results, key=lambda x: -x["lines"])


def find_todos():
    """找出TODO/FIXME/HACK"""
    results = []
    for line in run("grep -rn 'TODO\\|FIXME\\|HACK\\|XXX' --include='*.py' . | grep -v venv | grep -v __pycache__").split("\n"):
        if line.strip():
            parts = line.split(":", 2)
            if len(parts) >= 3:
                results.append({
                    "file": parts[0].lstrip("./"),
                    "line": parts[1],
                    "text": parts[2].strip(),
                })
    return results


def find_error_handling():
    """检查异常处理模式"""
    bare_except = run("grep -rn 'except:' --include='*.py' . | grep -v venv | wc -l")
    broad_except = run("grep -rn 'except Exception' --include='*.py' . | grep -v venv | wc -l")
    total_try = run("grep -rn 'try:' --include='*.py' . | grep -v venv | wc -l")
    return {
        "total_try": int(total_try) if total_try.isdigit() else 0,
        "bare_except": int(bare_except) if bare_except.isdigit() else 0,
        "broad_except": int(broad_except) if broad_except.isdigit() else 0,
    }


def find_hardcoded():
    """检查硬编码问题"""
    patterns = {
        "API Keys": r"(api_key|apikey|secret|password)\s*=\s*['\"][^'\"]{8,}",
        "IP地址": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
        "端口号": r"port\s*=\s*\d{4,5}",
    }
    results = {}
    for name, pattern in patterns.items():
        matches = run(f"grep -rn '{pattern}' --include='*.py' . | grep -v venv | grep -v __pycache__ | head -10")
        if matches:
            results[name] = [m.split(":", 2)[0:2] for m in matches.split("\n") if m.strip()][:5]
    return results


def check_imports():
    """检查导入问题"""
    unused = run("grep -rn '^import \\|^from ' --include='*.py' . | grep -v venv | wc -l")
    return {"total_imports": int(unused) if unused.isdigit() else 0}


def git_stats():
    """Git统计"""
    last_commit = run("git log -1 --pretty=format:'%h %s (%cr)'")
    total_commits = run("git rev-list --count HEAD")
    contributors = run("git shortlog -sn --no-merges | head -5")
    return {
        "last_commit": last_commit,
        "total_commits": total_commits,
        "contributors": contributors,
    }


def generate_report():
    """生成完整审计报告"""
    total_lines, by_dir = count_lines()
    complex_funcs = find_complex_functions()
    todos = find_todos()
    error_handling = find_error_handling()
    hardcoded = find_hardcoded()
    imports = check_imports()
    git = git_stats()

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    report = f"""# 代码库审计报告 - {now}

## 📊 总览
| 指标 | 值 |
|------|-----|
| 总代码行数 | {total_lines:,} |
| Python文件数 | {sum(d['files'] for d in by_dir.values())} |
| Git提交数 | {git['total_commits']} |
| 最近提交 | {git['last_commit']} |

## 📁 目录结构
| 目录 | 文件数 | 代码行 | 注释行 |
|------|--------|--------|--------|
"""
    for dir_name, stats in sorted(by_dir.items(), key=lambda x: -x[1]["lines"]):
        report += f"| {dir_name} | {stats['files']} | {stats['lines']:,} | {stats['comment']} |\n"

    report += f"""
## ⚠️ 复杂函数（>50行，需要重构）
| 文件 | 函数 | 行数 |
|------|------|------|
"""
    for func in complex_funcs[:10]:
        report += f"| `{func['file']}` | {func['function']}() | {func['lines']}行 |\n"
    if not complex_funcs:
        report += "| ✅ 无 | - | - |\n"

    report += f"""
## 🔧 异常处理
| 指标 | 值 |
|------|-----|
| try块总数 | {error_handling['total_try']} |
| 裸except | {error_handling['bare_except']} ⚠️ |
| 宽泛except | {error_handling['broad_except']} |

"""
    if error_handling['bare_except'] > 0:
        report += "> ⚠️ 存在裸 `except:` 语句，会吞掉所有异常，建议改为具体异常类型\n\n"

    report += f"""
## 📝 TODO/FIXME（{len(todos)}个）
"""
    for t in todos[:15]:
        report += f"- `{t['file']}:{t['line']}` — {t['text']}\n"
    if not todos:
        report += "- ✅ 无\n"

    report += f"""
## 🔍 硬编码检查
"""
    for category, items in hardcoded.items():
        report += f"\n**{category}**:\n"
        for file, line in items:
            report += f"- `{file}` L{line}\n"
    if not hardcoded:
        report += "- ✅ 未发现明显硬编码\n"

    report += f"""
## 👥 贡献者
```
{git['contributors']}
```

## 🎯 审核建议（AI Agent请参考）

### 高优先级
1. 清理 {error_handling['bare_except']} 个裸except语句
2. 重构 {len(complex_funcs)} 个超过50行的函数
3. 解决 {len([t for t in todos if 'FIXME' in t['text'] or 'HACK' in t['text']])} 个FIXME/HACK

### 中优先级
1. 完成 {len(todos)} 个TODO项
2. 检查硬编码的配置项，移到环境变量或配置文件
3. 添加缺失的类型注解

### 低优先级
1. 统一代码风格（建议用 ruff check）
2. 补充关键函数的docstring
3. 清理未使用的import
"""
    return report


def push_to_clickup(report, title, folder_id, dry_run=False):
    """推送到ClickUp Doc"""
    if dry_run:
        print("=== DRY RUN ===")
        print(f"Title: {title}")
        print(f"Would push to folder: {folder_id}")
        print(f"Report length: {len(report)} chars")
        output_path = ROOT / "output" / "code_audit_report.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report)
        print(f"Saved to: {output_path}")
        return True

    if not TOKEN:
        print("❌ 未设置 CLICKUP_API_TOKEN 环境变量")
        print("设置方法: export CLICKUP_API_TOKEN=your_token_here")
        return False

    import urllib.request
    import urllib.error

    # 先创建Doc
    create_url = f"{API_BASE}/doc"
    payload = json.dumps({
        "name": title,
        "parent": folder_id if folder_id else None,
    }).encode()

    req = urllib.request.Request(create_url, data=payload, method="POST", headers={
        "Authorization": TOKEN,
        "Content-Type": "application/json",
    })

    try:
        with urllib.request.urlopen(req) as resp:
            doc_data = json.loads(resp.read())
            doc_id = doc_data.get("id")
            print(f"✅ Doc创建成功: {doc_id}")

            # 更新Doc内容
            update_url = f"{API_BASE}/doc/{doc_id}"
            update_payload = json.dumps({"content": report}).encode()
            req2 = urllib.request.Request(update_url, data=update_payload, method="PUT", headers={
                "Authorization": TOKEN,
                "Content-Type": "application/json",
            })
            with urllib.request.urlopen(req2) as resp2:
                print(f"✅ Doc内容更新成功")
                return True

    except urllib.error.HTTPError as e:
        print(f"❌ API错误: {e.code} {e.read().decode()}")
        return False


if __name__ == "__main__":
    import sys
    dry_run = "--dry-run" in sys.argv

    print("🔍 正在分析代码库...")
    report = generate_report()

    print("📝 报告生成完成")
    title = f"代码审计报告 - {datetime.now().strftime('%Y-%m-%d')}"

    success = push_to_clickup(report, title, FOLDER_ID, dry_run=dry_run)

    if dry_run or success:
        print("\n✅ 审核报告已准备好")
        print("Agent可以通过 Knowledge Base 读取这份报告")

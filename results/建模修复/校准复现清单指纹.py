"""t5 复现清单指纹校准：逐条复算 SHA-256，把过期登记值刷成磁盘现值并留原值。

背景：results/问题三_参考口径/主方案_*.{json,csv} 与两个 结果提交_主方案.xlsx 在 2026-09-24 12:20–12:34 被重新生成，
而 复现清单.json 写于同日 11:12，登记的三条输入指纹仍指向旧版本（t1-D9 / t4-§8 D9）。
本脚本只改登记值，不触碰任何产物数值；保留 原记录值 供追溯。

注意（本次仓库清理）：目标清单 results/问题三_参考口径/、results/问题四_参考口径/ 已在删除性清理中移除，
直接运行会因目标缺失而失败；如确需重放，先运行 python code/问题三四_复现.py 重建这两棵目录。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = ["results/问题三_参考口径/复现清单.json", "results/问题四_参考口径/复现清单.json"]


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    for rel in MANIFESTS:
        path = ROOT / rel
        manifest = json.loads(path.read_text(encoding="utf-8"))
        stale = []
        print(f"== {rel} ==")
        for key, recorded in list(manifest["输入SHA256"].items()):
            target = ROOT / key
            assert target.is_file(), key
            actual = sha(target)
            flag = "一致" if actual == recorded else "不一致"
            print(f"  [{flag}] {key}  记录={recorded[:16]}…  磁盘={actual[:16]}…")
            if actual != recorded:
                stale.append({"文件": key, "原记录SHA256": recorded, "磁盘现值SHA256": actual})
                manifest["输入SHA256"][key] = actual
        if stale:
            manifest["指纹更新记录"] = [{
                "更新时间_UTC": now,
                "原因": "复现清单写于 2026-09-24T03:12:28Z，产物于 2026-09-24 12:20–12:34 重新生成，登记指纹过期",
                "依据": "t1 差异登记 D9、t4《12_独立推导与反例核验.md》§8 D9 行",
                "更新条目": stale,
            }]
            path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  已刷新 {len(stale)} 条并追加 指纹更新记录：{path.relative_to(ROOT)}")
        else:
            print("  无需更新")

    print("== 复核（重新加载并逐条复算） ==")
    for rel in MANIFESTS:
        manifest = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        bad = [k for k, v in manifest["输入SHA256"].items() if sha(ROOT / k) != v]
        print(f"  {rel}: 登记 {len(manifest['输入SHA256'])} 条，不一致 {len(bad)} 条 {bad}")


if __name__ == "__main__":
    main()

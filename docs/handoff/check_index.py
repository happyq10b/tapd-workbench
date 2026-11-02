# -*- coding: utf-8 -*-
"""交接索引一致性校验器（交接管家专用）

规则来源：`HANDOFF.md` §0.5.4 第 7 步 ——「索引行的正文路径不许指空」。

检查三件事：
  1. `docs/handoff/INDEX.md` 每条记录一行，序号连续、无跳号、无重号；
  2. 每行「正文路径」列指向的目标真实存在
     （指向 `docs/handoff/records/R*.md` → 文件必须存在；
       指向 `HANDOFF.md §七 #N` → 主文档必须确有该记录小节）；
  3. `HANDOFF.md` §六 索引表与 INDEX.md 的记录号集合一致。

用法：  D:/py/python.exe docs/handoff/check_index.py
退出码：0 = 全绿；1 = 有问题（逐条打印）
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HANDOFF = os.path.join(ROOT, "HANDOFF.md")
INDEX = os.path.join(ROOT, "docs", "handoff", "INDEX.md")

with open(HANDOFF, "r", encoding="utf-8") as f:
    h = f.read()
with open(INDEX, "r", encoding="utf-8") as f:
    idx = f.read()

bad = []
nums_idx = []
nums_sec6 = []


def paths_of(cell):
    """从单元格文本里取出候选路径（含反引号的，或 '正文在 ...' 形式）。"""
    m = re.search(r"`([^`]+)`", cell)
    if m:
        return m.group(1)
    m = re.search(r"正文在\s+`?([^`\s]+)`?", cell)
    if m:
        return m.group(1)
    return None


def check_rows(text, label):
    for line in text.split("\n"):
        if not re.match(r"^\| #\d+ \|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        num = cells[0].lstrip("#")
        # 「正文路径」列 = 倒数第二列（最后一列是归档状态）
        p = paths_of(cells[-2]) if len(cells) >= 2 else None
        if p is None:
            bad.append("%s #%s：正文路径列为空" % (label, num))
            continue
        if p.startswith("HANDOFF.md §七"):
            if ("### #%s · " % num) not in h:
                bad.append("%s #%s：主文档缺该记录小节（%s）" % (label, num, p))
        else:
            full = os.path.join(ROOT, p.replace("/", os.sep))
            if not os.path.isfile(full):
                bad.append("%s #%s：文件不存在（%s）" % (label, num, p))
        if label == "INDEX":
            nums_idx.append(num)
        else:
            nums_sec6.append(num)


sec6 = h.split("## 六、变更记录索引")[1].split("## 七、")[0]
check_rows(sec6, "§六")
check_rows(idx, "INDEX")

# 序号连续性
for name, nums in (("INDEX", nums_idx), ("§六", nums_sec6)):
    ints = [int(x) for x in nums]
    if ints != list(range(1, len(ints) + 1)):
        bad.append("%s 序号不连续：%s" % (name, ints))

if set(nums_idx) != set(nums_sec6):
    bad.append("§六 与 INDEX 记录号集合不一致：§六 %d 条 / INDEX %d 条" % (len(nums_sec6), len(nums_idx)))

recs = re.findall(r"^### #(\d+) · ", h, re.M)
files = [f for f in os.listdir(os.path.join(ROOT, "docs", "handoff", "records"))
         if f.startswith("R") and f != "README.md"]

print("主文档 §七 记录：%s" % (recs or "（空）"))
print("§六 索引行：%d　INDEX 行：%d　归档文件：%d" % (len(nums_sec6), len(nums_idx), len(files)))
print("主文档行数：%d" % len(h.split("\n")))

if bad:
    print("\n❌ 有问题：")
    for b in bad:
        print("  - " + b)
    sys.exit(1)
print("\n✅ 全绿：索引行路径无指空，序号连续，两处索引一致")

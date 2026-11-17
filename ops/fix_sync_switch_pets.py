# -*- coding: utf-8 -*-
"""T-204f：同步开关.bat 修复——Pets 菜单项支持选择同步环境（开发/生产）。
现状 bug：菜单分发错位（errorlevel 判断只到 4），选 [3] Pets 走了 ONLY_VERIFY、
选 [4] Verify only 走了 CANCEL，带 P/D 环境选择的 :PETS 段成了死代码。
铁律：bat 必须 rb/wb 二进制读写保证 CRLF（#110 事故）。
"""
import io, sys

P = r'E:\WB缓存\2026-10-26-15-55-08\同步开关.bat'
raw = open(P, 'rb').read()

subs = [
    # ① 分发逻辑：补 errorlevel 5 判断，[3] 正确进 :PETS
    (
        b'if errorlevel 4 goto :CANCEL\r\n'
        b'if errorlevel 3 goto :ONLY_VERIFY\r\n'
        b'if errorlevel 2 goto :PICK_PROD\r\n'
        b'if errorlevel 1 goto :PICK_DEV\r\n'
        b'goto :CANCEL\r\n',
        b'if errorlevel 5 goto :CANCEL\r\n'
        b'if errorlevel 4 goto :ONLY_VERIFY\r\n'
        b'if errorlevel 3 goto :PETS\r\n'
        b'if errorlevel 2 goto :PICK_PROD\r\n'
        b'if errorlevel 1 goto :PICK_DEV\r\n'
        b'goto :CANCEL\r\n',
    ),
    # ② 菜单文案：[3] 说明会先选环境
    (
        'echo     [3] Pets (--pets)   仅同步精灵图片（独立快速通道，不重启服务）\r\n'.encode('gbk'),
        'echo     [3] Pets (--pets)   仅同步精灵图片（先选环境：开发/生产，不重启服务）\r\n'.encode('gbk'),
    ),
    # ③ 注释补充说明
    (
        b'rem use goto labels instead.\r\n',
        b'rem use goto labels instead.\r\n'
        b'rem (2026-11-17 #123) fix: dispatch missed level 5 and sent [3] to ONLY_VERIFY,\r\n'
        b'rem leaving the :PETS env-choice branch dead -- [3] now enters :PETS and asks\r\n'
        b'rem P(prod)/D(dev) as designed.\r\n',
    ),
]

n = 0
for old, new in subs:
    if old not in raw:
        print('MISS:', old[:60]); sys.exit(1)
    raw = raw.replace(old, new, 1)
    n += 1

open(P, 'wb').write(raw)
print(f'replaced {n}/{len(subs)}，已写回（GBK+CRLF 保持）')

# 校验：CRLF 未破坏、关键标签在位
chk = raw.decode('gbk')
for key in ['goto :PETS', 'if errorlevel 5 goto :CANCEL', ':PETS', '--pets --dev', '目标 P=生产 / D=开发']:
    assert key in chk, key
assert b'\r\n' in raw and raw.count(b'\r\n') > 100
print('校验通过：CRLF 保持，:PETS 分发与 P/D 选择在位')

# -*- coding: utf-8 -*-
import sys, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, os.path.join(ROOT, 'ops'))
os.environ.setdefault('APP_SECRET', 'local-dev-secret-not-for-production')
import importlib.util
spec = importlib.util.spec_from_file_location('app', os.path.join(ROOT, 'src', 'app', 'app.py'))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
spec2 = importlib.util.spec_from_file_location('t197', os.path.join(ROOT, 'ops', 'test_t197_visibility.py'))
T = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(T)
T.setup()
try:
    P = T.P; BID = T.BID
    for u in ('u_own1', 'u_cown', 'u_cpart', 'u_bown', 'u_arch', 'u_none'):
        b, c = M.user_allowed(P + u)
        print(u, '| boards:', 'None' if b is None else sorted(b), '| cols:',
              'None' if c is None else {k: sorted(v) for k, v in c.items()})
    print('dept_stage(u_own1):', M._dept_stage_boards(P + 'u_own1'))
    print('leader_scope(u_arch):', M._leader_scope_boards(P + 'u_arch'))
    print('members:', [(r[0], r[1]) for r in M.dbq("SELECT name,account FROM team_members WHERE account LIKE '__t197%'")])
finally:
    T.cleanup()

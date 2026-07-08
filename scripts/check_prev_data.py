#!/usr/bin/env python3
from pathlib import Path
import json
for f in sorted(Path('data/yt_analytics').iterdir()):
    d = json.loads(f.read_text())
    slug = d.get('slug','?')
    ts = d.get('collected_at','?')
    summary = d.get('summary',{})
    rows = summary.get('rows',[])
    if rows:
        h = summary.get('headers',[])
        views = rows[0][h.index("views")] if "views" in h else "?"
        likes = rows[0][h.index("likes")] if "likes" in h else "?"
        print(f'{slug}: collected={ts[:19]}  views={views}  likes={likes}')
    else:
        err = summary.get('error','no rows')
        print(f'{slug}: collected={ts[:19]}  summary error: {err}')
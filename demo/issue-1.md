Title: Plugin rejected as incompatible on host 1.10.0 despite requiring >=1.9.0

After upgrading the host to **1.10.0**, the `audit-log` plugin stopped loading:

```
$ python -m app.cli 1.10.0 plugins.json
{
  "loadable": [],
  "rejected": {
    "audit-log": "requires host >=1.9.0, running 1.10.0"
  }
}
```

`plugins.json`:

```json
[{"name": "audit-log", "version": "0.3.0", "requires_host": ">=1.9.0"}]
```

Expected: `audit-log` is loadable, since 1.10.0 is newer than 1.9.0.
It worked on host 1.9.4. Looks like anything with a two-digit minor or patch
number is affected (e.g. 1.2.10 vs 1.2.9 as well).

Environment: Python 3.12, macOS.

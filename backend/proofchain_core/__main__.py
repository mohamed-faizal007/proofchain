"""`python -m proofchain_core file.pdf`: same CLI as `python -m proofchain_core.tree`.

This entry point avoids the runpy "found in sys.modules" warning that
`-m proofchain_core.tree` prints (the package imports `tree` eagerly).
"""

from proofchain_core.tree import main

raise SystemExit(main())

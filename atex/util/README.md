The point of this directory is to have miscellaneous utilities (for text
formatting, subprocess wrappers, whatever) accessible from the `util.*`
namespace, while being able to break them down into multiple `*.py` files
for readability.

These multiple `*.py` files then get automatically imported into one `globals()`
of the entire `util` module (package), appearing as a singular `util`.

Since the individual submodules cannot easily `from .* import *` themselves,
and since the intention is to give the impression of a single big `util.py`,
any local/relative imports between files should extract the necessary
identifiers via ie.

```
# in wrappers.py
from .custom_dedent import dedent

dedent(...)
```

rather than trying to preserve `custom_dedent.dedent()` or reaching beyond
parent with `from .. import util` (creating an infinite recursion).

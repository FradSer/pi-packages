# paths

isWithin(root,candidate) checks lexical containment of absolute POSIX paths after resolving dot segments. Root itself and descendants are allowed; sibling-prefix paths and traversal outside root are denied. A trailing root separator does not change meaning. Root '/' contains all absolute paths. Do not perform filesystem reads or claim symlink containment; that requires a different realpath check. Use maintained Node path functionality.
Given /work/app and /work/app2, then deny. Given a path that normalizes outside root, then deny. Given a real child or root itself, then allow.

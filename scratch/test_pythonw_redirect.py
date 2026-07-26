import os
import sys

try:
    if sys.stdout is None:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        sys.stdout = os.fdopen(1, 'w')
        sys.stderr = os.fdopen(2, 'w')
        with open("scratch_test.log", "w") as f:
            f.write("Success mapping fd 1 and 2")
except Exception as e:
    with open("scratch_test_error.log", "w") as f:
        f.write(str(e))

# Narova Direct runtime inventory

This directory is an inventory and license boundary for the experimental
Narova Direct engine. It is not a blind copy of the Narova repository and it
does not run setup scripts, install a global package, or fetch dependencies at
render time.

The pinned upstream artifact is @narova/narova@0.41.0 from the public npm
registry. The exact npm integrity, upstream gitHead, license, and the
HyperFrames 0.7.96 pin are recorded in runtime-manifest.json. A production
installer must stage the package from that exact tarball under
<install_root>/runtime/narova-direct, together with private Node, FFmpeg,
FFprobe, HyperFrames, and Chrome-for-Testing paths. The Python adapter passes
absolute paths and sets npm offline mode; it never invokes npx itself.

The published package declares os: ["darwin", "linux"]. Direct JavaScript
execution on Windows is therefore an experimental feasibility path, not a
claim of upstream Windows support. The package's 0.41.0 HyperFrames adapter
currently shells out to npx --yes hyperframes@0.7.96; a Windows production
bundle needs a local offline cache or a documented upstream adapter patch.

The existing repository vendor at third_party/narova is 0.31.14 and is
intentionally not used by Narova Direct.

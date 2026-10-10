/* Keep the outer app executable as the process image and effective bundle.
 * Do not initialize AppKit: Tk must create its TKApplication itself.
 */
#include <dlfcn.h>
#include <mach-o/dyld.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <limits.h>

typedef int (*python_main_fn)(int, char **);

static int prepend_env(const char *name, const char *prefix) {
    const char *old = getenv(name);
    size_t length = strlen(prefix) + (old && *old ? strlen(old) + 1 : 0) + 1;
    char *value = malloc(length);
    if (!value) return -1;
    snprintf(value, length, "%s%s%s", prefix, old && *old ? ":" : "", old ? old : "");
    int result = setenv(name, value, 1);
    free(value);
    return result;
}

static int path_under(char *output, size_t capacity, const char *base, const char *suffix) {
    int length = snprintf(output, capacity, "%s/%s", base, suffix);
    return length < 0 || (size_t)length >= capacity ? -1 : 0;
}

static int interpreter_args(int argc, char **argv) {
    if (argc < 2) return 0;
    /* Long application flags retain the shell launcher's -m voice_flow.main.
     * Python -m/-c, a script path, stdin, and standard short flags pass through.
     */
    if (!strcmp(argv[1], "--help") || !strcmp(argv[1], "--version")) return 1;
    if (!strncmp(argv[1], "--", 2)) return 0;
    return 1;
}

int main(int argc, char **argv) {
    char raw[PATH_MAX], executable[PATH_MAX], contents[PATH_MAX];
    char home[PATH_MAX], library[PATH_MAX], pythonpath[PATH_MAX * 3], bin[PATH_MAX];
    uint32_t capacity = sizeof(raw);
    if (_NSGetExecutablePath(raw, &capacity) || !realpath(raw, executable)) {
        fprintf(stderr, "AI Productivity Flow: cannot resolve application executable.\n");
        return 1;
    }
    memcpy(contents, executable, strlen(executable) + 1);
    char *separator = strrchr(contents, '/');
    if (!separator) return 1;
    *separator = '\0'; /* Contents/MacOS */
    separator = strrchr(contents, '/');
    if (!separator) return 1;
    *separator = '\0'; /* Contents */
    if (path_under(home, sizeof(home), contents, "Resources/runtime/python") ||
        path_under(library, sizeof(library), home, "lib/libpython3.11.dylib") ||
        path_under(bin, sizeof(bin), home, "bin")) {
        fprintf(stderr, "AI Productivity Flow: application path is too long.\n");
        return 1;
    }
    int length = snprintf(pythonpath, sizeof(pythonpath),
        "%s/Resources/src:%s/Resources/runtime/site-packages:%s/lib/python3.11/site-packages",
        contents, contents, home);
    if (length < 0 || (size_t)length >= sizeof(pythonpath) ||
        setenv("PYTHONHOME", home, 1) || prepend_env("PYTHONPATH", pythonpath) ||
        prepend_env("PATH", bin)) {
        fprintf(stderr, "AI Productivity Flow: cannot configure bundled runtime.\n");
        return 1;
    }
    void *python = dlopen(library, RTLD_NOW | RTLD_GLOBAL);
    if (!python) {
        fprintf(stderr, "AI Productivity Flow: cannot load bundled Python: %s\n", dlerror());
        return 1;
    }
    python_main_fn python_main = (python_main_fn)dlsym(python, "Py_BytesMain");
    if (!python_main) {
        fprintf(stderr, "AI Productivity Flow: bundled Python has no Py_BytesMain.\n");
        return 1;
    }
    /* Canonical executable argv[0] makes sys.executable use this launcher for
     * -m desktop/player children, preserving the outer app's code identity.
     */
    argv[0] = executable;
    if (interpreter_args(argc, argv)) return python_main(argc, argv);
    char **app_argv = calloc((size_t)argc + 3, sizeof(char *));
    if (!app_argv) return 1;
    app_argv[0] = executable;
    app_argv[1] = "-m";
    app_argv[2] = "voice_flow.main";
    for (int i = 1; i < argc; i++) app_argv[i + 2] = argv[i];
    int status = python_main(argc + 2, app_argv);
    free(app_argv);
    return status;
}

# Patches for env-config

## tcsh TCSH_XTRACEFD

Shell tracing for tcsh requires a patched tcsh that supports `TCSH_XTRACEFD` (analogous to bash's `BASH_XTRACEFD`). The full tcsh source tree is not checked in; only the patch and build instructions are.

### tcsh source

- **URL**: https://github.com/tcsh-org/tcsh
- **Patch**: `tcsh-TCSH_XTRACEFD.patch`

### Build patched tcsh

```bash
git clone https://github.com/tcsh-org/tcsh.git tcsh-src
cd tcsh-src
patch -p1 < /path/to/env-config/patches/tcsh-TCSH_XTRACEFD.patch
./configure && make
```

The resulting `tcsh` binary is built in the source directory. Point env-config at it via:

- `ENVCONFIG_TCSH_PATH=/path/to/tcsh-src/tcsh`
- Or pass `--shell-path` when running discover/trace for tcsh

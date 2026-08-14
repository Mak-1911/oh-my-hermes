# oh-my-hermes

This package exposes the `omh` command for npm and Bun global installs.

```sh
bun install -g oh-my-hermes
# or
npm install -g oh-my-hermes
```

Python 3.11 or newer must already be available. The package includes the exact
OMH wheel for its version and does not download Python packages when `omh`
starts. Continue with:

```sh
omh setup
```

Use `omh doctor` later to verify or troubleshoot the installation.

Update or remove the command with the manager that installed it:

```sh
bun update -g oh-my-hermes
bun remove -g oh-my-hermes
npm update -g oh-my-hermes
npm uninstall -g oh-my-hermes
```

These commands change only the CLI package. They preserve `~/.omh`, installed
skills, memory, and Hermes registration. Run `omh uninstall --all` before the
manager's remove command when you want a complete removal.

## Launcher cache

The launcher keeps the current exact wheel plus the two most recently used caches
and removes abandoned staging directories after 24 hours. Set `OMH_CACHE_DIR`
to override the location. Defaults are:

- macOS: `~/Library/Caches/oh-my-hermes/npm`
- Linux: `$XDG_CACHE_HOME/oh-my-hermes/npm`, or
  `~/.cache/oh-my-hermes/npm` when `XDG_CACHE_HOME` is unset
- Windows: `%LOCALAPPDATA%\oh-my-hermes\Cache\npm`

Package-manager removal preserves this cache. After every `omh` process has
stopped, delete the platform path above as the final step when no cached wheel
should remain.

Project documentation: <https://rlaope.github.io/oh-my-hermes/>

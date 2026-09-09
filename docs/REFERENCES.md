# Community references

Inspected on 2026-09-09. Interface/workflow references, not copied source.

- [Herdr v0.9.0 plugin contract](https://github.com/herdrdev/herdr/blob/v0.9.0/docs/next/website/src/content/docs/plugins.mdx): argv manifests, plugin root/state separation, invocation context, popup and marketplace discovery.
- [reviewr manifest](https://github.com/persiyanov/herdr-reviewr/blob/main/herdr-plugin.toml) and [pane action](https://github.com/persiyanov/herdr-reviewr/blob/main/herdr/pane.sh): use HERDR_BIN_PATH, distinguish invocation directory from plugin directory, prefer the invoking pane's live cwd. Reviewed MIT license; implementation here is original.
- [herdr-agent-inbox](https://github.com/douglascorrea/herdr-agent-inbox): shows why this plugin should not introduce another attention queue; serves as a comparison for explicit human workflow state.
- [herdr-review-loop](https://github.com/mikhail-angelov/herdr-review-loop): already implements a reviewer/author loop; this MVP does not schedule agents.

There is no runtime dependency on these community plugins. This is an independent community experiment, not an official Herdr plugin.

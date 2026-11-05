# Security policy

## Supported versions

Security fixes go into the latest release on
[PyPI](https://pypi.org/project/pedalpoint/). Please upgrade before reporting a
problem.

## Report a vulnerability

Please do not put details of a vulnerability in a public issue. Instead,
[open an issue](https://github.com/EMSwank/pedalpoint/issues/new) that says only
that you have a security report, and ask for a private way to share it.

Helpful reports include the pedalpoint version, the steps to reproduce the
problem, and what an attacker could do with it.

## What pedalpoint protects

- The server writes only `.draft` files, and only inside the git repository it
  started in or a worktree of that repository.
- Paths are resolved first, so `..` and symbolic links cannot escape the project.
- A symbolic link at a draft path is replaced, never written through.
- Claude Code's own permissions control promoting a draft to the real file.

Reports that get around any of these are especially welcome.

## Out of scope

- Code suggested by a model. Drafts can be wrong or unsafe, which is why Claude
  reviews them. The exception is local-only mode, where commits are marked
  `[unreviewed]` for you to check.
- Anyone who already has access to your user account, or your local model server.

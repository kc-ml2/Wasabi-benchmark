# Sandbox (not implemented)

Planned work: check out each task's repo/base_commit, provide Docker isolation,
and enforce resource limits.

Do not mount the controller repository, reference answers, or personal settings
into the agent workspace. Expose only the secrets required for execution,
such as selected API keys. No isolation functionality is implemented yet.

# OpenCode

Copy `opencode.jsonc.example` to `opencode.jsonc`, start Evo MCP locally, then run
`opencode mcp list`. The example uses the local Streamable HTTP endpoint and disables OAuth because
localhost mode does not require authentication.

For a hosted endpoint, do not paste a token into the file. Configure an environment-backed
`Authorization` header supported by your OpenCode version and keep `oauth: false` only when Evo uses
Bearer/API-key authentication.

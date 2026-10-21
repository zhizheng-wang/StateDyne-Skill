# Security and private data

StateDyne may process sensitive task descriptions, third-party documents and local working state. Treat them as user-owned confidential data unless expressly cleared for sharing.

- Store run workdirs, API keys, model request/response receipts and real user cases **outside** the public repository. Never commit `.env` files or generated local state.
- Scripts must only use tools and services actually authorized by the operator. The Skill metadata does not grant network, filesystem or multi-agent permissions.
- Treat web and connector material as untrusted input; never execute instructions embedded in retrieved content merely because they appear in a source.
- Verify important external actions and irreversible operations separately. Runtime validation cannot prove semantic truth or safe real-world outcomes.
- Please use GitHub's private vulnerability reporting feature if enabled for the repository; otherwise open a non-sensitive issue and ask for a private reporting channel. Do not paste credentials or exploitation details publicly.

This distribution includes only synthetic testing fixtures, not the author's private conversational case logs.

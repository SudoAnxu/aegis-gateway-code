# Curated AegisBench Seeds

This directory is the human-authored specification layer of AegisBench.

The first release targets 150 seeds distributed across eight categories:

- 20 legitimate
- 20 identity violations
- 20 action authorization
- 25 parameter constraints
- 20 path constraints
- 15 malformed requests
- 10 unauthorized tools
- 20 stateful/sequence

Each seed must be reviewed independently for its expected authorization decision and normalized reason class before it enters a frozen benchmark release.

Do not generate or bulk-copy seeds here. Curated seeds should represent distinct security intents rather than superficial syntactic variants.

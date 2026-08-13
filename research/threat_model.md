# Aegis Agent–Tool Governance Threat Model

Status: research draft

## 1. Scope

This study evaluates runtime governance at the boundary between an AI agent and external tools. The gateway is treated as a policy enforcement point between the agent's requested action and the trusted tool endpoint.

## 2. System model

A tool request is represented as:

R = (A, T, X, θ)

where:
- A is the claimed agent identity.
- T is the target tool.
- X is the requested action.
- θ is the set of request parameters.

The policy evaluator produces:

D ∈ {ALLOW, DENY}

A decision is considered correct when it agrees with the expected authorization label for the benchmark scenario.

## 3. Adversary model

The initial threat model treats the agent as potentially untrusted. The agent may generate tool requests that are unauthorized, malformed, or inconsistent with the applicable policy. The tool execution services and the gateway host are trusted components within the experimental environment.

The initial study does not claim to defend against a compromised gateway host, a compromised tool implementation, or an attacker with operating-system-level control. Prompt injection is also outside the initial threat model unless a benchmark scenario explicitly models the resulting unauthorized tool request.

## 4. Security scenarios

The benchmark will cover:

1. Unauthorized tool invocation.
2. Unauthorized action on an otherwise permitted tool.
3. Parameter constraint violations, such as exceeding a permitted amount.
4. Resource/path constraint violations.
5. Agent identity mismatch.
6. Malformed tool requests.

Additional adversarial scenarios may be added only when their expected behavior can be specified independently of the implementation.

## 5. Experimental systems

B0 — Direct execution: the request is sent to the tool without a governance layer.

B1 — Simple authorization baseline: an allowlist authorizes agent/tool/action combinations but does not implement Aegis parameter-level constraints.

B2 — Aegis: the proposed runtime governance system evaluates agent, tool, action, and supported parameter constraints before execution.

## 6. Security objective

The primary security objective is to prevent benchmark requests labelled DENY from reaching the protected tool while minimizing rejection of requests labelled ALLOW.

The study therefore reports security effectiveness together with legitimate-task utility and runtime overhead. No claim of universal security is made from the benchmark alone.

## 7. Benchmark validity

Benchmark cases should not be derived solely from the implementation's existing policy examples. The benchmark will combine manually designed seed scenarios with programmatically generated mutations of valid requests. A held-out subset should be independently reviewed where practical.

The benchmark dataset will be versioned and hashed for reproducibility.

## 8. Research questions

RQ1: Does runtime governance reduce unauthorized tool execution compared with direct execution?

RQ2: Does fine-grained parameter-aware governance provide measurable benefit over simple agent/tool/action authorization?

RQ3: What runtime overhead is introduced by the governance layer?

RQ4: Does stronger enforcement preserve legitimate tool-use success?

## 9. Non-claims

The study will not claim that Aegis detects malicious intent, makes an AI agent safe in general, or protects against threats outside the stated model. Results will be reported only for the tested policies, tools, scenarios, and experimental environment.

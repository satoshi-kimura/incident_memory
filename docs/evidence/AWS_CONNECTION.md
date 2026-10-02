# Proof: coding agent connected to AWS

Rule: *"A coding agent connected to the AWS console, with documented proof of the connection."*

**Live app:** https://d2zs12dmk7373h.cloudfront.net (public, no login, deployed on AWS us-east-1)
**Coding agent:** Claude Code (Anthropic).
**Connection:** Agent Toolkit for AWS. It provides the **AWS MCP Server**
(`https://aws-mcp.us-east-1.api.aws/mcp`, through `mcp-proxy-for-aws`) plus the AWS agent skills
(aws-serverless, aws-iam, aws-observability, amazon-bedrock, …), registered in Claude Code.
**AWS account:** AWS account (ID masked), region us-east-1.
**IAM identity:** the first connection checks (sections 3 and 4, 2026-09-25 15:51 UTC) ran as the
account's existing IAM user `user/terraform`. Minutes later the project switched to its dedicated,
least-privilege IAM user `user/sandbox` (limited to `incident-memory-*` in us-east-1), which made the
in-session call in section 5 (about 16:05 UTC) and all later agent work.

## 1. The MCP server is registered in the coding agent

`aws-mcp/01-claude-mcp-config.txt`

```
$ claude mcp list   (excerpt)
aws-mcp: uvx mcp-proxy-for-aws@latest https://aws-mcp.us-east-1.api.aws/mcp --metadata INSTALL_SOURCE=aws-cli - ✔ Connected

$ claude mcp get aws-mcp
aws-mcp:
  Scope: User config (available in all your projects)
  Status: ✔ Connected
```

## 2. The server exposes AWS tools

`aws-mcp/02-tools-list.txt`. The server is *MCP Proxy for AWS 1.7.0*, with 8 tools: `aws___run_script`
(AWS API access), `aws___search_documentation`, `aws___read_documentation`, `aws___retrieve_skill`,
`aws___list_regions`, `aws___get_regional_availability`, `aws___get_tasks`, `aws___get_presigned_url`.

## 3. A read-only call through the MCP server reaches this AWS account

`aws-mcp/03-run-script-readonly.txt` (script: `aws-mcp/mcp_call.py`). The agent called
`aws___run_script` with read-only APIs (GetCallerIdentity, ListFunctions, DescribeTable,
DescribeAlarms). It ran as `user/terraform`, before the switch to the dedicated user, and returned
the live Incident Memory resources:

```json
{
  "caller": "user/terraform",
  "incident_memory_lambdas": ["incident-memory-api", "incident-memory-demo-orders-api", "incident-memory-demo-scenario"],
  "dynamodb_table": ["incident-memory-incidents", "ACTIVE"],
  "demo_alarms": [["incident-memory-demo-orders-api-errors-high", "OK"], ...]
}
```

## 4. AWS itself recorded the MCP calls (CloudTrail)

`aws-mcp/04-cloudtrail-aws-mcp-events.txt`. CloudTrail events with
`eventSource: aws-mcp.amazonaws.com` (`CallReadWriteTool`, `DestroySession`), user agent
`mcp-proxy-for-aws/1.7.0`, identity `IAMUser/terraform`, region us-east-1. This is
independent, AWS-side proof of the agent's MCP connection to the account.

## 5. The agent calls the MCP tool directly in its session

`aws-mcp/05-agent-session-call.md`. Inside the Claude Code session, the agent called the tool
**`aws-mcp - aws___run_script`**. It ran as the project's dedicated IAM user `user/sandbox`, after the switch,
(limited to `incident-memory-*` in us-east-1), returned the Incident Memory resources, and then
queried CloudTrail through the same tool.

## 6. The whole build was done by the agent against AWS

See [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md). The agent verified the AWS identity, probed Bedrock
model access, ran every Terraform plan through the safety gate and applied it, ran the controlled
incident scenarios, and verified the live app. Terraform plan and apply outputs are in this folder.

## Screenshots

- [x] `screenshots/05-agent-calling-aws-mcp.png`: the Claude Code session in English: the agent states it is
      calling the AWS MCP Server and runs **`aws-mcp - aws___run_script (MCP)`** with read-only calls
      (GetCallerIdentity, ListFunctions, DescribeTable, DescribeAlarms, GetApis). The result is in `aws-mcp/05-agent-session-call.md`.
- [x] `screenshots/07-claude-code-mcp-aws-connected.png`: Claude Code's `/mcp` panel showing **aws-mcp ✔ (8 tools)** as a user MCP server

Screenshots are cropped to the Claude Code window only, so that no other project's information appears.

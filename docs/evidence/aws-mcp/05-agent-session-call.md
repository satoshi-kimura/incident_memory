# Agent session: Claude Code calls AWS through the AWS MCP Server

Recorded 2026-09-25 about 16:05 UTC, inside the Claude Code session that built Incident Memory.
After `/mcp` reconnected **aws-mcp**, the agent called the MCP tool **`aws-mcp - aws___run_script`**
directly as a tool call. There is no local AWS CLI in this path: the MCP server runs the script in its
sandbox and signs the AWS API calls with the connected identity.

## Tool call (input)

Tool: `mcp__aws-mcp__aws___run_script`

```python
async def c(svc, op, **params):
    return await call_boto3(service_name=svc, operation_name=op, region_name="us-east-1", params=params or None)

ident, fns, table, alarms = await asyncio.gather(
    c("sts", "GetCallerIdentity"),
    c("lambda", "ListFunctions"),
    c("dynamodb", "DescribeTable", TableName="incident-memory-incidents"),
    c("cloudwatch", "DescribeAlarms", AlarmNamePrefix="incident-memory-demo"),
    return_exceptions=True,
)
result = {...}   # caller, Incident Memory Lambda functions, table status, demo alarm states
result
```

## Tool result (output, verbatim)

```json
{"status":"success","stdout":"",
 "return_value":{
   "caller":"user/sandbox",
   "incident_memory_lambdas":["incident-memory-api","incident-memory-demo-orders-api","incident-memory-demo-scenario"],
   "dynamodb_table":["incident-memory-incidents","ACTIVE"],
   "demo_alarms":[["incident-memory-demo-orders-api-errors-high","OK"],
                  ["incident-memory-demo-orders-api-latency-high","OK"],
                  ["incident-memory-demo-orders-api-throttles-high","OK"]]},
 "api_calls":[{"service":"sts","operation":"GetCallerIdentity","status":"success"},
              {"service":"lambda","operation":"ListFunctions","status":"success","n_items":{"Functions":3}},
              {"service":"dynamodb","operation":"DescribeTable","status":"success"},
              {"service":"cloudwatch","operation":"DescribeAlarms","status":"success","n_items":{"MetricAlarms":3,"CompositeAlarms":0,"LogAlarms":0}}]}
```

The identity is `user/sandbox`, the dedicated IAM user for this project. Its permissions are limited
to `incident-memory-*` resources in us-east-1. All four calls were read-only.

## Follow-up call through the same tool: CloudTrail lookup

The agent then used `aws___run_script` again to query CloudTrail (`LookupEvents`,
`EventSource = aws-mcp.amazonaws.com`). The result listed the earlier `CallReadWriteTool` and
`DestroySession` events from the MCP server; see `04-cloudtrail-aws-mcp-events.txt`.

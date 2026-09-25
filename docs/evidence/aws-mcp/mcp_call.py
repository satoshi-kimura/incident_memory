import asyncio, json, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(command="uvx", args=["mcp-proxy-for-aws@latest", "https://aws-mcp.us-east-1.api.aws/mcp",
                                                    "--metadata", "INSTALL_SOURCE=aws-cli"])
CODE = '''
async def c(svc, op, **params):
    return await call_boto3(service_name=svc, operation_name=op, region_name="us-east-1", params=params or None)

ident, fns, table, alarms = await asyncio.gather(
    c("sts", "GetCallerIdentity"),
    c("lambda", "ListFunctions"),
    c("dynamodb", "DescribeTable", TableName="incident-memory-incidents"),
    c("cloudwatch", "DescribeAlarms", AlarmNamePrefix="incident-memory-demo"),
)
result = {
    "caller": ident["Arn"].split(":")[-1],
    "incident_memory_lambdas": sorted(f["FunctionName"] for f in fns["Functions"] if f["FunctionName"].startswith("incident-memory")),
    "dynamodb_table": [table["Table"]["TableName"], table["Table"]["TableStatus"]],
    "demo_alarms": [[a["AlarmName"], a["StateValue"]] for a in alarms["MetricAlarms"]],
}
result
'''

async def main():
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("aws___run_script", {"code": CODE})
            for c in res.content:
                print(getattr(c, "text", c))

asyncio.run(main())

import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(command="uvx", args=["mcp-proxy-for-aws@latest", "https://aws-mcp.us-east-1.api.aws/mcp",
                                                    "--metadata", "INSTALL_SOURCE=aws-cli"])

async def main():
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            print("SERVER", init.server_info.name, init.server_info.version)
            tools = await s.list_tools()
            for t in tools.tools:
                print("TOOL", t.name, "-", (t.description or "").split("\n")[0][:110])
                print("  SCHEMA", json.dumps((t.input_schema or {}).get("properties", {}))[:300])

asyncio.run(main())

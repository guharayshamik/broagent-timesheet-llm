import asyncio
from llm_agent.llm_agent import chain

async def test():
    result = await chain.ainvoke("I took annual leave from August 1 to August 3")
    print(result)

asyncio.run(test())

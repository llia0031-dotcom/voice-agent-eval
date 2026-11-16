# Confirming before an irreversible tool call: saved excerpts (fetched 2026-11-14)

Stars and licences from the GitHub API on 2026-11-14.

## OpenAI Agents SDK (openai/openai-agents-python, 30667 stars, MIT), https://openai.github.io/openai-agents-python/human_in_the_loop/

> Set needs_approval to True to always require approval or provide an async function that decides per call. The callable receives the run context, parsed tool parameters, and the tool call ID. 

> needs_approval is available on function_tool , Agent.as_tool , ShellTool , and ApplyPatchTool . Local MCP servers also support approvals through require_approval on MCPServerStdio , MCPServerSse , and MCPServerStreamableHttp . Hosted MCP servers support approvals via HostedMCPTool with tool_config={"require_approval": "always"}

## LangChain (langchain-ai/langchain, 149480 stars, MIT), https://docs.langchain.com/oss/python/langchain/human-in-the-loop.md

```python

agent = create_agent(
    model="gpt-6.1-sol",
    tools=[write_file, execute_sql, read_data],
    middleware=[
        HumanInTheLoopMiddleware( # [!code highlight]
            interrupt_on={
                "write_file": True,  # All decisions (approve, edit, reject, respond) allowed
                "execute_sql": {"allowed_decisions": ["approve", "reject"]},  # No editing allowed
                "read_data": False, # Safe operation, no approval needed
            },
            # Prefix for interrupt messages - combined with tool name and args to form the full message
            # e.g., "Tool execution pending approval: execute_sql with query='DELETE FROM...'"
            # Individual tools can override this by specifying a "description" in their interrupt config
            description_prefix="Tool execution pending approval",
        ),
    ],
```

## Nuance Mix, dialog design best practices, https://docs.nuance.com/mix/best-practices/dialog-planning/confirm/

> Implicit confirmation acknowledges the user’s choice and moves the conversation along faster. Although the user has an opportunity at any time to correct the application, the user may not notice the error or feel unsure how (or reluctant) to correct it. For this reason, use implicit confirmation when the confidence level is high and when the potential consequence of an error in understanding is low. 
> Conversely, use explicit confirmation when: 
> Confidence level is low 
> The application is about to perform an action it cannot undo 
> Business rules dictate use (for example, before submitting a payment) 
> Explicit confirmation instills confidence: gives users the chance to say “Yes” or “No” (or to make a forced choice decision) and helps prevent serious problems from occurring (such as an unintended purchase) due to false accepts. 

## Bixby developer guide, Confirmation Moments (https://bixbydevelopers.com/dev/docs/dev-guide/design-guides/conversations.confirm, fetched 2026-11-14)

> You should design your capsule such that Bixby confirms any irreversible or critical tasks.

> The dialog used on a Confirmation Moment should be a brief and direct question that prompts the user to act. For more information on how to write dialog, see the 
